import {loadCorpus} from './paper-data.js?v=f7986b19491c';
/** Static Model predictions and Voyage similarity. References alone never imply evolution. */
const VENUE={neurips:'NeurIPS',icml:'ICML',iclr:'ICLR',acl:'ACL',emnlp:'EMNLP',naacl:'NAACL'};
const SHOW=.85;let corpus=null,byUrl=null,meta=null,community=null;const shards=new Map();
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`${url}: HTTP ${r.status}`);return r.json()}
async function load(){if(!corpus){corpus=await loadCorpus();byUrl=new Map(corpus.map((p,i)=>[p.u,i]))}if(!meta)meta=await json('evolve/generated/edges/meta.json');if(!community)community=await json('evolve/generated/community.json')}
async function entry(i){const k=Math.floor(i/meta.shard_size);if(!shards.has(k))shards.set(k,json(`evolve/generated/edges/${String(k).padStart(3,'0')}.json`).catch(error=>{shards.delete(k);throw error}));const raw=(await shards.get(k))[i]||{c:[],s:[]},extra=community.entries[i];if(!extra)return raw;return {...raw,c:[...raw.c.filter(row=>!extra.overrides.includes(row[0])),...extra.c],checked:(raw.checked||0)+extra.checked}}
const shortName=t=>{const head=t.split(/:\s/)[0];return head.length<=36?head:t.slice(0,34).trim()+'…'};
const primary=types=>Object.entries(types).filter(([k,p])=>['Extends','Challenges','Combines','Transfers','Revives'].includes(k)&&p>=SHOW).sort((a,b)=>b[1]-a[1]);
export async function buildNeighbourhood(record){
 await load();const focus=byUrl.get(record.u);if(focus===undefined)return null;
 const raw=await entry(focus);
 const predictions=raw.c.map(([o,dir,types,r,inh,chg,sentence,mode,info])=>({o,dir,types,r,inh,chg,sentence,mode,info})).filter(e=>['historical_model','qwen','modelstudio','community'].includes(e.mode)&&e.info&&primary(e.types).length);
 const pick=(dir,n)=>predictions.filter(e=>e.dir===dir).sort((a,b)=>Number(b.info.quality_tier==='fulltext_supported_prediction')-Number(a.info.quality_tier==='fulltext_supported_prediction')||b.r-a.r).slice(0,n);
 const ancestors=pick(-1,4),descendants=pick(1,6),chosen=[...ancestors,...descendants];
 const used=new Set([focus,...chosen.map(e=>e.o)]),similar=raw.s.filter(([o])=>!used.has(o)).slice(0,3);
 const indices=[focus,...chosen.map(e=>e.o),...similar.map(([o])=>o)];
 const years=[...new Set(indices.map(i=>corpus[i].y))].sort((a,b)=>a-b),lanes=new Map();
 const papers=[],contributions=[],edges=[],similarities=[];
 const add=(i,branch,label)=>{const p=corpus[i],id='p'+i,col=years.indexOf(p.y),lane=lanes.get(col)||0;lanes.set(col,lane+1);papers.push({id,idx:i,name:shortName(p.t),title:p.t,year:p.y,authors:VENUE[p.v]||p.v.toUpperCase(),venue:VENUE[p.v]||p.v,source_url:p.u,branch,col,lane,topic:p.topic,computed:true});contributions.push({id:id+'-c',paper_id:id,label});return id};
 const fid=add(focus,'This paper',corpus[focus].topic);
 chosen.sort((a,b)=>corpus[a.o].y-corpus[b.o].y).forEach(e=>add(e.o,e.dir===-1?'Earlier contribution':'Later contribution',primary(e.types).map(([k])=>k).join(' · ')));
 similar.forEach(([o,s])=>{add(o,'Similar · not influence',`Semantic similarity ${s.toFixed(2)}`);similarities.push({id:`sim-${focus}-${o}`,a:fid,b:'p'+o,score:s,method:'voyage-4-large'})});
 for(const e of chosen){const a=e.dir===-1?e.o:focus,b=e.dir===-1?focus:e.o,t=primary(e.types),info=e.info;
  edges.push({id:`relation-${a}-${b}`,source:`p${a}-c`,target:`p${b}-c`,type:t[0][0],types:e.types,status:info.quality_tier==='fulltext_supported_prediction'?'source_supported':'inferred',
   inherited:info.inherited,changed:info.changed,motivation:info.reason,
   model:info.model,basis:info.basis,confidence:e.r,communityReview:info.community_review,humanVerified:info.human_verified===true,verification:info.verification,
   evidence:info.evidence.map(v=>({url:v.url||corpus[v.source.startsWith('a_')?a:b].u,section:v.page?`Paper passage · page ${v.page}`:v.source==='citing_sentence'?'Citing sentence in the later paper':v.source==='a_abstract'?'Earlier paper abstract':'Later paper abstract',passage:v.quote})),historical:false})
 }
 return {topic:corpus[focus].t,coverage:'Evidence-backed research connections',computed:true,focus:fid,hasCommunity:chosen.some(e=>e.mode==='community'),
  columns:years.map((year,i)=>[String(year),24+i*320]),span:`${years[0]}–${years.at(-1)}`,
  width:Math.max(1320,years.length*320+40),height:Math.max(944,Math.max(...lanes.values())*278+110),
  classificationPending:!raw.checked,classificationChecked:raw.checked||0,papers,contributions,edges,similarities};
}
