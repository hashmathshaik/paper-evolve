"""Recover missing ICLR abstracts with conservative OpenAlex identity checks.
Credentials never enter request logs, cache keys, or public output.
"""
import signal
import argparse,base64,fcntl,gzip,json,os,re,sqlite3,time,unicodedata
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib import request,parse,error
from voyage_pipeline import ROOT,read_records,atomic_json,digest

WORK=ROOT/'work/openalex'
FIELDS='id,title,publication_year,abstract_inverted_index,locations,authorships'

def normalize(s):
 return ''.join(c for c in unicodedata.normalize('NFKD',s).casefold() if c.isalnum())

def unpack_abstract(index):
 if not isinstance(index,dict) or not index:return None
 tokens={}
 for word,positions in index.items():
  if not isinstance(word,str) or not isinstance(positions,list):return None
  for n in positions:
   if not isinstance(n,int) or n<0 or n>50000 or n in tokens:return None
   tokens[n]=word
 if not tokens or set(tokens)!=set(range(max(tokens)+1)):return None
 text=' '.join(tokens[i] for i in range(len(tokens)))
 return text if len(text)>=40 else None

def note_id(url):
 p=parse.urlparse(url)
 return parse.parse_qs(p.query).get('id',[None])[0] if p.hostname in ['openreview.net','www.openreview.net'] else None

def match_record(record,works,authors):
 exact=[];fallback=[]
 for work in works:
  text=unpack_abstract(work.get('abstract_inverted_index'))
  if not text:continue
  locations=work.get('locations') or []
  if any(note_id(loc.get('landing_page_url') or '')==note_id(record['source_url']) and note_id(record['source_url']) for loc in locations):
   exact.append((work,text,'exact_openreview_id'));continue
  if normalize(work.get('title',''))!=normalize(record['title']):continue
  if not isinstance(work.get('publication_year'),int) or abs(work['publication_year']-record['year'])>1:continue
  expected={normalize(a) for a in authors.split(',') if a.strip()}
  observed={normalize(a.get('author',{}).get('display_name','')) for a in work.get('authorships',[])}
  if expected&observed:fallback.append((work,text,'exact_title_year_author'))
 matches=exact or fallback
 unique={w['id']:(w,text,method) for w,text,method in matches}
 if len(unique)==1:return next(iter(unique.values())),None
 return None,'ambiguous' if unique else 'no_verified_match'

def load_key():
 if os.environ.get('OPENALEX_API_KEY'):return os.environ['OPENALEX_API_KEY'].strip()
 for line in (ROOT/'.env').read_text().splitlines():
  name,sep,value=line.strip().removeprefix('export ').partition('=')
  if sep and name.strip()=='OPENALEX_API_KEY':return value.strip().strip('\"\x27')
 raise ValueError('OPENALEX_API_KEY is not configured.')

def retry_seconds(header,attempt=1,current_time=None):
 current_time=time.time() if current_time is None else current_time
 if header:
  try:return max(1,float(header))
  except (ValueError,TypeError):
   try:return max(1,parsedate_to_datetime(header).timestamp()-current_time)
   except (ValueError,TypeError,OverflowError):pass
 return min(300,30*(2**min(attempt-1,4)))


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--budget-usd',type=float,default=6.0);ap.add_argument('--limit',type=int);args=ap.parse_args()
 if not 0<args.budget_usd<=20:ap.error('Recovery must stay within the authorized $20 ceiling.')
 WORK.mkdir(parents=True,exist_ok=True);lock=(WORK/'recovery.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('OpenAlex recovery is already running.')
 stopped=False
 def stop(*_):
  nonlocal stopped
  stopped=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 key=load_key();cache=sqlite3.connect(WORK/'cache.sqlite3')
 cache.execute('CREATE TABLE IF NOT EXISTS queries(id TEXT PRIMARY KEY,response TEXT)');cache.execute('CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,amount REAL,status TEXT)');cache.execute('CREATE TABLE IF NOT EXISTS matches(paper_id TEXT PRIMARY KEY,work_id TEXT,method TEXT,status TEXT)');cache.commit()
 abstracts=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60)
 rows=[r for r in read_records('corpus') if note_id(r['source_url'])]
 if args.limit:rows=rows[:args.limit]
 atlas=(ROOT/'atlas.html').read_text();m=re.search(r'const hoverDataEncoded = "([^"]+)"',atlas);metadata=json.loads(gzip.decompress(base64.b64decode(m[1])))
 authors=dict(zip(metadata['url'],metadata['authors']));del atlas,metadata
 have={row[0] for row in abstracts.execute('SELECT url FROM abstracts')};done={row[0] for row in cache.execute('SELECT paper_id FROM matches')}
 pending=[r for r in rows if r['source_url'] not in have and r['id'] not in done];initial=len(have & {r['source_url'] for r in rows});added=0;checked=0;phase='running';retry_at=None
 def status():
  report={'phase':phase,'iclr_total':len(rows),'initial_available':initial,'recovered_this_run':added,'checked_this_run':checked,'remaining_queries_papers':max(0,len(pending)-checked),'reserved_usage_usd':round(cache.execute('SELECT COALESCE(SUM(amount),0) FROM attempts').fetchone()[0],6),'budget_usd':args.budget_usd,'retry_at':retry_at,'updated_at':datetime.now(timezone.utc).isoformat()}
  atomic_json(WORK/'status.json',report);print(json.dumps(report),flush=True)
 def wait_and_resume(seconds):
  nonlocal phase,retry_at
  phase='waiting_for_openalex';retry_at=datetime.fromtimestamp(time.time()+seconds,timezone.utc).isoformat();status()
  deadline=time.monotonic()+seconds
  while not stopped and time.monotonic()<deadline:time.sleep(min(5,max(0,deadline-time.monotonic())))
  if stopped:raise RuntimeError('operator_stopped')
  phase='running';retry_at=None;status()
 def query(titles):
  q={'search.title':' OR '.join('"'+t.replace('"',' ')+'"' for t in titles),'per_page':100,'select':FIELDS};identity=digest(q)
  saved=cache.execute('SELECT response FROM queries WHERE id=?',(identity,)).fetchone()
  if saved:return json.loads(saved[0])
  transient=0;rate_retries=0
  while True:
   if stopped:raise RuntimeError('operator_stopped')
   spent=cache.execute('SELECT COALESCE(SUM(amount),0) FROM attempts').fetchone()[0]
   if spent+.001>args.budget_usd+1e-10:raise RuntimeError('local_usage_cap')
   cursor=cache.execute('INSERT INTO attempts(amount,status) VALUES (?,?)',(.001,'reserved'));cache.commit();attempt_id=cursor.lastrowid
   try:
    url='https://api.openalex.org/works?'+parse.urlencode({**q,'api_key':key})
    with request.urlopen(request.Request(url,headers={'User-Agent':'PaperEvolve/0.1 (abstract recovery)'}),timeout=45) as response:data=json.load(response)
    actual=data.get('meta',{}).get('cost_usd',.001)
    cache.execute('UPDATE attempts SET amount=?,status=? WHERE id=?',(max(.001,float(actual)),'completed',attempt_id));cache.execute('INSERT OR REPLACE INTO queries VALUES (?,?)',(identity,json.dumps(data)));cache.commit();time.sleep(.3);return data
   except error.HTTPError as exc:
    cache.execute('UPDATE attempts SET status=? WHERE id=?',('http_'+str(exc.code),attempt_id));cache.commit()
    if exc.code==429:
     # OpenAlex documents rate-limit waits as uncharged. Keep the attempt for audit.
     cache.execute('UPDATE attempts SET amount=0 WHERE id=?',(attempt_id,));cache.commit()
     rate_retries+=1;wait_and_resume(retry_seconds(exc.headers.get('Retry-After'),rate_retries));continue
    transient+=1
    if exc.code in [400,500,502,503,504] and transient<5:wait_and_resume(min(60,2**transient));continue
    raise RuntimeError('openalex_http_'+str(exc.code)) from None
   except (error.URLError,TimeoutError):
    transient+=1
    if transient>=5:raise RuntimeError('network_error') from None
    wait_and_resume(min(60,2**transient))

 status()
 try:
  for offset in range(0,len(pending),3):
   batch=pending[offset:offset+3]
   try:works=query([r['title'] for r in batch]).get('results',[])
   except RuntimeError as exc:
    # A transient/odd 400 on one batch should not end the whole run; skip it and record why.
    if str(exc)!='openalex_http_400':raise
    for r in batch:cache.execute('INSERT OR REPLACE INTO matches VALUES (?,?,?,?)',(r['id'],None,None,'query_rejected_400'))
    cache.commit();checked+=len(batch);continue
   for r in batch:
    match,reason=match_record(r,works,authors.get(r['source_url'],''));checked+=1
    if match:
     work,text,method=match;date=datetime.now(timezone.utc).isoformat()
     abstracts.execute('INSERT OR IGNORE INTO abstracts VALUES (?,?,?,?)',(r['source_url'],text,date,work['id']));abstracts.execute('DELETE FROM failures WHERE url=?',(r['source_url'],));abstracts.commit()
     cache.execute('INSERT OR REPLACE INTO matches VALUES (?,?,?,?)',(r['id'],work['id'],method,'matched'));added+=1
    else:cache.execute('INSERT OR REPLACE INTO matches VALUES (?,?,?,?)',(r['id'],None,None,reason))
   cache.commit()
   if checked%30==0:status()
  phase='complete'
 except RuntimeError as exc:
  phase='paused_'+str(exc)
 finally:
  # Snapshot includes only ICLR abstracts accepted through the identity checks.
  temp=WORK/'iclr.jsonl.tmp'
  with temp.open('w') as f:
   for r in rows:
    saved=abstracts.execute('SELECT abstract,retrieved_at,endpoint FROM abstracts WHERE url=?',(r['source_url'],)).fetchone()
    if saved:
     text,date,endpoint=saved;record={k:r[k] for k in ['id','title','source_url','year']};record.update(abstract=text,abstract_retrieved_at=date,abstract_source_url=endpoint);f.write(json.dumps(record,ensure_ascii=False)+'\n')
  temp.replace(WORK/'iclr.jsonl');status();abstracts.close();cache.close()

if __name__=='__main__':main()
