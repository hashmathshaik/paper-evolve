"""Exact cosine top-K neighbours over all cached Voyage vectors (voyage-4-large, 2048-d).
Run with .venv-voyage/bin/python (needs numpy). Writes work/edges/knn.npz.
"""
import sqlite3,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
from voyage_pipeline import ROOT,read_records

K=10;BLOCK=2048;OUT=ROOT/'work/edges';OUT.mkdir(parents=True,exist_ok=True)
SEED=0;np.random.seed(SEED);print('seed',SEED,'K',K,'block',BLOCK)

corpus={r['id']:r for r in read_records('corpus')}
db=sqlite3.connect(ROOT/'work/voyage/cache.sqlite3')
latest={}
for pid,blob in db.execute("SELECT paper_id,vector FROM vectors WHERE dimension=2048 AND json_extract(metadata,'$.model')='voyage-4-large' ORDER BY rowid"):
 if pid in corpus:latest[pid]=blob
rows=list(latest.items())
del latest
ids=np.array([pid for pid,_ in rows])
X=np.frombuffer(b''.join(b for _,b in rows),dtype='<f4').reshape(len(rows),-1).copy()  # (N, 2048)
del rows
X/=np.linalg.norm(X,axis=1,keepdims=True)
N=len(X);print('papers',N,'dim',X.shape[1])

idx=np.empty((N,K),dtype=np.int32);sim=np.empty((N,K),dtype=np.float32);t=time.time()
for s in range(0,N,BLOCK):
 S=X[s:s+BLOCK]@X.T  # (B, N)
 S[np.arange(len(S)),np.arange(s,s+len(S))]=-np.inf  # drop self
 part=np.argpartition(-S,K,axis=1)[:,:K]  # (B, K) unordered
 ps=np.take_along_axis(S,part,1);o=np.argsort(-ps,1)
 idx[s:s+BLOCK]=np.take_along_axis(part,o,1);sim[s:s+BLOCK]=np.take_along_axis(ps,o,1)
 if s//BLOCK%8==0:print(f'{s+len(S)}/{N} rows, {time.time()-t:.0f}s',flush=True)
print(f'done {time.time()-t:.0f}s')

temporary=OUT/'knn.pending.npz'
np.savez(temporary,ids=ids,idx=idx,sim=sim)
temporary.replace(OUT/'knn.npz')
q=np.percentile(sim[:,0],[5,25,50,75,95]);q10=np.percentile(sim[:,-1],[5,50,95])
print('top-1 sim percentiles 5/25/50/75/95:',np.round(q,3))
print('10th-neighbour sim percentiles 5/50/95:',np.round(q10,3))
indeg=np.bincount(idx.ravel(),minlength=N);print('in-degree max',indeg.max(),'| papers never a neighbour',int((indeg==0).sum()))
mutual=sum(1 for i in range(N) for j in idx[i] if i in idx[j]);print('mutual directed pairs',mutual,'of',N*K)
