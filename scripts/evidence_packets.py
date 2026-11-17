"""Local source retrieval for contribution review. No paid model calls.
Only downloads official paper PDFs or an already verified arXiv alternate.
"""
import argparse,hashlib,json,re,sqlite3,subprocess,time,fcntl
from pathlib import Path
from urllib import request,parse,error
from html.parser import HTMLParser
from voyage_pipeline import ROOT,read_records,atomic_json

WORK=ROOT/'work/evidence'
ALLOWED={'proceedings.mlr.press','raw.githubusercontent.com','papers.nips.cc','papers.neurips.cc','proceedings.neurips.cc','openreview.net','arxiv.org','aclanthology.org'}
IDS=['a_passage_1','a_passage_2','b_citation_1','b_citation_2','b_passage_1','b_passage_2']
VERSION='source-packets-v1'

def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def compact(s):return ''.join(c.casefold() for c in s if c.isalnum())

class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='a' and attrs.get('href'):self.links.append(attrs['href'])

def get(url,max_bytes=40000000):
 if url.startswith('http://'):url='https://'+url[7:]
 if parse.urlparse(url).hostname not in ALLOWED:raise ValueError('Unsupported source host')
 req=request.Request(url,headers={'User-Agent':'PaperEvolve/0.1 (local scientific evidence retrieval)'})
 with request.urlopen(req,timeout=45) as r:
  final=r.geturl()
  if parse.urlparse(final).hostname not in ALLOWED:raise ValueError('Unsupported redirect')
  body=r.read(max_bytes+1)
  if len(body)>max_bytes:raise ValueError('Source exceeds retrieval limit')
  if b'Verifying your browser' in body[:15000] or '/challenge?' in final:raise ValueError('Source blocked by verification challenge')
  return body,final

def pdf_url(url):
 p=parse.urlparse(url);host=p.hostname
 if host=='aclanthology.org':return url.rstrip('/')+'.pdf'
 if host=='arxiv.org':return re.sub(r'/abs/','/pdf/',url)
 if host=='openreview.net':return 'https://openreview.net/pdf?id='+parse.quote(parse.parse_qs(p.query)['id'][0])
 if host in {'papers.nips.cc','papers.neurips.cc','proceedings.neurips.cc'}:
  return url.replace('/hash/','/file/').replace('-Abstract','-Paper').replace('.html','.pdf')
 if host=='proceedings.mlr.press':
  body,_=get(url);parser=Links();parser.feed(body.decode('utf-8','replace'))
  for link in parser.links:
   target=parse.urljoin(url,link)
   if target.endswith('.pdf') and parse.urlparse(target).hostname in ALLOWED:return target
 raise ValueError('No official PDF link found')

def paragraphs(text):
 """Keep page and original normalized text; exclude the reference list itself."""
 result=[];references=False
 for page,content in enumerate(text.split('\f'),1):
  for block in re.split(r'\n\s*\n',content):
   if re.match(r'^\s*(?:\d+\s+)?(?:References|Bibliography)\s*(?:\n|$)',block,re.I):references=True
   if references:continue
   normalized=' '.join(block.split())
   if len(normalized)>=100:result.append({'page':page,'text':normalized})
 return result

def reference_number(text,title):
 # Restrict numeric citation resolution to a bibliography entry matching the exact title.
 tail=re.split(r'\n\s*(?:References|Bibliography)\s*\n',text,flags=re.I)
 if len(tail)<2:return None
 for block in re.split(r'(?m)(?=^\s*\[\d+\])',tail[-1]):
  if compact(title) in compact(block):
   match=re.match(r'^\s*\[(\d+)\]',block)
   if match:return match[1]
 return None

def choose_passages(doc,title,context='',role='b'):
 paras=paragraphs(doc['text']);ref=reference_number(doc['text'],title)
 name=title.split(':')[0].strip()
 use_name=':' in title and len(name)>=4 and len(name.split())<=3
 snippets=[compact(s)[:180] for s in context.splitlines() if len(compact(s))>=50]
 citations=[];methods=[]
 tokens=set(re.findall(r'[a-z]{5,}',title.lower()))-{'learning','networks','neural','models','using','based','towards','understanding'}
 for p in paras:
  t=p['text'];n=compact(t)
  linked=any(s in n for s in snippets) or bool(ref and re.search(r'\['+ref+r'\]',t)) or bool(use_name and re.search(r'(?<![\w-])'+re.escape(name)+r'(?![\w-])',t,re.I))
  if linked and not re.match(r'^Abstract\b',t,re.I):
   rank=sum(snippet in n for snippet in snippets)*10+int(bool(use_name and name.casefold() in t.casefold()))
   citations.append((rank,p))
  overlap=len(tokens&set(re.findall(r'[a-z]{5,}',t.lower())))
  if re.search(r'\b(?:we propose|our method|our approach|we introduce|our framework|we extend)\b',t,re.I):
   methods.append((overlap,p))
 methods=[p for _,p in sorted(methods,key=lambda item:-item[0])]
 seen=set();out=[]
 citations=[p for _,p in sorted(citations,key=lambda item:-item[0])]
 for kind,items in [('citation',citations),('passage',methods)]:
  if role=='a' and kind=='citation':continue
  for p in items:
   if p['text'] in seen:continue
   seen.add(p['text']);i=sum(x['kind']==kind for x in out)+1
   if i>2:break
   # Source text is normalized, then excerpted. No model paraphrase enters the packet.
   excerpt=p['text'][:1800]
   if len(p['text'])>1800:excerpt=excerpt.rsplit(' ',1)[0]
   out.append({'id':f'{role}_{kind}_{i}','kind':kind,'page':p['page'],'text':excerpt,'url':doc['pdf_url'],'document_sha256':doc['sha256']})
 return out

def document(record,alternate=None):
 # Multiple source workers often share a highly cited parent. Serialize that
 # document's cache write/download, without serializing unrelated papers.
 WORK.mkdir(parents=True,exist_ok=True)
 with (WORK/(digest(record['source_url'])+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  return _document(record,alternate)

def _document(record,alternate=None):
 WORK.mkdir(parents=True,exist_ok=True);identity=digest(record['source_url']);path=WORK/(identity+'.json')
 if path.exists():
  cached=json.loads(path.read_text())
  if cached.get('pdf_url','').startswith('http://'):cached['pdf_url']='https://'+cached['pdf_url'][7:]
  return cached
 failures=[]
 urls=[record['source_url']]
 if alternate and parse.urlparse(alternate).hostname=='arxiv.org':urls.append(alternate)
 for url in urls:
  try:
   endpoint=pdf_url(url);body,endpoint=get(endpoint)
   if not body.startswith(b'%PDF-'):raise ValueError('Endpoint did not return a PDF')
   file=WORK/(identity+'.pdf');file.write_bytes(body)
   r=subprocess.run(['pdftotext',str(file),'-'],check=True,capture_output=True,text=True,timeout=45)
   text=r.stdout
   if len(text)<1000:raise ValueError('PDF has insufficient extractable text')
   # Exact URL identifies the paper; a title check also rejects unrelated/error PDFs.
   if compact(record['title']) not in compact(text[:15000]):raise ValueError('PDF title does not match corpus title')
   doc={'status':'ready','source_url':record['source_url'],'pdf_url':endpoint,'sha256':hashlib.sha256(body).hexdigest(),'text':text}
   atomic_json(path,doc);return doc
  except (ValueError,OSError,error.URLError,subprocess.SubprocessError) as e:failures.append(type(e).__name__+': '+str(e)[:180])
 failed={'status':'unavailable','source_url':record['source_url'],'errors':failures}
 atomic_json(path,failed);return failed

def build_packet(a,b,state,records,alternates):
 docs={};passages=[]
 for role,pid in [('a',a),('b',b)]:
  doc=document(records[pid],alternates.get(records[pid]['source_url']));docs[role]={k:v for k,v in doc.items() if k!='text'}
  if doc['status']=='ready':passages+=choose_passages(doc,state['paper_a']['title'] if role=='b' else records[pid]['title'],state.get('citing_sentence','') if role=='b' else '',role)
 linked=any(p['kind']=='citation' for p in passages)
 packet={'version':VERSION,'a':a,'b':b,'input_sha256':digest(json.dumps([state['paper_a'],state['paper_b']],sort_keys=True)),
         'status':'ready' if linked and docs['a']['status']=='ready' else 'needs_context','documents':docs,'passages':passages}
 atomic_json(WORK/'pairs'/(digest(a+'|'+b)+'.json'),packet);return packet

def enrich(a,b,state):
 path=WORK/'pairs'/(digest(a+'|'+b)+'.json')
 if not path.exists():return state
 packet=json.loads(path.read_text());current=digest(json.dumps([state['paper_a'],state['paper_b']],sort_keys=True))
 if current!=packet['input_sha256']:return state
 return {**state,'source_evidence':packet}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--limit',type=int,default=8);args=ap.parse_args()
 records={r['id']:r for r in read_records('corpus')}
 with sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3') as db:alternates=dict(db.execute('SELECT url,endpoint FROM abstracts'))
 sample=json.loads((ROOT/'work/relation-review/sample.json').read_text())
 priority=['R20','R24','R30','R27','R05','R07','R06','R23'];sample.sort(key=lambda r:priority.index(r['review_id']) if r['review_id'] in priority else 100)
 reports=[]
 for row in sample[:args.limit]:
  packet=build_packet(row['a'],row['b'],row['state'],records,alternates)
  reports.append({'review_id':row['review_id'],'a':row['a'],'b':row['b'],'status':packet['status'],'passages':len(packet['passages'])})
  atomic_json(WORK/'pilot.json',reports);print(json.dumps(reports[-1]),flush=True);time.sleep(.5)

if __name__=='__main__':main()
