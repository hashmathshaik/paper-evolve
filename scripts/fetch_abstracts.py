"""Fetch official-source abstracts into a resumable local cache; no paid APIs.
Pilot default: seven research papers. Use --source corpus --limit 200 for discovery.
Missing/blocked abstracts are reported explicitly, never generated.
"""
import argparse
from datetime import datetime,timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib import request,parse,error

from voyage_pipeline import ROOT,read_records,atomic_json


class AbstractParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0;self.capture=False;self.parts=[];self.meta='';self.stop_on_p=False
    def handle_starttag(self,tag,attrs):
        attrs={k:(v or '') for k,v in attrs}
        if tag=='meta' and attrs.get('name','').lower()=='citation_abstract':
            self.meta=attrs.get('content','')
        classes=attrs.get('class','').split()
        is_abstract=(tag=='blockquote' and 'abstract' in classes) or ('acl-abstract' in classes) or ('paper-abstract' in classes) or attrs.get('id')=='abstract'
        if self.capture and tag not in ['meta','br','img','hr','input','link']:
            self.depth+=1
        elif is_abstract and not self.parts:
            self.capture=True;self.depth=1;self.stop_on_p='paper-abstract' in classes
    def handle_endtag(self,tag):
        if self.capture:
            if self.stop_on_p and tag=='p':self.capture=False;return
            self.depth-=1
            if self.depth<=0:self.capture=False
    def handle_data(self,data):
        if self.capture:self.parts.append(data)
    def text(self):
        text=' '.join((self.meta or ' '.join(self.parts)).split())
        return re.sub(r'^Abstract\s*:?\s*','',text,flags=re.I).strip()


def source_request(url):
    parsed=parse.urlparse(url);host=parsed.hostname or ''
    if host in ['openreview.net','www.openreview.net']:
        note=parse.parse_qs(parsed.query).get('id',[''])[0]
        if not note:raise ValueError('Missing OpenReview note ID')
        return 'https://api2.openreview.net/notes?id='+parse.quote(note), 'openreview'
    if host not in ['arxiv.org','www.arxiv.org','aclanthology.org','proceedings.mlr.press','papers.nips.cc','papers.neurips.cc','proceedings.neurips.cc']:
        raise ValueError('No reviewed abstract adapter for this source host')
    return url, 'html'


def fetch(url):
    endpoint,kind=source_request(url)
    headers={'User-Agent':'PaperEvolve/0.1 (public scientific metadata; local research pilot)'}
    try:
        with request.urlopen(request.Request(endpoint,headers=headers),timeout=45) as response:
            raw=response.read().decode('utf-8','replace')
    except error.HTTPError as exc:
        # Older OpenReview notes may only exist on API v1.
        if kind!='openreview' or exc.code not in [400,404]:raise
        endpoint=endpoint.replace('api2.openreview.net','api.openreview.net')
        with request.urlopen(request.Request(endpoint,headers=headers),timeout=45) as response:raw=response.read().decode('utf-8','replace')
    if kind=='openreview':
        notes=json.loads(raw).get('notes',[])
        abstract=notes[0].get('content',{}).get('abstract','') if notes else ''
        if isinstance(abstract,dict):abstract=abstract.get('value','')
        text=' '.join(abstract.split())
    else:
        parser=AbstractParser();parser.feed(raw);text=parser.text()
    if len(text)<40:raise ValueError('Abstract not present in the reviewed page markup')
    return text,endpoint


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',choices=['research','corpus'],default='research')
    parser.add_argument('--limit',type=int,default=200)
    parser.add_argument('--delay',type=float,default=1.5)
    parser.add_argument('--cache',default=str(ROOT/'work/abstracts/cache.sqlite3'))
    parser.add_argument('--output',default=str(ROOT/'work/abstracts/papers.jsonl'))
    parser.add_argument('--write-research',action='store_true',help='Add fetched abstracts/provenance to the curated research JSON')
    args=parser.parse_args(argv)
    if args.limit<1 or args.delay<1:parser.error('Limit must be positive; delay must be at least one second.')
    if args.write_research and args.source!='research':parser.error('--write-research applies only to the curated slice.')
    records=read_records(args.source,limit=args.limit)
    Path(args.cache).parent.mkdir(parents=True,exist_ok=True)
    cache=sqlite3.connect(args.cache)
    cache.execute('CREATE TABLE IF NOT EXISTS abstracts(url TEXT PRIMARY KEY, abstract TEXT, retrieved_at TEXT, endpoint TEXT)')
    output=[];missing=[];requests=0
    for record in records:
        url=record['source_url'];saved=cache.execute('SELECT abstract,retrieved_at,endpoint FROM abstracts WHERE url=?',(url,)).fetchone()
        if saved:
            abstract,date,endpoint=saved
        else:
            if requests:time.sleep(args.delay)
            requests+=1
            try:abstract,endpoint=fetch(url)
            except (ValueError,OSError,error.URLError,json.JSONDecodeError) as exc:
                missing.append({'id':record['id'],'source_url':url,'status':'unavailable','reason':str(exc)[:160]})
                print(f"Missing abstract: {record['id']}",flush=True);continue
            date=datetime.now(timezone.utc).isoformat()
            cache.execute('INSERT OR REPLACE INTO abstracts VALUES (?,?,?,?)',(url,abstract,date,endpoint));cache.commit()
        output.append({'id':record['id'],'title':record['title'],'source_url':url,'year':record['year'],'abstract':abstract,
                       'abstract_source_url':endpoint,'abstract_retrieved_at':date})
        print(f"Abstract ready: {record['id']}",flush=True)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in output));temporary.replace(path)
    atomic_json(path.with_suffix('.report.json'),{'requested':len(records),'with_abstracts':len(output),'missing':missing,'http_requests':requests})
    if args.write_research:
        research_path=ROOT/'evolve/research.json';research=json.loads(research_path.read_text());lookup={r['id']:r for r in output}
        for paper in research['papers']:
            if paper['id'] in lookup:
                row=lookup[paper['id']]
                for key in ['abstract','abstract_source_url','abstract_retrieved_at']:paper[key]=row[key]
        atomic_json(research_path,research)
    cache.close()
    print(f"{len(output)}/{len(records)} abstracts ready. Output: {path}")

if __name__=='__main__':main()
