"""Public-paper retrieval and additive, reviewable contributor evidence.

PDFs/full text remain in the ignored workspace. Submitted excerpts carry paper
identity, official URL, physical PDF page, document hash and retrieval metadata.
Offline validation checks consistency; a maintainer still verifies authenticity.
"""
import copy
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib import request, parse, error
from voyage_pipeline import atomic_json

VERSION = 'paper-evolve-research-v1'
HOSTS = {'arxiv.org', 'www.arxiv.org', 'aclanthology.org', 'openreview.net',
         'proceedings.mlr.press', 'papers.nips.cc', 'papers.neurips.cc',
         'proceedings.neurips.cc', 'openaccess.thecvf.com', 'jmlr.org', 'www.jmlr.org',
         'proceedings.aaai.org'}
LIMIT = 40_000_000


def sha(data):return hashlib.sha256(data).hexdigest()
def digest(value):return sha(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
def normalize(value):return ' '.join(value.split())
def compact(value):return ''.join(c.casefold() for c in value if c.isalnum())


def official_url(url):
    p = parse.urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password
            or p.port not in (None, 443) or p.fragment
            or set(k.lower() for k in parse.parse_qs(p.query)).intersection({'token','api_key','apikey','access_token','secret','password'})):
        raise ValueError('Use a public HTTPS paper URL on a supported official host; no credentials or custom ports.')
    return url


class Redirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)  # Check before following, not after making a request.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get(url):
    official_url(url)
    req = request.Request(url, headers={'User-Agent': 'PaperEvolve/0.1 (public scientific source research)'})
    try:
        with request.build_opener(Redirects()).open(req, timeout=45) as response:
            final = official_url(response.geturl())
            body = response.read(LIMIT + 1)
    except error.HTTPError as exc:
        raise ValueError('Paper host returned HTTP ' + str(exc.code) + '; try an official open-access version. No access controls are bypassed.') from None
    if len(body) > LIMIT:raise ValueError('Paper exceeds the 40 MB download limit.')
    return body, final


class Links(HTMLParser):
    def __init__(self):super().__init__();self.urls=[]
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):self.urls.append(attrs['href'])


def pdf_url(url, fetch=get):
    p = parse.urlsplit(official_url(url))
    if p.path.lower().endswith('.pdf'):return url
    if p.hostname in {'arxiv.org','www.arxiv.org'}:
        return parse.urlunsplit((p.scheme,p.netloc,p.path.replace('/abs/','/pdf/'),p.query,''))
    if p.hostname == 'aclanthology.org':return url.rstrip('/') + '.pdf'
    if p.hostname == 'openreview.net':
        identity = parse.parse_qs(p.query).get('id')
        if not identity:raise ValueError('OpenReview source needs a paper id.')
        return 'https://openreview.net/pdf?id=' + parse.quote(identity[0])
    if p.hostname in {'papers.nips.cc','papers.neurips.cc','proceedings.neurips.cc'}:
        return url.replace('/hash/','/file/').replace('/hash_files/','/file/').replace('-Abstract','-Paper').replace('.html','.pdf')
    body, final = fetch(url)
    if body.startswith(b'%PDF-'):return official_url(final)
    links = Links();links.feed(body.decode('utf-8','replace'))
    for href in links.urls:
        candidate = parse.urljoin(final, href)
        if parse.urlsplit(candidate).path.lower().endswith('.pdf'):
            try:return official_url(candidate)
            except ValueError:continue
    raise ValueError('No official PDF link found. Supply --url with the official PDF or a matching open-access version.')


def extract(path):
    if shutil.which('pdftotext'):
        result = subprocess.run(['pdftotext','-enc','UTF-8',str(path),'-'],
                                check=True,capture_output=True,text=True,timeout=60)
        pages = result.stdout.split('\f')
        if pages and not pages[-1].strip():pages.pop()
        return [normalize(p) for p in pages], 'pdftotext (reading order)'
    try:from pypdf import PdfReader
    except ImportError:
        raise ValueError('Full-paper extraction needs pdftotext (Poppler) or pypdf. Install one in your own environment, or use your existing PDF reader.') from None
    return [normalize(p.extract_text() or '') for p in PdfReader(str(path)).pages], 'pypdf'


def selected_task(destination, identity):
    import contribution_workspace as W
    import community_edges as C
    workspace, pack, envelope = W.load(destination)
    if identity not in workspace['selected_task_ids']:raise ValueError('Choose a task from this workspace.')
    return C.task_index(pack)[identity], envelope


def fetch_papers(destination, identity, side='both', url=None, file=None, fetch=None, extractor=None):
    destination = Path(destination)
    task, _ = selected_task(destination, identity)
    if side not in {'a','b','both'}:raise ValueError('Choose paper a, b or both.')
    if (url or file) and side == 'both':raise ValueError('Choose one --side when supplying --url or --file.')
    if file and not url:raise ValueError('Imported PDFs need --url to record their public provenance.')
    fetch = fetch or get;extractor = extractor or extract
    research = destination / 'research';documents = research / 'documents';documents.mkdir(parents=True,exist_ok=True)
    index_path = research / 'index.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    results = []
    for role in (['a','b'] if side == 'both' else [side]):
        key = identity + ':' + role
        source = url or task['sources'][role]['url']
        cached = False
        if not url and not file and key in index:
            old_hash = index[key]
            if not re.fullmatch(r'[a-f0-9]{64}',old_hash):raise ValueError('Invalid cached PDF fingerprint.')
            saved = json.loads((documents/(old_hash+'.json')).read_text())
            if saved['paper_id'] != task[role] or saved['origin_url'] != task['sources'][role]['url']:
                raise ValueError('Cached source identifies a different paper.')
            body = (documents/(old_hash+'.pdf')).read_bytes()
            if sha(body)!=old_hash:raise ValueError('Cached PDF changed; explicitly fetch its official URL again.')
            final = saved['url'];cached = True
        elif file:
            endpoint = official_url(source)
            path = Path(file)
            if path.stat().st_size > LIMIT:raise ValueError('Imported PDF exceeds 40 MB.')
            body = path.read_bytes();final = endpoint
        else:
            endpoint = pdf_url(source,fetch)
            body, final = fetch(endpoint)
        official_url(final)
        if len(body)>LIMIT or not body.startswith(b'%PDF-'):raise ValueError('The source did not return a supported PDF.')
        document_hash = sha(body);pdf_path = documents / (document_hash + '.pdf')
        pdf_path.write_bytes(body)
        pages, tool = extractor(pdf_path)
        title = task['state']['paper_' + role]['title']
        if (not pages or len(''.join(pages)) < 1000
                or compact(title) not in compact(' '.join(pages)[:20000])):
            raise ValueError('PDF text/title does not match the selected paper. Check the source/version; no evidence was registered.')
        pages = [normalize(p) for p in pages]
        metadata = {'paper_id':task[role], 'paper_title':title, 'origin_url':task['sources'][role]['url'],
                    'url':final, 'document_sha256':document_hash, 'retrieved_at':saved['retrieved_at'] if cached else datetime.now(timezone.utc).isoformat(),
                    'extraction':tool, 'acquired_via':saved['acquired_via'] if cached else ('local_pdf' if file else 'public_download'), 'pages':pages}
        atomic_json(documents / (document_hash + '.json'),metadata)
        text_path = documents / (document_hash + '.txt')
        text_path.write_text('\n\n'.join(f'--- PDF PAGE {i} ---\n{text}' for i,text in enumerate(pages,1)))
        index[key] = document_hash
        atomic_json(index_path,index)
        results.append({'side':role,'pages':len(pages),'pdf':str(pdf_path),'text':str(text_path),
                        'url':final,'document_sha256':document_hash,'cached':cached})
    return {'task_id':identity,'documents':results,'published':False}


def augment(task, material):
    """Validate an additive source snapshot without trusting it as publication truth."""
    if (not isinstance(material,dict) or set(material)!={'version','passages','sha256'}
            or material['version']!=VERSION or material['sha256']!=digest({k:v for k,v in material.items() if k!='sha256'})):
        raise ValueError('Invalid research evidence fingerprint.')
    passages = material['passages']
    if not isinstance(passages,list) or not 1 <= len(passages) <= 12:raise ValueError('Attach 1–12 diagnostic source excerpts.')
    state = copy.deepcopy(task['state']);packet = state.setdefault('source_evidence',{'status':'needs_context','passages':[],'documents':{}})
    ids = {p['id'] for p in packet.get('passages',[])}
    fields = {'id','paper_id','paper_title','origin_url','url','page','document_sha256','text','text_sha256','retrieved_at','extraction','acquired_via'}
    for p in passages:
        if not isinstance(p,dict) or set(p)!=fields:raise ValueError('Research passage metadata is incomplete.')
        identity = p['id']
        if not isinstance(identity,str) or not re.fullmatch(r'(?:a_passage|b_passage|b_citation)_research_[1-9][0-9]?',identity) or identity in ids:
            raise ValueError('Invalid, duplicate or overwritten research source ID.')
        ids.add(identity);side = identity[0]
        if (p['paper_id']!=task[side] or p['origin_url']!=task['sources'][side]['url']
                or p['paper_title']!=task['state']['paper_'+side]['title']):raise ValueError('Research source belongs to a different paper.')
        official_url(p['url'])
        if type(p['page']) is not int or not 1<=p['page']<=10000:raise ValueError('Research quotes need a physical PDF page number.')
        if not isinstance(p['document_sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',p['document_sha256']):raise ValueError('Missing PDF fingerprint.')
        if not isinstance(p['text'],str) or not 16<=len(p['text'])<=16000 or sha(p['text'].encode())!=p['text_sha256']:
            raise ValueError('Research excerpt fingerprint or size is invalid.')
        try:stamp=datetime.fromisoformat(p['retrieved_at'])
        except (TypeError,ValueError):raise ValueError('Invalid source retrieval timestamp.') from None
        if stamp.tzinfo is None or p['acquired_via'] not in {'public_download','local_pdf'} or not isinstance(p['extraction'],str) or not p['extraction'].strip():
            raise ValueError('Declare how and when the PDF text was extracted.')
        packet.setdefault('passages',[]).append({**p,'kind':'citation' if identity.startswith('b_citation') else 'passage'})
    a_ready = task['state'].get('source_evidence',{}).get('status')=='ready' or packet.get('documents',{}).get('a',{}).get('status')=='ready' or any(p['id'].startswith('a_') for p in passages)
    packet['status'] = 'ready' if a_ready and any(p['id'].startswith('b_citation_') for p in packet['passages']) else 'needs_context'
    packet['research_provenance'] = 'contributor_retrieved; publication authenticity requires separate source review'
    return state


def cite(destination, identity, side, page, kind, quote_file):
    destination = Path(destination);task,envelope = selected_task(destination,identity)
    if side not in {'a','b'} or kind not in {'passage','citation'} or (side=='a' and kind=='citation'):
        raise ValueError('Use passage for A; passage or citation for B.')
    index = json.loads((destination/'research/index.json').read_text())
    document_hash = index[identity+':'+side]
    if not re.fullmatch(r'[a-f0-9]{64}',document_hash):raise ValueError('Invalid cached PDF fingerprint.')
    documents = destination/'research/documents';metadata = json.loads((documents/(document_hash+'.json')).read_text())
    if sha((documents/(document_hash+'.pdf')).read_bytes())!=document_hash:raise ValueError('Downloaded PDF changed after extraction.')
    # Re-extract from the PDF, rather than trusting an edited local text file.
    pages,tool = extract(documents/(document_hash+'.pdf'))
    if compact(task['state']['paper_'+side]['title']) not in compact(' '.join(pages)[:20000]):
        raise ValueError('PDF title does not match the selected paper.')
    if type(page) is not int or not 1<=page<=len(pages):raise ValueError('Physical PDF page is outside the document.')
    quote = normalize(Path(quote_file).read_text())
    if not 16<=len(quote)<=16000 or quote not in normalize(pages[page-1]):
        raise ValueError('Quote is not an exact excerpt of that extracted PDF page.')
    rows = envelope['submission']['decisions'];row = next((r for r in rows if r['task_id']==identity),None)
    if row is None:
        import contribution_workspace as W
        row={'task_id':identity,'task_sha256':task['sha256'],'decision':W.blank_decision()};rows.append(row)
    material = row.get('source_material',{'version':VERSION,'passages':[]})
    prefix = side+'_'+kind+'_research_'
    number = 1
    while any(p['id']==prefix+str(number) for p in material['passages']):number+=1
    passage = {k:metadata[k] for k in ('paper_id','paper_title','origin_url','url','document_sha256','retrieved_at','acquired_via')}
    passage.update(id=prefix+str(number),page=page,text=quote,text_sha256=sha(quote.encode()),extraction=tool)
    material['passages'].append(passage)
    material['sha256']=digest({k:v for k,v in material.items() if k!='sha256'})
    augment(task,material)
    row['source_material']=material
    atomic_json(destination/'submission.json',envelope)
    return {'task_id':identity,'source_id':passage['id'],'page':page,'document_sha256':document_hash,'published':False}
