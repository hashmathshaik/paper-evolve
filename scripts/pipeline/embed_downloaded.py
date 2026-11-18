"""Snapshot downloaded abstracts and embed them locally via Voyage. Resumable."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import argparse,fcntl,json,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from voyage_pipeline import ROOT,Cache,read_records,load_config,load_api_key,plan,run_embeddings,atomic_json,token_bound,cache_key

WORK=ROOT/'work/voyage'

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--resume',action='store_true');ap.add_argument('--estimate-only',action='store_true');args=ap.parse_args()
 WORK.mkdir(parents=True,exist_ok=True);lock=(WORK/'embedding.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('An embedding snapshot job is already running.')
 snapshot=WORK/'downloaded-abstracts.jsonl';config=load_config(ROOT/'config/voyage.json')
 # Reserve room for the separately capped $6 OpenAlex recovery pass.
 config['budget_usd']=min(config['budget_usd'],14.0)
 if not args.resume or not snapshot.exists():
  corpus=read_records('corpus');source=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60)
  abstract_rows={url:(text,date,endpoint) for url,text,date,endpoint in source.execute('SELECT url,abstract,retrieved_at,endpoint FROM abstracts')};source.close()
  temporary=snapshot.with_suffix('.tmp');count=0
  with temporary.open('w') as output:
   for paper in corpus:
    saved=abstract_rows.get(paper['source_url'])
    if not saved:continue
    text,date,endpoint=saved;row={k:paper[k] for k in ['id','title','source_url','year']};row.update(abstract=text,abstract_retrieved_at=date,abstract_source_url=endpoint)
    output.write(json.dumps(row,ensure_ascii=False)+'\n');count+=1
  temporary.replace(snapshot)
 records=read_records('corpus',snapshot);cache=Cache(WORK/'cache.sqlite3');report=plan(records,config,cache)
 print(json.dumps(report,indent=2),flush=True);atomic_json(WORK/'snapshot-plan.json',report)
 oversized=[r['id'] for r in records if token_bound(r['text'])>config['max_document_token_bound']]
 if oversized:
  atomic_json(WORK/'oversized.json',oversized);raise ValueError('Some abstracts exceed the conservative input bound; review oversized.json before sending.')
 snapshot_keys={cache_key(r,config) for r in records}
 cached_keys={row[0] for row in cache.db.execute('SELECT key FROM vectors')}
 def status(phase,retry_at=None):
  # Match exact text hashes/model settings, not merely the existence of a paper ID.
  cached=len(snapshot_keys & cached_keys)
  total_tokens=cache.db.execute('SELECT COALESCE(SUM(actual_tokens),0) FROM attempts WHERE status="completed"').fetchone()[0]
  value={'phase':phase,'snapshot_papers':len(records),'embedded_in_snapshot':cached,'remaining':len(records)-cached,'model':config['model'],'dimensions':config['output_dimension'],'reported_successful_tokens_all_jobs':total_tokens,'reserved_cost_all_jobs_usd':round(cache.spent_bound(),6),'embedding_budget_usd':config['budget_usd'],'retry_at':retry_at,'updated_at':datetime.now(timezone.utc).isoformat()}
  atomic_json(WORK/'embedding-status.json',value);return value
 status('estimated' if args.estimate_only else 'starting')
 if args.estimate_only:return
 key=load_api_key()
 if not key:raise ValueError('VOYAGE_API_KEY is not configured locally.')
 # Capture progress after each validated response without persisting any credentials.
 from voyage_pipeline import http_embed
 def transport(payload,key):return http_embed(payload,key)
 original_save=cache.save
 def save(batch,vectors,cfg):
  original_save(batch,vectors,cfg)
  cached_keys.update(cache_key(r,cfg) for r in batch)
  status('embedding')
 cache.save=save
 while True:
  try:
   run_embeddings(records,config,cache,key,transport)
   status('complete');print('Embedding snapshot complete.',flush=True);return
  except ValueError as exc:
   if 'HTTP 429' not in str(exc):status('stopped_error');raise
   retry=time.time()+60;status('waiting_for_voyage',datetime.fromtimestamp(retry,timezone.utc).isoformat())
   print('Voyage throttled requests. Retrying cached job in 60 seconds.',flush=True)
   while time.time()<retry:time.sleep(min(20,max(0,retry-time.time())))

if __name__=='__main__':main()
