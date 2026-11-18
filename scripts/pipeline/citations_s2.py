"""Map every corpus paper to a Semantic Scholar paperId, then fetch its reference list. Free, keyless.
ID mapping: ACL -> exact 'ACL:<anthology id>'; ICLR/NeurIPS/ICML -> S2 bulk venue listing, exact normalized
title + |year diff|<=1, unique. Writes work/edges/s2.sqlite3 (paper_id -> s2_id, refs JSON). Resumable.
"""
import json,sqlite3,sys,time
from pathlib import Path
from urllib import request,parse,error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
from voyage_pipeline import ROOT,read_records
from recover_openalex import normalize

API='https://api.semanticscholar.org/graph/v1';UA='PaperEvolve/0.1 (citation graph for research)'
VENUES={'openreview.net':'International Conference on Learning Representations','papers.nips.cc':'Neural Information Processing Systems','proceedings.mlr.press':'International Conference on Machine Learning'}

def call(url,body=None):
 for attempt in range(10):
  try:
   req=request.Request(url,data=json.dumps(body).encode() if body else None,headers={'User-Agent':UA,'Content-Type':'application/json'})
   with request.urlopen(req,timeout=120) as r:data=json.load(r)
   time.sleep(1.2);return data
  except error.HTTPError as exc:
   if exc.code in [429,500,502,503,504]:time.sleep(min(90,5*2**attempt));continue
   if exc.code==400:print('S2 400:',exc.read()[:200],flush=True);return None
   raise
  except (error.URLError,TimeoutError,OSError):time.sleep(min(90,5*2**attempt))
 raise RuntimeError('Semantic Scholar unavailable; rerun to resume.')

def acl_id(anth):
 # S2 accepts ACL:<id> only for old-style IDs (P18-1001); 2020+ IDs (2024.acl-long.475) need the Anthology DOI.
 return 'DOI:10.18653/v1/'+anth if '.' in anth else 'ACL:'+anth

def batch(ids,fields):
 # Split on 400 until the offending IDs are isolated; those come back as None.
 res=call(API+'/paper/batch?fields='+fields,{'ids':ids})
 if res is not None:return res
 if len(ids)==1:return [None]
 h=len(ids)//2;return batch(ids[:h],fields)+batch(ids[h:],fields)

def main():
 out=ROOT/'work/edges';out.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(out/'s2.sqlite3')
 db.execute('CREATE TABLE IF NOT EXISTS ids(paper_id TEXT PRIMARY KEY,s2_id TEXT,method TEXT)')
 db.execute('CREATE TABLE IF NOT EXISTS refs(s2_id TEXT PRIMARY KEY,refs TEXT)');db.commit()
 corpus=read_records('corpus');mapped={r[0] for r in db.execute('SELECT paper_id FROM ids')}
 todo=[r for r in corpus if r['id'] not in mapped];print('to map',len(todo),flush=True)

 acl=[r for r in todo if 'aclanthology.org' in r['source_url']]
 for i in range(0,len(acl),500):
  chunk=acl[i:i+500];res=batch([acl_id(parse.urlparse(r['source_url']).path.strip('/')) for r in chunk],'paperId')
  db.executemany('INSERT OR REPLACE INTO ids VALUES (?,?,?)',[(r['id'],p['paperId'] if p else None,'acl_id') for r,p in zip(chunk,res)]);db.commit()
 print('ACL mapped',db.execute("SELECT COUNT(s2_id) FROM ids WHERE method='acl_id'").fetchone()[0],'/',len(acl),flush=True)

 for host,venue in VENUES.items():
  rs=[r for r in todo if host in r['source_url']]
  if not rs:continue
  years=[r['year'] for r in rs];by_title={};token=None;pages=0
  while True:
   q={'venue':venue,'year':f'{min(years)-1}-{max(years)+1}','fields':'title,year'}
   if token:q['token']=token
   d=call(API+'/paper/search/bulk?'+parse.urlencode(q));pages+=1
   for p in d.get('data',[]):by_title.setdefault(normalize(p.get('title') or ''),[]).append(p)
   token=d.get('token')
   if not token:break
  rows=[]
  for r in rs:
   c={p['paperId'] for p in by_title.get(normalize(r['title']),[]) if isinstance(p.get('year'),int) and abs(p['year']-r['year'])<=1}
   rows.append((r['id'],c.pop() if len(c)==1 else None,'venue_title' if len(c)==0 else 'ambiguous'))
  db.executemany('INSERT OR REPLACE INTO ids VALUES (?,?,?)',rows);db.commit()
  print(f'{host}: {pages} listing pages, mapped {sum(1 for x in rows if x[1])}/{len(rs)}',flush=True)

 need=[r[0] for r in db.execute('SELECT DISTINCT s2_id FROM ids WHERE s2_id IS NOT NULL AND s2_id NOT IN (SELECT s2_id FROM refs)')]
 print('fetch references for',len(need),flush=True)
 for i in range(0,len(need),500):
  chunk=need[i:i+500];res=batch(chunk,'references.paperId')
  db.executemany('INSERT OR REPLACE INTO refs VALUES (?,?)',[(s,json.dumps([x['paperId'] for x in (p or {}).get('references') or [] if x.get('paperId')])) for s,p in zip(chunk,res)]);db.commit()
  if i//500%10==0:print(f'refs {i+len(chunk)}/{len(need)}',flush=True)
 n=db.execute('SELECT COUNT(*) FROM refs WHERE refs!="[]"').fetchone()[0];print('papers with non-empty reference lists',n,flush=True)

if __name__=='__main__':main()
