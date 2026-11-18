"""Recover missing abstracts from Semantic Scholar (free, no key). OpenReview's API is behind a bot challenge.
ICLR: bulk venue search, accept only exact normalized title + |year diff|<=1 + >=1 shared author, unique match.
ACL: batch lookup by Anthology ID (ACL:<id>), exact ID so no title matching needed.
Resume-safe: only fills URLs missing from work/abstracts/cache.sqlite3.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import base64,gzip,json,re,sqlite3,time
from datetime import datetime,timezone
from urllib import request,parse,error
from voyage_pipeline import ROOT,read_records
from recover_openalex import normalize

API='https://api.semanticscholar.org/graph/v1'
UA='PaperEvolve/0.1 (public scientific metadata; abstract recovery)'
ICLR_VENUE='International Conference on Learning Representations'

def call(url,body=None):
 for attempt in range(8):
  req=request.Request(url,data=json.dumps(body).encode() if body else None,headers={'User-Agent':UA,'Content-Type':'application/json'})
  try:
   with request.urlopen(req,timeout=60) as r:data=json.load(r)
   time.sleep(1.1);return data
  except error.HTTPError as exc:
   if exc.code in [429,500,502,503,504]:time.sleep(min(60,5*2**attempt));continue
   raise
 raise RuntimeError('Semantic Scholar kept throttling; rerun later, progress is saved.')

def now():return datetime.now(timezone.utc).isoformat()

def main():
 db=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60);db.execute('PRAGMA busy_timeout=60000')
 have={r[0] for r in db.execute('SELECT url FROM abstracts')}
 missing=[r for r in read_records('corpus') if r['source_url'] not in have]
 atlas=(ROOT/'atlas.html').read_text();m=re.search(r'const hoverDataEncoded = "([^"]+)"',atlas);meta=json.loads(gzip.decompress(base64.b64decode(m[1])))
 authors=dict(zip(meta['url'],meta['authors']));del atlas,meta
 def save(url,text,endpoint):
  db.execute('INSERT OR IGNORE INTO abstracts VALUES (?,?,?,?)',(url,' '.join(text.split()),now(),endpoint));db.execute('DELETE FROM failures WHERE url=?',(url,))

 # ACL by exact Anthology ID.
 acl=[r for r in missing if 'aclanthology.org' in r['source_url']];got_acl=0
 for i in range(0,len(acl),500):
  chunk=acl[i:i+500];ids=['ACL:'+parse.urlparse(r['source_url']).path.strip('/') for r in chunk]
  for r,p in zip(chunk,call(API+'/paper/batch?fields=abstract',{'ids':ids})):
   if p and p.get('abstract') and len(p['abstract'])>=40:save(r['source_url'],p['abstract'],API+'/paper/'+p['paperId']);got_acl+=1
 db.commit();print(f'ACL: recovered {got_acl}/{len(acl)}',flush=True)

 # ICLR by bulk venue listing.
 iclr=[r for r in missing if 'openreview.net' in r['source_url']]
 if not iclr:return
 years=sorted({r['year'] for r in iclr});lo,hi=years[0]-1,years[-1]+1
 by_title={}
 token=None;pages=0
 while True:
  q={'venue':ICLR_VENUE,'year':f'{lo}-{hi}','fields':'title,abstract,year,authors'}
  if token:q['token']=token
  data=call(API+'/paper/search/bulk?'+parse.urlencode(q));pages+=1
  for p in data.get('data',[]):
   if p.get('abstract') and p.get('title'):by_title.setdefault(normalize(p['title']),[]).append(p)
  print(f'ICLR listing page {pages}: {sum(map(len,by_title.values()))} papers with abstracts (S2 total {data.get("total")})',flush=True)
  token=data.get('token')
  if not token:break
 got=0;reasons={}
 for r in iclr:
  cands=[p for p in by_title.get(normalize(r['title']),[]) if isinstance(p.get('year'),int) and abs(p['year']-r['year'])<=1]
  expected={normalize(a) for a in authors.get(r['source_url'],'').split(',') if a.strip()}
  cands=[p for p in cands if expected & {normalize(a.get('name') or '') for a in p.get('authors',[])}]
  uniq={p['paperId']:p for p in cands}
  if len(uniq)==1:
   p=next(iter(uniq.values()))
   if len(p['abstract'])>=40:save(r['source_url'],p['abstract'],API+'/paper/'+p['paperId']);got+=1;continue
  why='ambiguous' if len(uniq)>1 else 'no_verified_match';reasons[why]=reasons.get(why,0)+1
 db.commit();print(f'ICLR: recovered {got}/{len(iclr)}; unmatched {reasons}',flush=True)

if __name__=='__main__':main()
