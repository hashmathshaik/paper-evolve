/** Static retrieval boundary. API credentials and embedding computation never run here. */
async function textHash(text){const bytes=new TextEncoder().encode(JSON.stringify(text));return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('')}
export class LocalResearchProvider {
 async load(){
  const r=await fetch('evolve/research.json');if(!r.ok)throw new Error(`Research HTTP ${r.status}`);const data=await r.json();
  // Optional precomputed Voyage output. Keep the lexical baseline if absent or stale.
  try{const response=await fetch('evolve/generated/similarities.json');if(response.ok){const generated=await response.json();const ids=new Set(data.papers.map(p=>p.id));let valid=generated.model?.model==='voyage-4-large'&&Object.keys(generated.text_hashes||{}).length===ids.size;
   for(const p of data.papers){let text=p.title;const abstract=(p.abstract||'').trim();if(abstract)text+='\n\nAbstract:\n'+abstract;const summaries=data.contributions.filter(c=>c.paper_id===p.id).map(c=>c.label);if(summaries.length)text+='\n\nCurated contributions:\n'+summaries.join('\n');if(await textHash(text)!==generated.text_hashes[p.id])valid=false;}
   if(valid&&Array.isArray(generated.similarities)&&generated.similarities.every(e=>ids.has(e.a)&&ids.has(e.b)&&Number.isFinite(e.score))){data.similarities=generated.similarities;data.embedding_model=generated.model.model;}
  }}catch{/* Optional artifact unavailable: show the existing baseline. */}
  return data;
 }
 async search(query){const d=await this.load();return d.papers.filter(p=>p.title.toLowerCase().includes(query.toLowerCase()))}
 async read(id){const d=await this.load();return d.papers.find(p=>p.id===id)??null}
}
