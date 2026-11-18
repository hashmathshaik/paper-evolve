"""Download all corpus abstracts. No paid API calls. Resume with the same command."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed,wait,FIRST_COMPLETED
from datetime import datetime,timezone
import fcntl
import json
from pathlib import Path
import sqlite3
import threading,signal
import time
from urllib import request,parse,error
import xml.etree.ElementTree as ET
from fetch_abstracts import fetch
from voyage_pipeline import ROOT,read_records,atomic_json

WORK=ROOT/'work/full-collection'
STOP=threading.Event()
UA='PaperEvolve/0.1 (public scientific metadata; resumable local research collection)'

def now():return datetime.now(timezone.utc).isoformat()

def acl_collection(url):
 slug=parse.urlparse(url).path.strip('/')
 return slug.split('-')[0]

def parse_acl(raw):
 root=ET.fromstring(raw);collection=root.get('id');out={}
 for volume in root.findall('volume'):
  for paper in volume.findall('paper'):
   n=paper.get('id');v=volume.get('id')
   slug=f'{collection}-{int(v)*1000+int(n):04d}' if collection[0].isalpha() else f'{collection}-{v}.{n}'
   abstract=paper.find('abstract')
   if abstract is not None:
    text=' '.join(''.join(abstract.itertext()).split())
    if len(text)>=40:out['https://aclanthology.org/'+slug+'/']=text
 return out

def get(url):
 req=request.Request(url,headers={'User-Agent':UA})
 with request.urlopen(req,timeout=45) as response:return response.read()

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--workers',type=int,default=6);ap.add_argument('--delay',type=float,default=.75);ap.add_argument('--limit',type=int);args=ap.parse_args()
 if not 1<=args.workers<=12 or args.delay<.5:ap.error('Use 1–12 workers and at least .5 seconds between requests per origin.')
 WORK.mkdir(parents=True,exist_ok=True)
 signal.signal(signal.SIGTERM,lambda *_:STOP.set());signal.signal(signal.SIGINT,lambda *_:STOP.set())
 lock=(WORK/'download.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Another full-collection download is already running.')
 records=read_records('corpus',limit=args.limit)
 cache_path=ROOT/'work/abstracts/cache.sqlite3';cache_path.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(cache_path,timeout=60)
 db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA busy_timeout=60000')
 db.execute('CREATE TABLE IF NOT EXISTS abstracts(url TEXT PRIMARY KEY,abstract TEXT,retrieved_at TEXT,endpoint TEXT)')
 db.execute('CREATE TABLE IF NOT EXISTS failures(url TEXT PRIMARY KEY,reason TEXT,checked_at TEXT)');db.commit()
 lookup={r['source_url']:r for r in records};started=time.monotonic();phase='bulk_acl'
 def saved_urls():return {row[0] for row in db.execute('SELECT url FROM abstracts')}
 def export():
  temp=WORK/'papers.jsonl.tmp';count=0
  with temp.open('w') as stream:
   for url,text,date,endpoint in db.execute('SELECT url,abstract,retrieved_at,endpoint FROM abstracts ORDER BY url'):
    if url not in lookup:continue
    r=lookup[url];row={k:r[k] for k in ['id','title','source_url','year']};row.update(abstract=text,abstract_source_url=endpoint,abstract_retrieved_at=date)
    stream.write(json.dumps(row,ensure_ascii=False)+'\n');count+=1
  temp.replace(WORK/'papers.jsonl');return count
 def status(emit=True):
  have=saved_urls();fail={url:reason for url,reason in db.execute('SELECT url,reason FROM failures') if url in lookup and url not in have}
  venues={}
  for r in records:
   venue=parse.urlparse(r['source_url']).hostname;v=venues.setdefault(venue,{'total':0,'available':0,'failed':0});v['total']+=1;v['available']+=r['source_url'] in have;v['failed']+=r['source_url'] in fail
  result={'phase':phase,'total':len(records),'available':len(have&lookup.keys()),'failed':len(fail),'remaining':len(lookup.keys()-have-fail.keys()),'elapsed_seconds':round(time.monotonic()-started),'updated_at':now(),'sources':venues,'paid_api_calls':0}
  atomic_json(WORK/'status.json',result)
  if emit:print(json.dumps({k:v for k,v in result.items() if k!='sources'}),flush=True)
  return result
 have=saved_urls();collections=sorted({acl_collection(r['source_url']) for r in records if 'aclanthology.org' in r['source_url'] and r['source_url'] not in have})
 for collection in collections:
  if STOP.is_set():break
  path=WORK/'raw'/f'{collection}.xml';path.parent.mkdir(exist_ok=True)
  endpoint='https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/'+collection+'.xml'
  try:
   if not path.exists():path.write_bytes(get(endpoint));time.sleep(.25)
   abstracts=parse_acl(path.read_bytes());date=now()
   db.executemany('INSERT OR REPLACE INTO abstracts VALUES (?,?,?,?)',[(url,text,date,endpoint) for url,text in abstracts.items() if url in lookup]);db.commit()
  except Exception as exc:print(f'Bulk source {collection}: {type(exc).__name__}',flush=True)
  status()
 export()
 # OpenReview supports bulk note retrieval. Match by note ID, never by title similarity.
 phase='bulk_openreview';have=saved_urls();openrecords=[r for r in records if 'openreview.net' in r['source_url'] and r['source_url'] not in have]
 review_lookup={parse.parse_qs(parse.urlparse(r['source_url']).query).get('id',[''])[0]:r['source_url'] for r in openrecords};review_blocked=False
 for year in sorted({r['year'] for r in openrecords}):
  if STOP.is_set():break
  base='https://api.openreview.net' if year<=2023 else 'https://api2.openreview.net'
  query={'invitation':f'ICLR.cc/{year}/Conference/-/Blind_Submission'} if year<=2023 else {'content.venueid':f'ICLR.cc/{year}/Conference'}
  offset=0
  while not STOP.is_set():
   endpoint=base+'/notes?'+parse.urlencode({**query,'limit':1000,'offset':offset})
   try:data=json.loads(get(endpoint))
   except Exception as exc:
    print(f'OpenReview {year}: {type(exc).__name__}',flush=True)
    if getattr(exc,'code',None)==403:review_blocked=True
    break
   notes=data.get('notes',[]);date=now()
   for note in notes:
    url=review_lookup.get(note.get('id'));abstract=note.get('content',{}).get('abstract','')
    if isinstance(abstract,dict):abstract=abstract.get('value','')
    if url and isinstance(abstract,str) and len(abstract)>=40:db.execute('INSERT OR REPLACE INTO abstracts VALUES (?,?,?,?)',(url,' '.join(abstract.split()),date,endpoint))
   db.commit();status()
   if len(notes)<1000:break
   offset+=1000;time.sleep(args.delay)
  if review_blocked:break
 if review_blocked:
  have=saved_urls();db.executemany('INSERT OR REPLACE INTO failures VALUES (?,?,?)',[(r['source_url'],'Official OpenReview API returned HTTP 403',now()) for r in openrecords if r['source_url'] not in have]);db.commit()
 export();phase='paper_pages';have=saved_urls()
 pending=[r for r in records if r['source_url'] not in have and not(review_blocked and 'openreview.net' in r['source_url'])]
 # Round-robin source origins to make use of parallelism without hammering one server.
 groups={}
 for r in pending:groups.setdefault(parse.urlparse(r['source_url']).hostname,[]).append(r)
 pending=[g[i] for i in range(max((len(g) for g in groups.values()),default=0)) for g in groups.values() if i<len(g)]
 locks={};last={};guard=threading.Lock();blocked=set()
 def retrieve(r):
  if STOP.is_set():return r,None,None,'cancelled'
  host=parse.urlparse(r['source_url']).hostname
  with guard:host_lock=locks.setdefault(host,threading.Lock())
  with host_lock:
   if STOP.is_set():return r,None,None,'cancelled'
   if host in blocked:return r,None,None,'Source HTTP 403; requests stopped for this origin'
   for attempt in range(3):
    STOP.wait(max(0,args.delay-(time.monotonic()-last.get(host,0))));last[host]=time.monotonic()
    if STOP.is_set():return r,None,None,'cancelled'
    try:
     text,endpoint=fetch(r['source_url']);return r,text,endpoint,None
    except Exception as exc:
     if STOP.is_set():return r,None,None,'cancelled'
     code=getattr(exc,'code',None)
     if code==403:blocked.add(host)
     if code in [429,500,502,503,504] and attempt<2:time.sleep(2**(attempt+1));continue
     return r,None,None,f'{type(exc).__name__}: {str(exc)[:130]}'
 status()
 with ThreadPoolExecutor(max_workers=args.workers) as pool:
  iterator=iter(pending);active=set();processed=0
  def submit_next():
   if STOP.is_set():return
   try:active.add(pool.submit(retrieve,next(iterator)))
   except StopIteration:pass
  for _ in range(args.workers):submit_next()
  while active:
   if STOP.is_set():
    for future in active:future.cancel()
    active={future for future in active if not future.cancelled()}
    if not active:break
   ready,_=wait(active,timeout=1,return_when=FIRST_COMPLETED)
   for future in ready:
    active.remove(future)
    if future.cancelled():continue
    r,text,endpoint,reason=future.result();date=now()
    if reason!='cancelled':
     if text:db.execute('INSERT OR REPLACE INTO abstracts VALUES (?,?,?,?)',(r['source_url'],text,date,endpoint));db.execute('DELETE FROM failures WHERE url=?',(r['source_url'],))
     else:db.execute('INSERT OR REPLACE INTO failures VALUES (?,?,?)',(r['source_url'],reason,date))
     db.commit();processed+=1
     if processed%25==0:status()
     if processed%500==0:export()
    submit_next()
 export();phase='stopped_cleanly' if STOP.is_set() else 'complete';report=status();have=saved_urls();atomic_json(WORK/'missing.json',[{'id':r['id'],'source_url':r['source_url']} for r in records if r['source_url'] not in have]);db.close()
 print(f"Download {phase}: {report['available']}/{len(records)} abstracts. See status.json and missing.json.",flush=True)

if __name__=='__main__':main()
