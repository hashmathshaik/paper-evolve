"""Fetch citing sentences + intents + isInfluential for citation-backed candidate pairs (Semantic Scholar, keyless).
One call per citing paper B: /paper/{B}/references?fields=paperId,contexts,intents,isInfluential.
Order: citing papers of the highest-similarity pairs first. Resumable; writes work/edges/s2.sqlite3:contexts.
"""
import json,sqlite3,sys,time
from pathlib import Path
from urllib import request,error
sys.path.insert(0,str(Path(__file__).parent))
import edges_jev as J

API='https://api.semanticscholar.org/graph/v1';UA='PaperEvolve/0.1 (citation contexts for research)'

def get(url):
 for attempt in range(10):
  try:
   with request.urlopen(request.Request(url,headers={'User-Agent':UA}),timeout=90) as r:data=json.load(r)
   time.sleep(1.1);return data
  except error.HTTPError as exc:
   if exc.code==404:return {'data':[]}
   if exc.code in [429,500,502,503,504]:time.sleep(min(90,3*2**attempt));continue
   raise
  except (error.URLError,TimeoutError,OSError):time.sleep(min(90,5*2**attempt))
 raise RuntimeError('Semantic Scholar unavailable; rerun to resume.')

def main():
 db=sqlite3.connect(J.E/'s2.sqlite3',timeout=120)
 db.execute('CREATE TABLE IF NOT EXISTS contexts(citing TEXT,cited TEXT,contexts TEXT,intents TEXT,influential INTEGER,PRIMARY KEY(citing,cited))')
 db.execute('CREATE TABLE IF NOT EXISTS contexts_done(citing TEXT PRIMARY KEY)');db.commit()
 P=J.papers();pairs=J.candidate_pairs(P);cit=J.cites();s2=cit[0]
 best={}
 for (a,b),(s,rank) in pairs.items():
  if J.label(a,b,cit) and s2.get(b):best[s2[b]]=max(best.get(s2[b],0),s)
 done={r[0] for r in db.execute('SELECT citing FROM contexts_done')}
 todo=[c for c,_ in sorted(best.items(),key=lambda x:-x[1]) if c not in done];print('citing papers',len(best),'to fetch',len(todo),flush=True)
 t=time.time()
 for n,c in enumerate(todo,1):
  rows=[];offset=0
  while True:
   d=get(f'{API}/paper/{c}/references?fields=paperId,contexts,intents,isInfluential&limit=1000&offset={offset}')
   for r in d.get('data') or []:  # S2 returns data:null when a publisher elides references
    pid=(r.get('citedPaper') or {}).get('paperId')
    if pid:rows.append((c,pid,json.dumps(r.get('contexts') or []),json.dumps(r.get('intents') or []),int(bool(r.get('isInfluential')))))
   if d.get('next') is None:break
   offset=d['next']
  db.executemany('INSERT OR REPLACE INTO contexts VALUES (?,?,?,?,?)',rows);db.execute('INSERT OR IGNORE INTO contexts_done VALUES (?)',(c,));db.commit()
  if n%200==0:print(f'{n}/{len(todo)} citing papers, {time.time()-t:.0f}s',flush=True)
 print('done',flush=True)

if __name__=='__main__':main()
