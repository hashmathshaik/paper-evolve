"""Recover still-missing ICLR (and ACL) abstracts from free public sources, one source per process.
  --source arxiv : arXiv API, ~8 titles per OR'd ti:"..." query, 3.1 s between requests (arXiv's stated pace).
  --source s2    : Semantic Scholar /paper/search/match (keyless; backs off on 429).
  --source hf    : Hugging Face /api/papers/search (arXiv papers; 'summary' is the arXiv abstract).
Accept only: exact normalized title + >=1 shared author, unique candidate. Same rule as recover_s2/OpenAlex.
Re-reads the missing set every batch, so parallel processes skip what another source already filled.
Every checked paper is logged in work/recover_more/<source>.done so a rerun resumes.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import argparse,base64,gzip,json,re,sqlite3,time
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from urllib import request,parse,error
from voyage_pipeline import ROOT,read_records
from recover_openalex import normalize

UA='PaperEvolve/0.1 (public scientific metadata; abstract recovery)'
WORK=ROOT/'work/recover_more'
ATOM='{http://www.w3.org/2005/Atom}'

def get(url,pause):
 for attempt in range(8):
  try:
   with request.urlopen(request.Request(url,headers={'User-Agent':UA}),timeout=60) as r:body=r.read()
   time.sleep(pause);return body
  except error.HTTPError as exc:
   if exc.code==404:time.sleep(pause);return None
   if exc.code in [429,500,502,503,504]:time.sleep(min(120,max(pause,5)*2**attempt));continue
   raise
  except (error.URLError,TimeoutError,OSError):time.sleep(min(120,10*2**attempt))
 return None

def phrase(title):  # arXiv phrase query: letters/digits only
 return ' '.join(re.sub(r'[^A-Za-z0-9 ]',' ',title).split()[:14])

def arxiv(batch):
 q=' OR '.join(f'ti:"{phrase(r["title"])}"' for r in batch if phrase(r['title']))
 body=get('https://export.arxiv.org/api/query?'+parse.urlencode({'search_query':q,'max_results':50}),3.1)
 if not body:return []
 out=[]
 for e in ET.fromstring(body).findall(ATOM+'entry'):
  out.append({'title':e.findtext(ATOM+'title') or '','abstract':' '.join((e.findtext(ATOM+'summary') or '').split()),
   'authors':[a.findtext(ATOM+'name') or '' for a in e.findall(ATOM+'author')],'endpoint':e.findtext(ATOM+'id')})
 return out

def s2(batch):
 out=[]
 for r in batch:
  body=get('https://api.semanticscholar.org/graph/v1/paper/search/match?'+parse.urlencode({'query':r['title'],'fields':'title,abstract,authors'}),1.5)
  for p in (json.loads(body).get('data',[]) if body else []):
   out.append({'title':p.get('title') or '','abstract':p.get('abstract') or '','authors':[a.get('name') or '' for a in p.get('authors',[])],'endpoint':'https://api.semanticscholar.org/graph/v1/paper/'+p['paperId']})
 return out

def hf(batch):
 out=[]
 for r in batch:
  body=get('https://huggingface.co/api/papers/search?'+parse.urlencode({'q':r['title']}),1.0)
  for item in (json.loads(body) if body else []):
   p=item.get('paper',item)
   out.append({'title':p.get('title') or '','abstract':' '.join((p.get('summary') or '').split()),'authors':[a.get('name') or '' for a in p.get('authors',[])],'endpoint':'https://arxiv.org/abs/'+p.get('id','')})
 return out

SOURCES={'arxiv':(arxiv,8),'s2':(s2,5),'hf':(hf,5)}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',choices=SOURCES,required=True);ap.add_argument('--limit',type=int);args=ap.parse_args()
 fn,size=SOURCES[args.source];WORK.mkdir(parents=True,exist_ok=True);done_path=WORK/f'{args.source}.done'
 done=set(done_path.read_text().split()) if done_path.exists() else set()
 db=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60);db.execute('PRAGMA busy_timeout=60000')
 corpus=[r for r in read_records('corpus') if 'openreview.net' in r['source_url'] or 'aclanthology.org' in r['source_url']]
 atlas=(ROOT/'atlas.html').read_text();m=re.search(r'const hoverDataEncoded = "([^"]+)"',atlas);meta=json.loads(gzip.decompress(base64.b64decode(m[1])))
 authors=dict(zip(meta['url'],meta['authors']));del atlas,meta
 def missing():
  have={r[0] for r in db.execute('SELECT url FROM abstracts')}
  return [r for r in corpus if r['source_url'] not in have and r['id'] not in done]
 todo=missing()[:args.limit] if args.limit else missing();# Spread sources across the list so parallel processes rarely query the same paper.
 if args.source=='hf':todo.reverse()
 if args.source=='s2':todo=todo[len(todo)//2:]+todo[:len(todo)//2]
 print(f'{args.source}: {len(todo)} to check',flush=True)
 got=checked=0;log=done_path.open('a')
 while todo:
  batch,todo=todo[:size],todo[size:]
  have={r[0] for r in db.execute('SELECT url FROM abstracts')};batch=[r for r in batch if r['source_url'] not in have]
  if not batch:continue
  cands=fn(batch);by_title={}
  for c in cands:
   if len(c['abstract'])>=40:by_title.setdefault(normalize(c['title']),[]).append(c)
  for r in batch:
   expected={normalize(a) for a in authors.get(r['source_url'],'').split(',') if a.strip()}
   ok=[c for c in by_title.get(normalize(r['title']),[]) if expected & {normalize(a) for a in c['authors']}]
   uniq={c['abstract']:c for c in ok}
   if len(uniq)==1:
    c=next(iter(uniq.values()))
    db.execute('INSERT OR IGNORE INTO abstracts VALUES (?,?,?,?)',(r['source_url'],c['abstract'],datetime.now(timezone.utc).isoformat(),c['endpoint']));db.execute('DELETE FROM failures WHERE url=?',(r['source_url'],));got+=1
   log.write(r['id']+'\n');checked+=1
  db.commit();log.flush()
  if checked%40<size:print(f'{args.source}: checked {checked}, recovered {got}',flush=True)
 print(f'{args.source}: DONE checked {checked}, recovered {got}',flush=True)

if __name__=='__main__':main()
