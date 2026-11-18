"""Fill reference lists from OpenAlex where Semantic Scholar returned none (publisher-elided references).
1) S2 batch externalIds (free) -> DOI, else arXiv DOI 10.48550/arxiv.<id>; ACL papers also get their Anthology DOI.
2) OpenAlex /works?filter=doi:d1|...|d50 (list+filter ~$0.0001/call) -> OpenAlex id + referenced_works.
Writes work/edges/s2.sqlite3: ext(paper_id, doi), oa(paper_id, oa_id, refs). Resumable. Cost printed from meta.cost_usd.
"""
import json,sqlite3,sys,time
from pathlib import Path
from urllib import request,parse,error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import edges_jev as J
from recover_openalex import load_key
from citations_s2 import batch

def oa_get(url):
 for attempt in range(8):
  try:
   with request.urlopen(request.Request(url,headers={'User-Agent':'PaperEvolve/0.1 (citation graph)'}),timeout=60) as r:return json.load(r)
  except error.HTTPError as exc:
   if exc.code in [429,500,502,503,504]:
    print('OpenAlex',exc.code,'retrying',flush=True);time.sleep(min(120,5*2**attempt));continue
   raise
  except (error.URLError,TimeoutError,OSError):time.sleep(min(60,5*2**attempt))
 raise RuntimeError('OpenAlex unavailable; rerun to resume.')

def main():
 db=sqlite3.connect(J.E/'s2.sqlite3',timeout=120)
 db.execute('CREATE TABLE IF NOT EXISTS ext(paper_id TEXT PRIMARY KEY,doi TEXT)');db.execute('CREATE TABLE IF NOT EXISTS oa(paper_id TEXT PRIMARY KEY,oa_id TEXT,refs TEXT)');db.commit()
 P=J.papers();s2=dict(db.execute('SELECT paper_id,s2_id FROM ids WHERE s2_id IS NOT NULL'))
 have={r[0] for r in db.execute('SELECT paper_id FROM ext')}
 todo=[p for p in P if p in s2 and p not in have];print('externalIds to fetch',len(todo),flush=True)
 for i in range(0,len(todo),500):
  chunk=todo[i:i+500]
  res=batch([s2[p] for p in chunk],'externalIds')
  rows=[]
  for p,r in zip(chunk,res):
   x=(r or {}).get('externalIds') or {}
   doi=x.get('DOI') or (('10.48550/arxiv.'+x['ArXiv']) if x.get('ArXiv') else None)
   rows.append((p,doi.lower() if doi else None))
  db.executemany('INSERT OR REPLACE INTO ext VALUES (?,?)',rows);db.commit()
 # ACL fallback: Anthology DOI is derivable from the URL.
 for p,r in P.items():
  if 'aclanthology.org' in r['source_url']:
   aid=parse.urlparse(r['source_url']).path.strip('/')
   db.execute('INSERT INTO ext VALUES (?,?) ON CONFLICT(paper_id) DO UPDATE SET doi=COALESCE(doi,excluded.doi)',(p,'10.18653/v1/'+aid.lower()))
 db.commit()
 ext={p:d for p,d in db.execute('SELECT paper_id,doi FROM ext WHERE doi IS NOT NULL')}
 done={r[0] for r in db.execute('SELECT paper_id FROM oa')}
 need=[p for p in ext if p not in done];print('papers with DOI',len(ext),'| OpenAlex lookups needed',len(need),flush=True)
 key=load_key();cost=0.0;t=time.time()
 for i in range(0,len(need),50):
  chunk=need[i:i+50];by={ext[p]:p for p in chunk}
  q={'filter':'doi:'+'|'.join(by),'per_page':50,'select':'id,doi,referenced_works','api_key':key}
  d=oa_get('https://api.openalex.org/works?'+parse.urlencode(q));cost+=float(d.get('meta',{}).get('cost_usd') or 0)
  found={}
  for w in d.get('results',[]):
   doi=(w.get('doi') or '').lower().replace('https://doi.org/','')
   if doi in by:found[by[doi]]=(w['id'],json.dumps(w.get('referenced_works') or []))
  db.executemany('INSERT OR REPLACE INTO oa VALUES (?,?,?)',[(p,)+found.get(p,(None,'[]')) for p in chunk]);db.commit()
  if (i//50)%100==0:print(f'{i+len(chunk)}/{len(need)} looked up, OpenAlex cost ${cost:.4f}, {time.time()-t:.0f}s',flush=True)
 n=db.execute("SELECT COUNT(oa_id),SUM(refs!='[]') FROM oa").fetchone();print('OpenAlex matched',n[0],'| with references',n[1],'| cost $%.4f' % cost,flush=True)

if __name__=='__main__':main()
