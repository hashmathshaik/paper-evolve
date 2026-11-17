"""Recover missing ACL abstracts from official PDFs when HTML/XML omit them.
Needs Poppler pdftotext. Stores exact-source provenance and retains local PDF/text.
"""
import hashlib,json,re,sqlite3,subprocess
from pathlib import Path
from urllib import request
from datetime import datetime,timezone
from voyage_pipeline import ROOT

def extract(text):
    match=re.search(r'(?m)^Abstract\s*\n(.*?)\n1\s+Introduction\s*\n',text,re.S)
    if not match:raise ValueError('Unambiguous Abstract / Introduction boundaries not found')
    body=re.sub(r'(?m)^\*Equal contribution\s*\n','',match[1])
    body=re.sub(r'([a-zA-Z])-\n([a-z])',r'\1\2',body)
    return ' '.join(body.split())

def main():
    db=sqlite3.connect(ROOT/'work/abstracts/cache.sqlite3',timeout=60)
    db.execute('CREATE TABLE IF NOT EXISTS pdf_provenance(url TEXT PRIMARY KEY,pdf_url TEXT,sha256 TEXT,method TEXT)')
    have={r[0] for r in db.execute('SELECT url FROM abstracts')};saved=0
    for r in json.loads((ROOT/'evolve/corpus.json').read_text()):
        url=r['u']
        if url in have or 'aclanthology.org' not in url:continue
        endpoint=url.rstrip('/')+'.pdf';directory=ROOT/'work/abstracts/pdfs';directory.mkdir(exist_ok=True)
        path=directory/(url.rstrip('/').split('/')[-1]+'.pdf')
        if not path.exists():
            with request.urlopen(endpoint,timeout=60) as response:path.write_bytes(response.read())
        result=subprocess.run(['pdftotext','-f','1','-l','1','-raw',str(path),'-'],check=True,capture_output=True,text=True)
        abstract=extract(result.stdout)
        # Verified against the published first page: preserve the superscript exponent.
        if path.stem=='2025.naacl-long.514':abstract=abstract.replace('1030 sentences','10^30 sentences')
        if not 100<len(abstract)<7000:raise ValueError('Unexpected extracted abstract length')
        db.execute('INSERT OR IGNORE INTO abstracts VALUES (?,?,?,?)',(url,abstract,datetime.now(timezone.utc).isoformat(),endpoint))
        db.execute('INSERT OR REPLACE INTO pdf_provenance VALUES (?,?,?,?)',(url,endpoint,hashlib.sha256(path.read_bytes()).hexdigest(),'published_pdf_abstract_section'))
        db.execute('DELETE FROM failures WHERE url=?',(url,));db.commit();saved+=1
    print('Recovered official PDF abstracts:',saved)

if __name__=='__main__':main()
