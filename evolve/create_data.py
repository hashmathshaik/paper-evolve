import json
from pathlib import Path
rows=[
('cachegen','CacheGen','KV Cache Compression and Streaming for Fast Large Language Model Serving','2310.07240',2023,'2023-10-11','Liu et al.','Store & stream','Compress cached context for bandwidth-adaptive loading.',0,0),
('prompt','Prompt Cache','Modular Attention Reuse for Low-Latency Inference','2311.04934',2023,'2023-11-07','Gim et al.','Modular reuse','Define reusable prompt modules with position-aware attention states.',0,1),
('sglang','SGLang','Efficient Execution of Structured Language Model Programs','2312.07104',2023,'2023-12-12','Zheng et al.','Prefix sharing','Use RadixAttention to reuse KV cache across structured generation calls.',0,2),
('hydragen','Hydragen','High-Throughput LLM Inference with Shared Prefixes','2402.05099',2024,'2024-02-07','Juravsky et al.','Prefix sharing','Separate shared-prefix attention from unique suffixes to improve batched decoding.',1,2),
('blend','CacheBlend','Fast Large Language Model Serving for RAG with Cached Knowledge Fusion','2405.16444',2024,'2024-05-26','Yao et al.','Reuse & repair','Selectively recompute cached tokens to restore cross-chunk attention.',1,1),
('preble','Preble','Efficient Distributed Prompt Scheduling for LLM Serving','2407.00023',2024,'2024-05-08','Srivatsa et al.','Prefix sharing','Schedule distributed requests by balancing reuse and GPU load.',2,2),
('kvlink','KVLink','Accelerating Large Language Models via Efficient KV Cache Reuse','2502.16002',2025,'2025-02-21','Yang et al.','Reuse & repair','Reconnect independently encoded documents using trainable link tokens.',3,1)]
papers=[]; contributions=[]
for id,name,title,arxiv,year,date,authors,branch,summary,col,lane in rows:
 papers.append(dict(id=id,name=name,title=name+': '+title,arxiv_id=arxiv,year=year,date=date,authors=authors,venue='Preprint',venue_verified=False,source_url='https://arxiv.org/abs/'+arxiv,versions=[dict(id=arxiv,kind='preprint')],retrieved_at='2026-11-11',updated_at='2026-11-11',branch=branch,col=col,lane=lane))
 contributions.append(dict(id=id+'-c1',paper_id=id,label=summary))
def edge(id,a,b,type,status,inherited,changed,motivation,url,section,passage=None):
 return dict(id=id,source=a+'-c1',target=b+'-c1',type=type,status=status,inherited=inherited,changed=changed,motivation=motivation,evidence=[dict(url=url,section=section,passage=passage)],historical=True)
edges=[
edge('modular-repair','prompt','blend','Extends','explicit','Independently precomputed KV states for reusable text chunks.','Recompute selected tokens to recover cross-chunk attention.','Full reuse omits attention to earlier chunks.','https://arxiv.org/html/2405.16444v2#S1','Introduction; Figure 1','this method ignores the important cross-attention'),
edge('learned-repair','blend','kvlink','Challenges','explicit','Reuse independently encoded document caches.','Use positional re-encoding and learned link tokens rather than selective token repair.','KVLink reports quality degradation and recomputation costs for CacheBlend.','https://arxiv.org/html/2502.16002v1#S4','Related work, KV cache reuse','the non-trivial cost of recomputing 10%–20% of tokens'),
edge('distributed','sglang','preble','Extends','explicit','SGLang as a serving backend with prefix reuse.','Add a distributed scheduler balancing reuse and load.','Single-device reuse does not address distributed scheduling.','https://escholarship.org/uc/item/1bm0k1w0','Implementation, §5.1','we currently support vLLM [21] and SGLang [64] as two backends.'),
edge('stream-fusion','cachegen','blend','Combines','inferred','Stored KV caches can avoid repeated context computation.','Overlap retrieval with selective recomputation.','Cache transfer can be overlapped with repair; direct inheritance is not established.','https://arxiv.org/html/2405.16444v2#S1','Introduction; conceptual interpretation only'),
]
Path(__file__).with_name('research.json').write_text(json.dumps(dict(topic='KV-cache reuse & repair',coverage='Curated research slice · 7 papers · not a field survey',papers=papers,contributions=contributions,edges=edges),indent=2))
