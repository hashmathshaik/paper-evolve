"""Continuous local embedding queue. Refresh at 10k arrivals and whenever caught up."""
from collections import deque
import argparse
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import fcntl,json,signal,sqlite3,time
from pathlib import Path
from urllib import error
from voyage_pipeline import ROOT,Cache,read_records,load_config,load_api_key,atomic_json,token_bound,cache_key,batches,http_embed,validate_response,digest

WORK=ROOT/'work/voyage'

def should_refresh(available,admitted,pending,threshold=10000):
 return available-admitted>=threshold or (pending==0 and available>admitted)

def delay_seconds(header,default=60):
 try:return max(1,float(header))
 except (ValueError,TypeError):
  try:return max(1,parsedate_to_datetime(header).timestamp()-time.time())
  except (ValueError,TypeError,OverflowError):return default

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--refresh-every',type=int,default=10000);ap.add_argument('--batch-tokens',type=int,default=60000);ap.add_argument('--batch-papers',type=int,default=128);ap.add_argument('--interval',type=float,default=0.5);ap.add_argument('--tpm',type=int,default=1000000);args=ap.parse_args()
 if args.refresh_every<1:ap.error('Refresh size must be positive.')
 WORK.mkdir(parents=True,exist_ok=True);lock=(WORK/'embedding.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Another embedding worker holds the queue lock.')
 stopped=False
 def stop(*_):
  nonlocal stopped
  stopped=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 config=load_config(ROOT/'config/voyage.json');config['budget_usd']=min(config['budget_usd'],14)
 # Batches sized in estimated real tokens (bytes * learned tokens-per-byte). On 429: halve batch, double interval;
 # regrow after 5 successes. Free tier (no payment method) needs --batch-tokens 3000 --batch-papers 32 --interval 21 --tpm 9000.
 minimum_interval=args.interval;token_window=deque();token_capacity=args.tpm;batch_target=args.batch_tokens;tokens_per_byte=0.25;success_streak=0
 key=load_api_key()
 if not key:raise ValueError('VOYAGE_API_KEY missing locally.')
 cache=Cache(WORK/'cache.sqlite3');cache.db.execute('PRAGMA busy_timeout=60000')
 source=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60)
 corpus=read_records('corpus');by_url={r['source_url']:r for r in corpus}
 source.execute('CREATE TEMP TABLE corpus_urls(url TEXT PRIMARY KEY)');source.executemany('INSERT OR IGNORE INTO corpus_urls VALUES (?)',[(u,) for u in by_url]);source.commit()
 records={};cached_keys={r[0] for r in cache.db.execute('SELECT key FROM vectors')};bad={};pending=[];admitted=0;last_refresh=None;last_available=0;last_request=0;phase='starting';retry_at=None;last_error=None;completed_this_run=0
 def available_count():return source.execute('SELECT COUNT(*) FROM abstracts INNER JOIN corpus_urls USING(url)').fetchone()[0]
 def record_from(row):
  url,text,date,endpoint=row;p=by_url[url];joined=p['title'].strip()+'\n\nAbstract:\n'+text.strip()
  return {'id':p['id'],'title':p['title'],'source_url':url,'year':p['year'],'text':joined,'text_hash':digest(joined),'quality':'title_abstract','abstract':text,'abstract_retrieved_at':date,'abstract_source_url':endpoint}
 def refresh():
  nonlocal admitted,pending,last_refresh,last_available
  for row in source.execute('SELECT url,abstract,retrieved_at,endpoint FROM abstracts INNER JOIN corpus_urls USING(url)'):
   r=record_from(row)
   if token_bound(r['text'])>config['max_document_token_bound']:bad[r['id']]='abstract_exceeds_conservative_input_bound';continue
   records[r['id']]=r
  admitted=available_count();last_available=admitted;last_refresh=datetime.now(timezone.utc).isoformat()
  pending=[r for r in records.values() if cache_key(r,config) not in cached_keys]
  # Public-research inputs only, stored locally. Atomic snapshot remains CLI compatible.
  path=WORK/'downloaded-abstracts.jsonl';tmp=path.with_suffix('.tmp')
  with tmp.open('w') as stream:
   for r in records.values():stream.write(json.dumps({k:r[k] for k in ['id','title','source_url','year','abstract','abstract_retrieved_at','abstract_source_url']},ensure_ascii=False)+'\n')
  tmp.replace(path);atomic_json(WORK/'oversized.json',bad)
  print(f'Queue refreshed: {len(records)} admitted papers; {len(pending)} pending; {len(bad)} require input review.',flush=True)
 def status():
  value={'phase':phase,'snapshot_papers':len(records),'embedded_in_snapshot':len(records)-len(pending),'remaining':len(pending),'downloaded_abstracts':last_available,'waiting_to_admit':max(0,last_available-admitted),'refresh_every':args.refresh_every,'last_refresh_at':last_refresh,'oversized_skipped':len(bad),'completed_this_run':completed_this_run,'model':config['model'],'dimensions':config['output_dimension'],'reserved_cost_all_jobs_usd':round(cache.spent_bound(),6),'reported_successful_tokens_all_jobs':cache.db.execute('SELECT COALESCE(SUM(actual_tokens),0) FROM attempts WHERE status="completed"').fetchone()[0],'embedding_budget_usd':config['budget_usd'],'retry_at':retry_at,'last_error':last_error,'minimum_request_interval_seconds':round(minimum_interval,1),'local_token_capacity_per_minute':token_capacity,'batch_token_target':batch_target,'batch_papers':len(pending[:1]) and len(take_batch()[0]),'updated_at':datetime.now(timezone.utc).isoformat()}
  atomic_json(WORK/'embedding-status.json',value)
 def take_batch():
  out,est=[],0
  for r in pending:
   t=token_bound(r['text'])*tokens_per_byte
   if out and (est+t>batch_target or len(out)>=args.batch_papers):break
   out.append(r);est+=t
  return out,est
 def wait(seconds):
  deadline=time.monotonic()+seconds
  while not stopped and time.monotonic()<deadline:time.sleep(min(5,max(0,deadline-time.monotonic())))
 refresh();status();network_failures=0
 while not stopped:
  last_available=available_count()
  if should_refresh(last_available,admitted,len(pending),args.refresh_every):refresh()
  if not pending:
   phase='caught_up_waiting_for_downloads';retry_at=None;status();wait(30);continue
  batch,estimated_batch_tokens=take_batch()
  while token_window and time.monotonic()-token_window[0][0]>=60:token_window.popleft()
  token_wait=max(0,60-(time.monotonic()-token_window[0][0])) if token_window and sum(t for _,t in token_window)+estimated_batch_tokens>token_capacity else 0
  wait(max(token_wait,minimum_interval-(time.monotonic()-last_request)))
  if stopped:break
  payload={'input':[r['text'] for r in batch],'model':config['model'],'output_dimension':config['output_dimension'],'input_type':config['input_type'],'output_dtype':'float','truncation':False}
  amount=sum(token_bound(r['text']) for r in batch)/1e6*config['price_per_million_tokens']
  try:attempt=cache.reserve(amount,config['budget_usd'])
  except ValueError:phase='stopped_budget_limit';status();return
  phase='embedding';retry_at=None;status();last_request=time.monotonic()
  try:
   result=http_embed(payload,key);vectors=validate_response(result,len(batch),config['output_dimension']);usage=result.get('usage',{}).get('total_tokens')
   cache.save(batch,vectors,config);cache.finish(attempt,'completed',usage);cached_keys.update(cache_key(r,config) for r in batch);pending=pending[len(batch):];completed_this_run+=len(batch);token_window.append((time.monotonic(),usage or estimated_batch_tokens))
   if usage:tokens_per_byte=0.8*tokens_per_byte+0.2*usage/sum(token_bound(r['text']) for r in batch)
   success_streak+=1
   if success_streak>=5:batch_target=min(args.batch_tokens,int(batch_target*1.25));minimum_interval=max(args.interval,minimum_interval/1.5);success_streak=0
   network_failures=0;last_error=None;status()
   print(f'Embedded {len(records)-len(pending)}/{len(records)} admitted papers.',flush=True)
  except error.HTTPError as exc:
   cache.finish(attempt,'http_'+str(exc.code));last_error='http_'+str(exc.code)
   if exc.code in [429,500,502,503,504]:
    if exc.code==429:batch_target=max(400,batch_target//2);minimum_interval=min(30,minimum_interval*2);success_streak=0
    seconds=delay_seconds(exc.headers.get('Retry-After'),60 if exc.code==429 else 30)
    phase='waiting_for_voyage';retry_at=datetime.fromtimestamp(time.time()+seconds,timezone.utc).isoformat();status();print(f'Provider HTTP {exc.code}; waiting {round(seconds)} seconds before retrying the same batch.',flush=True);wait(seconds);continue
   phase='stopped_provider_error';status();return
  except (error.URLError,TimeoutError,OSError):
   cache.finish(attempt,'network_uncertain');network_failures+=1;last_error='network_error';phase='waiting_for_network';status()
   if network_failures>=5:phase='stopped_network_error';status();return
   wait(min(60,2**network_failures))
  except (ValueError,TypeError,KeyError):
   cache.finish(attempt,'invalid_response');phase='stopped_invalid_response';status();return
 phase='stopped_cleanly';retry_at=None;status()

if __name__=='__main__':main()
