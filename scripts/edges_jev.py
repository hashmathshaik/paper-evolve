"""Type candidate paper pairs with Jev (TypeSafe AI 'System One', pinned jev-1.13.0), following TypeSafe docs:
object state, one Noul per relation type (multi-label) + a companion 'related' Noul instead of a 'none' option.
State is billed once per request; extra questions cost only their own tokens.

Modes (cached separately in work/edges/jev.sqlite3, keyed by (a,b,mode)):
  abstract : titles+abstracts only. For pairs whose citing reference list is unknown, and to test vs citations (no leak).
  context  : + sentences in B that cite A (Semantic Scholar contexts). For citation-backed pairs.
Commands:
  pilot    : n abstract-mode pairs with known citation label (half positive) + n context-mode positives.
  eval     : AUC of 'related' vs B-cites-A (abstract mode), type mix, agreement with S2 intents / isInfluential.
  run      : --mode context -> all citation-backed pairs; --mode abstract -> unknown-reference pairs, best rank first.
Hard budget: --budget-usd caps total spend over ALL runs (sum of billed input tokens in the cache).
"""
import argparse,json,random,sqlite3,sys,threading,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request,error
sys.path.insert(0,str(Path(__file__).parent))
from voyage_pipeline import ROOT,read_records

MODEL='jev-1.13.0';URL='https://api.typesafe.ai/v1/systemone';PRICE_PER_M=0.042;SEED=0
E=ROOT/'work/edges';TYPES=['extends','challenges','combines','transfers','revives']
B_CITES='`citation.sentences_in_b_citing_a`'

def noul(question,yes,no):return {'type':'noul','instructions':question,'criteria':{'true':yes,'false':no}}
FACETS={'method':'algorithm, model or technique','architecture':'network or system architecture','objective':'training objective, loss or optimization',
 'data':'dataset, benchmark or evaluation protocol','theory':'theoretical result or analysis','problem':'problem formulation or task definition'}
QUESTIONS={
 'related':noul('Does `paper_b` build on, respond to, or directly reuse a specific contribution of `paper_a`? Use the abstracts and, if present, '+B_CITES+'.',
  '`paper_b` depends on or responds to a particular idea, method, result or resource of `paper_a`','the papers merely share a topic, or `paper_a` is only mentioned in passing among many related works'),
 'extends':noul('Does `paper_b` take `paper_a`\'s contribution and add to it (improve, generalize, scale or add capabilities)?',
  '`paper_b` keeps `paper_a`\'s core idea and builds more on top of it','`paper_b` replaces, criticizes, or only cites `paper_a`; or works on a different idea'),
 'challenges':noul('Does `paper_b` identify a failure, limitation or wrong assumption in `paper_a`\'s contribution and respond to it?',
  '`paper_b` explicitly points out a weakness of `paper_a`\'s approach (e.g. it ignores X, fails when Y, is too slow) and addresses it','`paper_b` does not criticize `paper_a`\'s approach'),
 'combines':noul('Does `paper_b` join `paper_a`\'s contribution with a contribution from a separate line of work?',
  '`paper_b`\'s method is explicitly a combination of `paper_a`\'s idea and another distinct idea','`paper_b` uses only one line of work, or just lists several baselines'),
 'transfers':noul('Does `paper_b` apply `paper_a`\'s contribution in a different task, domain, modality or setting?',
  '`paper_b` carries `paper_a`\'s idea to a setting `paper_a` did not target','`paper_b` works in the same task and setting as `paper_a`'),
 'revives':noul('Does `paper_b` reintroduce an older approach from `paper_a` that had fallen out of use, under new conditions (stronger models, new hardware, new data)?',
  '`paper_a`\'s approach was older or abandoned and `paper_b` brings it back','`paper_a`\'s approach was current when `paper_b` used it, or `paper_b` does not reuse it'),
 'inherited':{'type':'choice','instructions':'What does `paper_b` mainly take from `paper_a`?','criteria':FACETS},
 'changed':{'type':'choice','instructions':'What does `paper_b` mainly change relative to `paper_a`?','criteria':{**FACETS,'domain':'application domain, task or modality'}},
}

def load_key():
 for line in (ROOT/'.env').read_text().splitlines():
  k,_,v=line.partition('=')
  if k.strip()=='TYPESAFE_API_KEY':return v.strip()
 raise SystemExit('TYPESAFE_API_KEY missing from .env')

def state(a,b,ctx=None,cited=False):
 card=lambda p:{'title':p['title'],'year':p['year'],'venue':p['venue'],'abstract':p['abstract']}
 s={'paper_a':card(a),'paper_b':card(b)}
 if ctx is not None:s['citation']={'sentences_in_b_citing_a':ctx[:8]}
 elif cited:s['citation']={'paper_b_reference_list_includes_paper_a':True}
 return s

def jev(key,st):
 body=json.dumps({'model':MODEL,'state':st,'questions':QUESTIONS}).encode()
 for attempt in range(8):
  try:
   req=request.Request(URL,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
   with request.urlopen(req,timeout=120) as r:return json.load(r)
  except error.HTTPError as exc:
   if exc.code in [429,500,502,503,504]:
    try:wait=float(exc.headers.get('retry-after') or 0)
    except ValueError:wait=0
    time.sleep(max(wait,2**attempt));continue
   raise SystemExit(f'Jev HTTP {exc.code}: {exc.read()[:300]}')
  except (error.URLError,TimeoutError,OSError):time.sleep(2**attempt)
 raise RuntimeError('Jev unavailable')

def papers():
 corpus={r['id']:r for r in read_records('corpus')}
 db=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3');abst=dict(db.execute('SELECT url,abstract FROM abstracts'))
 venue={'aclanthology.org':'ACL Anthology','openreview.net':'ICLR','papers.nips.cc':'NeurIPS','proceedings.mlr.press':'ICML'}
 return {pid:{**r,'abstract':abst[r['source_url']],'venue':venue.get(r['source_url'].split('/')[2],'')} for pid,r in corpus.items() if r['source_url'] in abst}

def candidate_pairs(P):
 import numpy as np
 d=np.load(E/'knn.npz');ids,idx,sim=d['ids'],d['idx'],d['sim'];seen={}
 for i in range(len(ids)):
  for rank,(j,s) in enumerate(zip(idx[i],sim[i])):
   a,b=ids[i],ids[j]
   if a not in P or b not in P or s>=0.99:continue  # >=0.99: same paper listed twice, not an edge
   if (P[a]['year'],a)>(P[b]['year'],b):a,b=b,a
   if (a,b) not in seen or rank<seen[(a,b)][1]:seen[(a,b)]=(float(s),rank)
 return seen

def cites():
 # Reference lists from Semantic Scholar and OpenAlex (OpenAlex fills publisher-elided S2 lists).
 db=sqlite3.connect(E/'s2.sqlite3',timeout=120);s2=dict(db.execute('SELECT paper_id,s2_id FROM ids WHERE s2_id IS NOT NULL'))
 refs={k:set(json.loads(v)) for k,v in db.execute('SELECT s2_id,refs FROM refs') if v!='[]'}
 try:
  oa=dict(db.execute('SELECT paper_id,oa_id FROM oa WHERE oa_id IS NOT NULL'))
  oarefs={k:set(json.loads(v)) for k,v in db.execute("SELECT oa_id,refs FROM oa WHERE oa_id IS NOT NULL AND refs!='[]'")}
 except sqlite3.OperationalError:oa,oarefs={},{}
 return s2,refs,oa,oarefs

def contexts():
 db=sqlite3.connect(E/'s2.sqlite3')
 try:return {(c,d):(json.loads(x),json.loads(i),inf) for c,d,x,i,inf in db.execute('SELECT citing,cited,contexts,intents,influential FROM contexts')}
 except sqlite3.OperationalError:return {}

def label(a,b,cit):
 # 1 if the later paper's reference list (S2 or OpenAlex) contains the earlier one; None when neither list is known.
 s2,refs,oa,oarefs=cit;known=hit=False
 if s2.get(a) and s2.get(b) in refs:known=True;hit|=s2[a] in refs[s2[b]]
 if oa.get(a) and oa.get(b) in oarefs:known=True;hit|=oa[a] in oarefs[oa[b]]
 return int(hit) if known else None

def auc(scores,labels):
 pos=sum(labels);neg=len(labels)-pos
 if not pos or not neg:return float('nan')
 order=sorted(range(len(scores)),key=lambda i:scores[i]);r=[0]*len(scores)
 for k,i in enumerate(order):r[i]=k+1
 return (sum(r[i] for i,l in enumerate(labels) if l)-pos*(pos+1)/2)/(pos*neg)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('cmd',choices=['pilot','eval','run','compare']);ap.add_argument('--mode',choices=['abstract','context','cited'])
 ap.add_argument('--n',type=int,default=500);ap.add_argument('--workers',type=int,default=8);ap.add_argument('--budget-usd',type=float,default=4.8);args=ap.parse_args()
 random.seed(SEED);print('seed',SEED,'model',MODEL,vars(args),flush=True)
 db=sqlite3.connect(E/'jev.sqlite3',check_same_thread=False)
 db.execute('CREATE TABLE IF NOT EXISTS runs(a TEXT,b TEXT,mode TEXT,sim REAL,rank INTEGER,answers TEXT,input_tokens INTEGER,PRIMARY KEY(a,b,mode))');db.commit()
 P=papers();pairs=candidate_pairs(P);cit=cites();s2,refs=cit[0],cit[1];C=contexts()
 ctx=lambda a,b:C.get((s2.get(b),s2.get(a)))
 print('papers',len(P),'candidate pairs',len(pairs),'papers with refs S2/OA',len(refs),len(cit[3]),'context rows',len(C),flush=True)
 cap=int(args.budget_usd/PRICE_PER_M*1e6)
 def spent():return db.execute('SELECT COALESCE(SUM(input_tokens),0) FROM runs').fetchone()[0]

 def label_all(items):
  done={(a,b,m) for a,b,m in db.execute('SELECT a,b,mode FROM runs')};items=[x for x in items if x not in done]
  print('to label',len(items),'| spent so far $%.4f of $%.2f cap' % (spent()/1e6*PRICE_PER_M,args.budget_usd),flush=True)
  key=load_key();lock=threading.Lock();used=[spent()];t=time.time();count=[0]
  def work(x):
   a,b,mode=x
   if used[0]>=cap:return
   c=ctx(a,b)[0] if mode=='context' else None
   r=jev(key,state(P[a],P[b],c,cited=mode=='cited'));tok=r.get('usage',{}).get('input_tokens',0);s,rank=pairs[(a,b)]
   with lock:
    db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?)',(a,b,mode,s,rank,json.dumps(r['answers']),tok));db.commit();used[0]+=tok;count[0]+=1
    if count[0]%200==0:print(f'{count[0]}/{len(items)} labelled, ${used[0]/1e6*PRICE_PER_M:.4f} spent, {time.time()-t:.0f}s',flush=True)
  with ThreadPoolExecutor(args.workers) as pool:list(pool.map(work,items))
  if used[0]>=cap:print('BUDGET CAP REACHED; stopped.',flush=True)

 directed=lambda k:P[k[0]]['year']<P[k[1]]['year']
 if args.cmd=='pilot':
  known=[k for k in pairs if directed(k) and label(*k,cit) is not None];random.shuffle(known)
  pos=[k for k in known if label(*k,cit)];neg=[k for k in known if not label(*k,cit)]
  withctx=[k for k in pos if ctx(*k) and ctx(*k)[0]]
  items=[(a,b,'abstract') for a,b in pos[:args.n//2]+neg[:args.n//2]]+[(a,b,'context') for a,b in withctx[:args.n]]
  print('pilot: abstract',min(len(pos),args.n//2)+min(len(neg),args.n//2),'| context',min(len(withctx),args.n),flush=True);label_all(items)
 if args.cmd=='compare':
  # Same citation-backed pairs with vs without citing sentences: is waiting for sentences worth it?
  both=[k for k in pairs if directed(k) and label(*k,cit) and ctx(*k) and ctx(*k)[0]];random.shuffle(both);both=both[:args.n]
  label_all([(a,b,'context') for a,b in both]+[(a,b,'cited') for a,b in both])
  R={(a,b,m):json.loads(x) for a,b,m,x in db.execute('SELECT a,b,mode,answers FROM runs')}
  both=[k for k in both if (k[0],k[1],'context') in R and (k[0],k[1],'cited') in R];inf=[ctx(*k)[2] for k in both];meth=[int('methodology' in ctx(*k)[1]) for k in both]
  print(f'\n[compare] n={len(both)} influential={sum(inf)} methodology-intent={sum(meth)}')
  for m in ['context','cited']:
   rel=[R[(a,b,m)]['related']['noul'] for a,b in both];ext=[R[(a,b,m)]['extends']['noul'] for a,b in both]
   print(f'  {m:8s} AUC related vs isInfluential {auc(rel,inf):.3f} | AUC extends vs methodology {auc(ext,meth):.3f} | related>=0.5 {sum(r>=.5 for r in rel)/len(rel):.1%}')
  for t in TYPES:
   agree=sum((R[(a,b,'context')][t]['noul']>=.5)==(R[(a,b,'cited')][t]['noul']>=.5) for a,b in both)/len(both)
   print(f'  {t:10s} same yes/no decision in both modes: {agree:.1%}')
  return
 if args.cmd=='run':
  if args.mode=='context':
   items=[(a,b,'context') for (a,b) in sorted(pairs,key=lambda k:pairs[k][1]) if directed((a,b)) and label(a,b,cit) and ctx(a,b) and ctx(a,b)[0]]
  elif args.mode=='cited':
   items=[(a,b,'cited') for (a,b) in sorted(pairs,key=lambda k:pairs[k][1]) if directed((a,b)) and label(a,b,cit) and not (ctx(a,b) and ctx(a,b)[0])]
  else:
   items=[(a,b,'abstract') for (a,b) in sorted(pairs,key=lambda k:(pairs[k][1],-pairs[k][0])) if directed((a,b)) and label(a,b,cit) is None]
  label_all(items)

 # ---- eval (always printed) ----
 rows=[(a,b,m,s,rk,json.loads(ans)) for a,b,m,s,rk,ans in db.execute('SELECT a,b,mode,sim,rank,answers FROM runs')]
 tok=spent();print(f'\n== total labelled {len(rows)} | billed input tokens {tok} = ${tok/1e6*PRICE_PER_M:.4f} (avg {tok/max(1,len(rows)):.0f}/pair)')
 ab=[r for r in rows if r[2]=='abstract' and label(r[0],r[1],cit) is not None];lab=[label(r[0],r[1],cit) for r in ab]
 if ab:
  print(f'\n[abstract mode, B-cites-A known] n={len(ab)} positives={sum(lab)}')
  print('AUC  cosine %.3f | Jev related %.3f | max type prob %.3f' % (auc([r[3] for r in ab],lab),auc([r[5]['related']['noul'] for r in ab],lab),auc([max(r[5][t]['noul'] for t in TYPES) for r in ab],lab)))
  for lo,hi in [(0,.3),(.3,.5),(.5,.7),(.7,1.01)]:
   v=[l for r,l in zip(ab,lab) if lo<=r[5]['related']['noul']<hi]
   if v:print(f'  related in [{lo},{hi}): n={len(v):4d}  cite-rate {sum(v)/len(v):.1%}')
 cx=[r for r in rows if r[2]=='context']
 if cx:
  print(f'\n[context mode, citation-backed] n={len(cx)}')
  print('  related>=0.5: %.1f%%' % (100*sum(r[5]['related']['noul']>=.5 for r in cx)/len(cx)))
  for t in TYPES:
   ps=[r[5][t]['noul'] for r in cx];print(f'  {t:10s} >=0.5: {sum(p>=.5 for p in ps)/len(ps):6.1%}   mean {sum(ps)/len(ps):.2f}')
  meta=[(r,ctx(r[0],r[1])) for r in cx];meta=[(r,m) for r,m in meta if m]
  inf=[m[2] for _,m in meta];rel=[r[5]['related']['noul'] for r,_ in meta];print('  AUC related vs S2 isInfluential %.3f (influential %d/%d)' % (auc(rel,inf),sum(inf),len(inf)))
  meth=[int('methodology' in m[1]) for _,m in meta];print('  AUC extends vs S2 intent=methodology %.3f' % auc([r[5]['extends']['noul'] for r,_ in meta],meth))
  print('  inherited:',Counter(r[5]['inherited']['choice'] for r in cx).most_common(),'\n  changed:',Counter(r[5]['changed']['choice'] for r in cx).most_common())

if __name__=='__main__':main()
