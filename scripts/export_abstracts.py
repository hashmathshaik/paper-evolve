"""Publish cached paper abstracts as small, lazy-loaded static reader files.

No API requests. Credentials, provider responses and billing databases stay local.
"""
import json,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

ROOT=Path(__file__).resolve().parents[1]

def public_url(value):
    parts=urlsplit(value or '')
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:return ''
    # API retrieval endpoints may contain a credential in their query string.
    query=urlencode([(k,v) for k,v in parse_qsl(parts.query) if k in {'id','doi','paperId','paper_id','version'}])
    path=parts.path.replace('/resolve/','/blob/') if parts.hostname=='huggingface.co' else parts.path
    return urlunsplit(('https',parts.netloc,path,query,''))

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
    temporary.replace(path)

def export(corpus_path,cache_path,output,shard_size=500):
    records=json.loads(Path(corpus_path).read_text());output=Path(output)
    with sqlite3.connect(Path(cache_path).resolve().as_uri()+'?mode=ro',uri=True) as db:
        cached={u:(a,t,s) for u,a,t,s in db.execute('SELECT url,abstract,retrieved_at,endpoint FROM abstracts')}
    missing=[p['u'] for p in records if p['u'] not in cached or len((cached[p['u']][0] or '').strip())<40]
    if missing:raise ValueError(f'{len(missing)} papers lack a complete abstract; no files published.')
    for start in range(0,len(records),shard_size):
        rows=[]
        for record in records[start:start+shard_size]:
            abstract,date,source=cached[record['u']]
            rows.append({'url':record['u'],'abstract':abstract.strip(),
                         'source_url':public_url(source),'retrieved_at':date})
        write_json(output/f'{start//shard_size:03d}.json',rows)
    result={'version':1,'total':len(records),'abstracts':len(records),'shard_size':shard_size,
            'shards':(len(records)+shard_size-1)//shard_size,'updated_at':datetime.now(timezone.utc).isoformat()}
    write_json(output/'meta.json',result)
    return result

def main():
    print(json.dumps(export(ROOT/'evolve/corpus.json',ROOT/'work/abstracts/cache.sqlite3',ROOT/'evolve/generated/abstracts')))

if __name__=='__main__':main()
