import {paragraphsHTML,readableText} from './text-format.js?v=3b080bf0551b';
import {renderMath} from './math.js?v=3b080bf0551b';
import {paperRecord,readPaper,venueName} from './paper-data.js?v=3b080bf0551b';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL=value=>/^https?:\/\//i.test(value||'')?value:'';
const metadata=p=>[p.year,venueName(p.venue)].filter(Boolean).map(esc).join(' <span aria-hidden="true">·</span> ');
const evidenceLabel=edge=>edge.model?(edge.status==='source_supported'?'Passage-supported prediction':'Abstract-based prediction'):'Example interpretation';
const typeLabel=edge=>Object.keys(edge.types||{}).join(' · ')||edge.type;

/** One paper-reading experience shared by the graph, search and library. */
export function createPaperReader({container,onEvolution,onSelectPaper,onConnection}){
 let generation=0;
 function begin(label){
  const current=++generation;document.getElementById('details-title').textContent=label;
  const reset=()=>container.scrollTo({top:0,behavior:'instant'});
  reset();requestAnimationFrame(()=>{if(current===generation)reset()});
  return current;
 }
 function paperButton(record,label){const p=paperRecord(record);return `<button class="reader-paper-link" data-reader-paper="${esc(record.id||p.source_url)}"><small>${esc(label)} · ${metadata(p)}</small><strong>${esc(readableText(p.title))}</strong><span>Read abstract →</span></button>`}
 function wirePapers(records){
  container.querySelectorAll('[data-reader-paper]').forEach(button=>button.onclick=()=>{
   const record=records.find(p=>(p.id||paperRecord(p).source_url)===button.dataset.readerPaper);if(record)onSelectPaper(record);
  });
 }
 function showPaper(record,context={}){
  const current=begin('Paper details'),p=paperRecord(record),connections=context.connections||[];
  container.innerHTML=`<article class="paper-reader" aria-labelledby="reader-title">
   <div class="reader-meta">${metadata(p)}</div>
   <h2 id="reader-title">${esc(readableText(p.title))}</h2>
   ${p.authors?`<p class="reader-authors">${esc(Array.isArray(p.authors)?p.authors.join(', '):p.authors)}</p>`:''}
   <div class="reader-actions"><a class="reader-source" href="${esc(safeURL(p.source_url))}" target="_blank" rel="noopener">Read paper ↗</a><button class="reader-evolution">Explore evolution →</button></div>
   <section class="reader-section" aria-labelledby="abstract-heading"><h3 id="abstract-heading">Abstract</h3><div class="reader-abstract" aria-busy="true"><p class="reader-loading" role="status">Loading abstract…</p></div></section>
   ${context.contributions?.length?`<section class="reader-section"><h3>Contribution in this map</h3>${context.contributions.map(text=>`<p>${esc(text)}</p>`).join('')}</section>`:''}
   <section class="reader-section"><h3>Research connections${connections.length?` <span>${connections.length}</span>`:''}</h3>
    ${connections.map(e=>`<button class="reader-connection" data-reader-connection="${esc(e.id)}"><span class="connection-type">${esc(typeLabel(e))}</span><span>${esc(e.sourceTitle)} <span aria-hidden="true">→</span> ${esc(e.targetTitle)}</span><small>${evidenceLabel(e)}</small></button>`).join('')||(context.connections===undefined?'<p class="reader-empty">Explore evolution to inspect this paper’s available connections and similar work.</p>':'<p class="reader-empty">No connections match the current view. Try another evidence filter or explore similar papers.</p>')}
   </section>
   ${context.branchAction?'<button class="reader-branch"></button>':''}
   ${[p.topic,p.area,p.leaf!=='Unclustered'?p.leaf:''].filter(Boolean).length?`<details class="reader-provenance"><summary>Topics and source</summary><p>${[p.area,p.topic,p.leaf!=='Unclustered'?p.leaf:''].filter(Boolean).map(esc).join('<br>')}</p><div class="abstract-provenance"></div></details>`:'<details class="reader-provenance"><summary>Abstract source</summary><div class="abstract-provenance"></div></details>'}
  </article>`;
  container.querySelector('.reader-evolution').onclick=async event=>{
   const button=event.currentTarget;button.disabled=true;button.textContent='Loading evolution…';
   try{await onEvolution({t:p.title,u:p.source_url})}
   finally{if(container.contains(button)){button.disabled=false;button.textContent='Explore evolution →'}}
  };
  container.querySelectorAll('[data-reader-connection]').forEach(button=>button.onclick=()=>onConnection(button.dataset.readerConnection));
  if(context.branchAction){const button=container.querySelector('.reader-branch');button.textContent=context.branchAction.label;button.onclick=context.branchAction.run}
  const target=container.querySelector('.reader-abstract'),provenance=container.querySelector('.abstract-provenance');
  async function load(){
   target.setAttribute('aria-busy','true');
   try{
    const full=await readPaper(record);
    if(current!==generation||!container.contains(target))return;
    target.innerHTML=full.abstract?paragraphsHTML(full.abstract):'<p class="reader-empty">An abstract is not available for this record. Open the paper to read the original.</p>';
    renderMath(target);
    const url=safeURL(full.abstract_source_url),date=full.abstract_retrieved_at?.slice(0,10);
    provenance.innerHTML=(url?`<a href="${esc(url)}" target="_blank" rel="noopener">Abstract source ↗</a>`:'')+(date?`<p>Retrieved ${esc(date)}</p>`:'');
   }catch{
    if(current!==generation||!container.contains(target))return;
    target.innerHTML='<p class="reader-empty">The abstract could not be loaded.</p><button class="reader-retry">Try again</button>';
    target.querySelector('button').onclick=()=>{target.innerHTML='<p class="reader-loading" role="status">Loading abstract…</p>';load()};
   }finally{if(current===generation&&container.contains(target))target.setAttribute('aria-busy','false')}
  }
  renderMath(container.querySelector('#reader-title'));load();
 }
 function showRelation(edge,earlier,later){
  begin('Connection details');
  const isPrediction=Boolean(edge.model),evidence=edge.evidence||[];
  container.innerHTML=`<article class="connection-reader"><div class="reader-meta">${esc(typeLabel(edge))}</div><h2>How the idea changed</h2>
   <div class="reader-endpoints">${paperButton(earlier,'Earlier paper')}<div class="reader-direction" aria-hidden="true">↓</div>${paperButton(later,'Later paper')}</div>
   <section class="reader-section"><h3>What was retained</h3><p>${esc(edge.inherited)}</p></section>
   <section class="reader-section"><h3>What changed</h3><p>${esc(edge.changed)}</p></section>
   ${edge.motivation?`<section class="reader-section"><h3>Why they are connected</h3><p>${esc(edge.motivation)}</p></section>`:''}
   <section class="reader-section"><h3>Supporting evidence</h3>${evidence.length?evidence.map(item=>`<div class="reader-evidence">${item.passage?`<blockquote>${esc(item.passage)}</blockquote>`:'<p class="reader-empty">No supporting passage is attached to this connection.</p>'}${safeURL(item.url)?`<a href="${esc(item.url)}" target="_blank" rel="noopener">Read source ↗</a>`:''}${item.section?`<small>${esc(item.section)}</small>`:''}</div>`).join(''):'<p class="reader-empty">No supporting passage is available.</p>'}</section>
   <details class="reader-provenance"><summary>About this connection</summary><p>${edge.communityReview?(edge.humanVerified?'Community submission reviewed by a human maintainer.':'Community submission checked by an AI assistant; not human-reviewed.'):isPrediction?'This is a model prediction, not a human-reviewed fact.':'This connection is part of the curated research example.'}</p>${edge.verification?`<p>Agreed by ${esc(edge.verification.proposal_model)} and ${esc(edge.verification.review_model)} using separate source reviews. Model agreement is not calibrated accuracy.</p>`:''}${edge.communityReview?`<p>Contributor: ${esc(edge.communityReview.contributor.name)}<br>Reviewer: ${esc(edge.communityReview.reviewer)}</p><p>${esc(edge.communityReview.note)}</p>`:''}${isPrediction?`<p>${esc(edge.model)} · ${esc(edge.basis?.replaceAll('_',' '))}<br>Self-assessed confidence: ${Number(edge.confidence).toFixed(2)}. This is not calibrated accuracy.</p>`:''}</details>
  </article>`;
  wirePapers([earlier,later]);renderMath(container.querySelector('.reader-endpoints'));
 }
 function showSimilarity(link,a,b){
  begin('Similar papers');
  container.innerHTML=`<article class="connection-reader"><div class="reader-meta">Conceptual similarity</div><h2>Related ideas</h2><p>These papers discuss related ideas. Similarity does not establish influence or an evolution relationship.</p><div class="reader-endpoints">${paperButton(a,'Selected paper')}${paperButton(b,'Similar paper')}</div>${Number.isFinite(link.score)?`<p class="reader-empty">Semantic similarity: ${link.score.toFixed(2)}</p>`:''}</article>`;
  wirePapers([a,b]);renderMath(container.querySelector('.reader-endpoints'));
 }
 return {showPaper,showRelation,showSimilarity,cancel:()=>{generation++}};
}
