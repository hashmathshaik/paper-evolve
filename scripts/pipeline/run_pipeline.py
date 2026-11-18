"""Own and monitor the abstract/download/embedding workers as one resumable run."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import argparse,fcntl,json,signal,sqlite3,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from voyage_pipeline import ROOT,atomic_json

WORK=ROOT/'work/pipeline'
SERVICES={
 'downloads':{'command':['scripts/pipeline/download_collection.py'],'log':'work/full-collection/download.log','status':'work/full-collection/status.json'},
 'openalex':{'command':['scripts/pipeline/recover_openalex.py','--budget-usd','6'],'log':'work/openalex-recovery.log','status':'work/openalex/status.json'},
 'embeddings':{'command':['scripts/pipeline/embedding_queue.py','--refresh-every','10000'],'log':'work/voyage/embedding.log','status':'work/voyage/embedding-status.json'},
}

def read_status(path):
 try:return json.loads(Path(path).read_text())
 except (OSError,ValueError):return {}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--duration-seconds',type=float,help='Bounded supervisor smoke test');args=ap.parse_args()
 WORK.mkdir(parents=True,exist_ok=True);lock=(WORK/'supervisor.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('The pipeline supervisor is already running.')
 stop=False
 def request_stop(*_):
  nonlocal stop
  stop=True
 signal.signal(signal.SIGINT,request_stop);signal.signal(signal.SIGTERM,request_stop)
 corpus=json.loads((ROOT/'evolve/corpus.json').read_text());urls={p['u'] for p in corpus};ids=set()
 from voyage_pipeline import read_records
 ids={p['id'] for p in read_records('corpus')}
 processes={};handles={};restarts={name:0 for name in SERVICES};started=time.monotonic();last_publish=0;retry_due={name:None for name in SERVICES}
 def launch(name):
  spec=SERVICES[name];log=ROOT/spec['log'];log.parent.mkdir(parents=True,exist_ok=True)
  handles[name]=log.open('a');handles[name].write('\n--- supervised resume '+datetime.now(timezone.utc).isoformat()+' ---\n');handles[name].flush()
  processes[name]=subprocess.Popen([sys.executable,'-u',*spec['command']],cwd=ROOT,stdout=handles[name],stderr=subprocess.STDOUT,start_new_session=True)
  print(f'{name}: started worker {processes[name].pid}',flush=True)
 def publish(phase='running'):
  abstract_db=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60)
  available=sum(row[0] in urls for row in abstract_db.execute('SELECT url FROM abstracts'));abstract_db.close()
  embed_db=sqlite3.connect(ROOT/'work/voyage/cache.sqlite3',timeout=60)
  embedded=sum(row[0] in ids for row in embed_db.execute('SELECT DISTINCT paper_id FROM vectors'));embed_db.close()
  workers={}
  for name,process in processes.items():
   details=read_status(ROOT/SERVICES[name]['status'])
   workers[name]={'pid':process.pid,'alive':process.poll() is None,'exit_code':process.poll(),'phase':details.get('phase'),'retry_at':details.get('retry_at'),'restarts':restarts[name]}
  atomic_json(WORK/'status.json',{'phase':phase,'supervisor_pid':__import__('os').getpid(),'abstracts_downloaded':available,'embeddings_cached':embedded,'total_papers':len(corpus),'workers':workers,'updated_at':datetime.now(timezone.utc).isoformat()})
 try:
  for name in SERVICES:launch(name)
  while not stop:
   if args.duration_seconds and time.monotonic()-started>=args.duration_seconds:break
   for name,process in list(processes.items()):
    code=process.poll()
    if code is None:continue
    # Budget/provider/input stops are terminal for that run, never silently restarted.
    if code==0:continue
    if restarts[name]>=3:continue
    if retry_due[name] is None:retry_due[name]=time.monotonic()+30
    if time.monotonic()<retry_due[name]:continue
    handles[name].close();restarts[name]+=1;retry_due[name]=None;launch(name)
   if time.monotonic()-last_publish>=15:publish();last_publish=time.monotonic()
   if all(p.poll() is not None for p in processes.values()):break
   time.sleep(1)
 finally:
  publish('stopping')
  for process in processes.values():
   if process.poll() is None:process.terminate()
  deadline=time.monotonic()+65
  for process in processes.values():
   try:process.wait(timeout=max(1,deadline-time.monotonic()))
   except subprocess.TimeoutExpired:process.kill();process.wait()
  for handle in handles.values():handle.close()
  publish('stopped' if stop or args.duration_seconds else 'finished')

if __name__=='__main__':main()
