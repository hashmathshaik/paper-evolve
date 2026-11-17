"""Recover real abstracts from public OpenReview mirrors by exact note ID + title.
Run with .venv-voyage/bin/python (pyarrow). No model-generated abstracts, no paid calls.
Each dataset revision, downloaded file hash and accepted source is recorded locally.
"""
import argparse,fcntl,gzip,hashlib,json,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path
from urllib import request,parse,error
import pyarrow.parquet as pq
from voyage_pipeline import ROOT,read_records,atomic_json
from recover_openalex import normalize,note_id

WORK=ROOT/'work/mirror-recovery'
SOURCES=[('yufan/top-conference-papers',f'ICLR/{y}-00000-of-00001.parquet') for y in (2026,2025,2024)]
SOURCES += [('Wutaghost/LLMscore-ICLR-OpenReview',f'data/ICLR_{y}/papers.jsonl.gz') for y in (2023,2024,2025)]
SOURCES += [('ai-conferences/ICLR'+str(y),'data/train-00000-of-00001.parquet') for y in range(2018,2024)]
SOURCES += [('Jasonpicky/openreview_raw',f'data/train-{i:05d}-of-00006.parquet') for i in range(6)]

def get(url):
    for attempt in range(4):
        try:
            with request.urlopen(request.Request(url,headers={'User-Agent':'PaperEvolve/0.1 (abstract recovery)'}),timeout=90) as r:return r.read()
        except (error.URLError,TimeoutError,OSError):
            if attempt==3:raise
            time.sleep(2**attempt)

def candidate(row):
    url=row.get('source_url') or row.get('openreview_url') or row.get('paper_url') or row.get('forum_url') or ''
    identity=note_id(url) or row.get('forum_id') or row.get('paper_id')
    return identity,row.get('title') or row.get('forum_title') or '',row.get('abstract') or row.get('forum_abstract') or ''

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--small-only',action='store_true');args=ap.parse_args()
    WORK.mkdir(parents=True,exist_ok=True);lock=(WORK/'worker.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Mirror recovery is already running.')
    records=read_records('corpus');by_id={note_id(r['source_url']):r for r in records if note_id(r['source_url'])}
    db=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60)
    db.execute('CREATE TABLE IF NOT EXISTS mirror_provenance(url TEXT PRIMARY KEY, dataset TEXT, revision TEXT, file_sha256 TEXT, match_method TEXT)');db.commit()
    have={r[0] for r in db.execute('SELECT url FROM abstracts')};initial=len(have);recovered=0;revisions={}
    def status(phase,source=None):
        report={'phase':phase,'initial_cached':initial,'recovered_this_run':recovered,'available':sum(r['source_url'] in have for r in records),'total':len(records),'source':source,'updated_at':datetime.now(timezone.utc).isoformat()}
        atomic_json(WORK/'status.json',report);print(json.dumps(report),flush=True)
    for repo,name in SOURCES:
        if args.small_only and repo=='Jasonpicky/openreview_raw':break
        if all(r['source_url'] in have for r in by_id.values()):break
        status('downloading',repo+'/'+name)
        if repo not in revisions:revisions[repo]=json.loads(get('https://huggingface.co/api/datasets/'+repo))['sha']
        revision=revisions[repo];endpoint='https://huggingface.co/datasets/'+repo+'/resolve/'+revision+'/'+name
        target=WORK/(hashlib.sha256(endpoint.encode()).hexdigest()+Path(name).suffix)
        if not target.exists():
            body=get(endpoint);temp=target.with_suffix('.tmp');temp.write_bytes(body);temp.replace(target)
        sha=hashlib.sha256(target.read_bytes()).hexdigest()
        if name.endswith('.parquet'):
            parquet=pq.ParquetFile(target)
            cols=[c for c in parquet.schema.names if c in ['title','abstract','source_url','openreview_url','paper_url','forum_url','forum_id','paper_id','forum_title','forum_abstract']]
            batches=(b.to_pylist() for b in parquet.iter_batches(batch_size=2000,columns=cols))
        else:batches=([json.loads(line) for line in gzip.decompress(target.read_bytes()).decode().splitlines() if line],)
        # Collect unique abstracts for each identity before accepting; duplicated reviews may disagree.
        candidates={}
        for batch in batches:
            for row in batch:
                identity,title,text=candidate(row);record=by_id.get(identity)
                if not record or record['source_url'] in have or not isinstance(text,str) or len(text.strip())<40:continue
                if normalize(title)!=normalize(record['title']):continue
                text=' '.join(text.split());candidates.setdefault(identity,set()).add(text)
        for identity,texts in candidates.items():
            if len(texts)!=1:continue
            record=by_id[identity];url=record['source_url'];text=next(iter(texts))
            result=db.execute('INSERT OR IGNORE INTO abstracts VALUES (?,?,?,?)',(url,text,datetime.now(timezone.utc).isoformat(),endpoint))
            if result.rowcount:
                db.execute('INSERT OR REPLACE INTO mirror_provenance VALUES (?,?,?,?,?)',(url,repo,revision,sha,'exact_openreview_id_and_title'));db.execute('DELETE FROM failures WHERE url=?',(url,));recovered+=1
            have.add(url)
        db.commit();status('source_complete',repo+'/'+name)
    status('complete')

if __name__=='__main__':main()
