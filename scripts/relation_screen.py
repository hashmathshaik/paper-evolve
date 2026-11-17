"""Jev screening and cached rankings for the Qwen relationship pipeline.
All optional new screening shares the durable relationship spending ledger.
"""
import hashlib,json,math,sqlite3,time
from urllib import request,error
import relation_core as H

VERSION='jev-screen-v1'
THRESHOLD=.5

def score(answers):
    values={k:answers[k]['noul'] for k in ['related',*H.J.TYPES]}
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in values.values()):raise ValueError('Invalid Jev score')
    return values['related'],{k.title():values[k] for k in H.J.TYPES},min(values['related'],max(values[k] for k in H.J.TYPES))

def decision(a,b,answers):
    related,types,rank=score(answers)
    passed=related>=THRESHOLD and max(types.values())>=THRESHOLD
    audit=not passed and int(hashlib.sha256((VERSION+a+'|'+b).encode()).hexdigest()[:8],16)%20==0
    return {'passed':passed,'audit':audit,'related':related,'types':types,'score':rank}

def setup(ledger):
    ledger.db.execute('CREATE TABLE IF NOT EXISTS screens(a TEXT,b TEXT,text_hash TEXT,decision TEXT,source TEXT,PRIMARY KEY(a,b))');ledger.db.commit()

def fingerprint(state):
    # Citations/context can improve over time without invalidating an abstract-only screen.
    return hashlib.sha256(json.dumps([state['paper_a'],state['paper_b']],sort_keys=True).encode()).hexdigest()

def prepare_gate(ledger,papers,pairs,cites,contexts,new_budget=.5):
    setup(ledger)
    legacy={}
    with sqlite3.connect(H.J.E/'jev.sqlite3') as db:
        # Use abstract-only legacy scores when available; context is secondary.
        for a,b,mode,raw in db.execute("SELECT a,b,mode,answers FROM runs ORDER BY CASE mode WHEN 'abstract' THEN 2 WHEN 'context' THEN 1 ELSE 0 END"):
            legacy[(a,b)]=json.loads(raw)
    for a,b,raw,st in ledger.db.execute("SELECT a,b,result,state FROM calls WHERE status='screen_complete'"):
        legacy[(a,b)]=(json.loads(raw),fingerprint(json.loads(st)))
    new_spent=ledger.db.execute("SELECT COALESCE(SUM(cost),0) FROM calls WHERE model=?",(H.J.MODEL,)).fetchone()[0]
    api_key=None;seen=0
    for a,b in pairs:
        state=H.make_state(a,b,papers,cites,contexts);identity=fingerprint(state)
        old=ledger.db.execute('SELECT text_hash FROM screens WHERE a=? AND b=?',(a,b)).fetchone()
        if old and old[0]==identity:continue
        source='legacy_jev_cache';answers=legacy.get((a,b))
        if isinstance(answers,tuple):
            answers,old_hash=answers
            if old_hash!=identity:answers=None
            source='jev_screen'
        if answers is None:
            # Limit new Jev calls as well as the shared total. Never spend on every pair blindly.
            if new_spent>=new_budget or (H.J.E/'STOP').exists():continue
            body=json.dumps({'model':H.J.MODEL,'state':{'paper_a':state['paper_a'],'paper_b':state['paper_b']},
                             'questions':{k:H.J.QUESTIONS[k] for k in ['related',*H.J.TYPES]}}).encode()
            bound=(len(body)+1024)*H.J.PRICE_PER_M/1e6
            if new_spent+bound>new_budget:continue
            if api_key is None:api_key=H.J.load_key()
            key='screen-'+hashlib.sha256(VERSION.encode()+body).hexdigest()
            if not ledger.reserve(key,a,b,H.J.MODEL,state,bound):continue
            new_spent+=bound
            req=request.Request(H.J.URL,data=body,headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json'})
            try:
                with request.urlopen(req,timeout=60) as response:r=json.load(response)
            except error.HTTPError as exc:
                ledger.finish(key,None,{},0,'screen_rejected',f'HTTP {exc.code}');new_spent-=bound
                raise RuntimeError(f'Jev screening rejected (HTTP {exc.code}); review account before resuming.') from None
            except (error.URLError,TimeoutError,OSError):
                ledger.finish(key,None,{},bound,'screen_unknown','Network outcome uncertain; reservation retained.');continue
            usage=r.get('usage',{});tokens=usage.get('input_tokens')
            actual=tokens*H.J.PRICE_PER_M/1e6 if isinstance(tokens,int) and tokens>=0 else bound
            answers=r.get('answers',{})
            try:score(answers)
            except (ValueError,TypeError,KeyError):
                ledger.finish(key,None,usage,actual,'screen_invalid','Invalid Jev screening response.');continue
            ledger.finish(key,answers,usage,actual,'screen_complete');new_spent+=actual-bound;source='jev_screen'
        try:d=decision(a,b,answers)
        except (ValueError,TypeError,KeyError):continue
        ledger.db.execute('INSERT OR REPLACE INTO screens VALUES (?,?,?,?,?)',(a,b,identity,json.dumps(d),source));seen+=1
        if seen%100==0:ledger.db.commit()
    ledger.db.commit()
    return gate_report(ledger,len(pairs))

def gate_report(ledger,total):
    rows=ledger.db.execute('SELECT decision,source FROM screens').fetchall();passed=audits=0
    for raw,_ in rows:
        d=json.loads(raw);passed+=d['passed'];audits+=d['audit']
    return {'candidate_pairs':total,'jev_screened':len(rows),'jev_passed':passed,'negative_audit_sample':audits,
            'unscreened':total-len(rows),'screen_threshold':THRESHOLD,'audit_fraction':.05,'new_screen_cost_usd':ledger.db.execute('SELECT COALESCE(SUM(cost),0) FROM calls WHERE model=?',(H.J.MODEL,)).fetchone()[0]}

def eligible(ledger,pairs):
    rows={(a,b):json.loads(raw) for a,b,raw in ledger.db.execute('SELECT a,b,decision FROM screens')}
    good=[p for p in pairs if p in rows and rows[p]['passed']]
    audits=[p for p in pairs if p in rows and rows[p]['audit']]
    audits=audits[:max(1,math.ceil(len(good)/19))]
    # Interleave one rejected-screen audit after every 19 positives.
    output=[]
    for i in range(0,max(len(good),len(audits)*19),19):
        output.extend(good[i:i+19])
        if i//19<len(audits):output.append(audits[i//19])
    return output,rows
