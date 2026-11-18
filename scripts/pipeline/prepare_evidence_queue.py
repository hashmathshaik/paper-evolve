"""Resume free source retrieval for Jev-gated candidates. Never calls paid models."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import argparse,fcntl,json,signal,time
from pathlib import Path
import relation_core as H
import evidence_packets as E
import relation_screen as S
from voyage_pipeline import ROOT,atomic_json

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--limit',type=int,default=0);args=ap.parse_args()
 E.WORK.mkdir(parents=True,exist_ok=True);lock=(E.WORK/'queue.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Evidence retrieval is already running.')
 stop=False
 def request_stop(*_):
  nonlocal stop
  stop=True
 signal.signal(signal.SIGTERM,request_stop);signal.signal(signal.SIGINT,request_stop)
 papers,pairs,cites,contexts=H.candidates();ledger=H.Ledger(H.J.E/'relations.sqlite3',5);S.setup(ledger)
 eligible,_=S.eligible(ledger,pairs)
 if args.limit:eligible=eligible[:args.limit]
 records={r['id']:r for r in H.J.read_records('corpus')}
 with H.sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3') as db:alternates=dict(db.execute('SELECT url,endpoint FROM abstracts'))
 counts={'ready':0,'needs_context':0};checked=0;current=None
 def status(phase):
  report={'phase':phase,'total_gated_pairs':len(eligible),'checked':checked,'remaining':len(eligible)-checked,'counts':counts,'current':current,'paid_model_calls':0}
  atomic_json(E.WORK/'queue-status.json',report)
  if checked%25==0 or phase!='running':print(json.dumps(report),flush=True)
 status('running')
 for a,b in eligible:
  if stop:break
  current=[a,b];state=H.make_state(a,b,papers,cites,contexts)
  packet=state.get('source_evidence')
  if not packet:packet=E.build_packet(a,b,state,records,alternates);time.sleep(1)
  counts[packet['status']]+=1;checked+=1;status('running')
 current=None;status('stopped' if stop else 'complete')

if __name__=='__main__':main()
