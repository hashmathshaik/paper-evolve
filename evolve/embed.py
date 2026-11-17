"""Reproducible dependency-free sparse TF-IDF embeddings, not a neural model.
Similarity is stored separately and NEVER promoted to influence evidence.
"""
import json,math,re
from collections import Counter
from pathlib import Path
path=Path(__file__).with_name('research.json');d=json.loads(path.read_text())
stop=set('a an the of and to for with in by from across as using its use'.split())
texts={p['id']:p['title']+' '+ ' '.join(c['label'] for c in d['contributions'] if c['paper_id']==p['id']) for p in d['papers']}
tokens={id:Counter(w for w in re.findall(r'[a-z]+',text.lower()) if w not in stop) for id,text in texts.items()}
vectors={id:{w:tf*(math.log((1+len(tokens))/(1+sum(w in t for t in tokens.values())))+1) for w,tf in t.items()} for id,t in tokens.items()}
for v in vectors.values():
 norm=math.sqrt(sum(x*x for x in v.values()))
 for w in v:v[w]/=norm
pairs=[]
for i,a in enumerate(vectors):
 for b in list(vectors)[i+1:]:
  shared=set(vectors[a])&set(vectors[b]);score=sum(vectors[a][w]*vectors[b][w] for w in shared)
  pairs.append(dict(id='sim-'+a+'-'+b,a=a,b=b,score=round(score,4),terms=sorted(shared,key=lambda w:-vectors[a][w]*vectors[b][w])[:5],method='tfidf-cosine'))
# Union of each paper's closest neighbor keeps the discovery graph sparse.
chosen={}
for id in vectors:
 best=max((p for p in pairs if id in [p['a'],p['b']]),key=lambda p:p['score']);chosen[best['id']]=best
d['similarities']=list(chosen.values());path.write_text(json.dumps(d,indent=2)+'\n')
print(f"Embedded {len(vectors)} papers; {len(chosen)} separate similarity links")
