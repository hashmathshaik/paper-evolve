"""Freeze a reproducible stratified sample for independent assistant evidence review."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import json,random,sqlite3
from pathlib import Path
from voyage_pipeline import ROOT,atomic_json

def main():
 out=ROOT/'work/relation-review';out.mkdir(exist_ok=True)
 source=sqlite3.connect(ROOT/'work/edges/relations.sqlite3');snapshot=sqlite3.connect(out/'snapshot.sqlite3');source.backup(snapshot)
 rows=[{'id':key,'a':a,'b':b,'state':json.loads(st),'prediction':json.loads(r)} for key,a,b,st,r in snapshot.execute("SELECT id,a,b,state,result FROM calls WHERE status='complete'")]
 accepted=[r for r in rows if r['prediction'].get('types')];rejected=[r for r in rows if not r['prediction'].get('types')]
 rng=random.Random(20261113);chosen=[];used=set()
 def pick(pool,n,stratum):
  pool=[r for r in pool if r['id'] not in used]
  for row in rng.sample(pool,min(n,len(pool))):
   used.add(row['id']);chosen.append({**row,'stratum':stratum,'review_id':f'R{len(chosen)+1:02d}'})
 pick(accepted,16,'random_accepted')
 pick([r for r in accepted if 'Challenges' in r['prediction']['types']],4,'targeted_challenges')
 pick([r for r in accepted if 'Transfers' in r['prediction']['types']],4,'targeted_transfers')
 pick(rejected,6,'random_rejected')
 atomic_json(out/'sample.json',chosen)
 atomic_json(out/'sampling.json',{'seed':20261113,'snapshot_complete':len(rows),'snapshot_accepted':len(accepted),'sample_size':len(chosen),'strata':{k:sum(r['stratum']==k for r in chosen) for k in {r['stratum'] for r in chosen}},'note':'Assistant review, not independent human expert ground truth. Random accepted subset and targeted subsets must be reported separately.'})
 print(json.dumps(json.loads((out/'sampling.json').read_text())))

if __name__=='__main__':main()
