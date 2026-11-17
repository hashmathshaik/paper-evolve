"""Check abstract provenance and exact-text/model embedding coverage for every corpus paper."""
import json,sqlite3
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
from voyage_pipeline import ROOT,read_records,digest,atomic_json,cache_key,load_config

def main():
    papers=read_records('corpus');config=load_config(ROOT/'config/voyage.json')
    with sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3') as db:
        abstracts={u:(a,t,s) for u,a,t,s in db.execute('SELECT url,abstract,retrieved_at,endpoint FROM abstracts')}
    with sqlite3.connect(ROOT/'work/voyage/cache.sqlite3') as db:keys={r[0] for r in db.execute('SELECT key FROM vectors')}
    rows=[];problems=[];sources=Counter();ready=0
    for p in papers:
        saved=abstracts.get(p['source_url']);valid=False;embedded=False
        if saved:
            text,date,source=saved;valid=len(text.strip())>=40 and source.startswith('https://') and bool(date)
            record={**p,'text_hash':digest(p['title'].strip()+'\n\nAbstract:\n'+text.strip())}
            embedded=cache_key(record,config) in keys;sources[urlparse(source).hostname]+=1
        if not valid or not embedded:problems.append({'id':p['id'],'abstract_valid':valid,'embedding_current':embedded})
        ready+=embedded
        rows.append({'id':p['id'],'source_url':p['source_url'],'abstract_sha256':digest(saved[0]) if saved else None,'abstract_source_url':saved[2] if saved else None,'abstract_valid':valid,'embedding_current':embedded})
    out=ROOT/'work/abstracts/audit.jsonl';out.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    report={'total':len(papers),'abstracts':sum(r['abstract_valid'] for r in rows),'embeddings':ready,'model':config['model'],'dimensions':config['output_dimension'],'problems':problems,'abstract_sources':dict(sources),'updated_at':datetime.now(timezone.utc).isoformat()}
    atomic_json(ROOT/'work/abstracts/audit.json',report);atomic_json(ROOT/'evolve/generated/coverage.json',report)
    print(json.dumps({**report,'problems':len(problems)}))
    if problems:raise SystemExit(1)

if __name__=='__main__':main()
