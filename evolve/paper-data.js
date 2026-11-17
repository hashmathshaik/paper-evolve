/** Shared static data access. Selecting a paper never starts a model/API job. */
let corpusPromise=null,indexPromise=null,metaPromise=null;
const shards=new Map();
async function json(path){const response=await fetch(path);if(!response.ok)throw new Error(`Local file unavailable: ${response.status}`);return response.json()}
export function loadCorpus(){
 if(!corpusPromise)corpusPromise=json('evolve/corpus.json').catch(error=>{corpusPromise=null;throw error});
 return corpusPromise;
}
async function urlIndex(){
 if(!indexPromise)indexPromise=loadCorpus().then(rows=>new Map(rows.map((p,i)=>[p.u,i]))).catch(error=>{indexPromise=null;throw error});
 return indexPromise;
}
export function paperRecord(p){
 return {title:p.title||p.t||p.name||'Untitled paper',year:p.year||p.y,venue:p.venue||p.v||'',
  source_url:p.source_url||p.u||'',topic:p.topic||'',area:p.mega||'',leaf:p.leaf||'',
  authors:p.computed?'':p.authors||'',abstract:p.abstract||'',
  abstract_source_url:p.abstract_source_url||'',abstract_retrieved_at:p.abstract_retrieved_at||''};
}
export async function readPaper(p){
 const record=paperRecord(p);
 if(record.abstract.trim())return record;
 const index=await urlIndex(),i=index.get(record.source_url);
 if(i===undefined)return {...record,abstract:null};
 if(!metaPromise)metaPromise=json('evolve/generated/abstracts/meta.json').catch(error=>{metaPromise=null;throw error});
 const meta=await metaPromise,k=Math.floor(i/meta.shard_size);
 if(!shards.has(k))shards.set(k,json(`evolve/generated/abstracts/${String(k).padStart(3,'0')}.json`).catch(error=>{shards.delete(k);throw error}));
 const rows=await shards.get(k),saved=rows[i%meta.shard_size];
 if(saved?.url!==record.source_url)throw new Error('Paper content index is out of date.');
 return {...record,abstract:saved.abstract,abstract_source_url:saved.source_url,abstract_retrieved_at:saved.retrieved_at};
}
export const venueName=value=>({neurips:'NeurIPS',icml:'ICML',iclr:'ICLR',acl:'ACL',emnlp:'EMNLP',naacl:'NAACL',preprint:'Preprint'}[String(value).toLowerCase()]||value);
