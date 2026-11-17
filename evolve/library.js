import {loadCorpus,readPaper,venueName} from './paper-data.js?v=3b080bf0551b';
import {escapeHTML as esc,readableText} from './text-format.js?v=3b080bf0551b';
import {renderMath} from './math.js?v=3b080bf0551b';
const groupLabel=name=>name==='Unclustered'?'Uncategorized research':name;
const palette=['#547b62','#6b8396','#9a8461','#89799a'];
const groupColor=name=>{let hash=2166136261;for(const c of name)hash=Math.imul(hash^c.codePointAt(0),16777619);return palette[(hash>>>16)%palette.length]};
export function createLibrary({selectPaper,openEvolution}){
 let records=null,view='map',area='',topic='',page=0,selectedURL='',revision=0,openRevision=0;
 const $=id=>document.getElementById(id),pageSize=20;
 function filtered(){
  const words=$('library-search').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return records.filter(p=>(!$('library-year').value||p.y===+$('library-year').value)&&
   (!$('library-venue').value||p.v===$('library-venue').value)&&(!area||p.mega===area)&&(!topic||p.topic===topic)&&
   words.every(word=>`${p.t} ${p.topic} ${p.leaf} ${p.mega}`.toLowerCase().includes(word)));
 }
 function clearSearch(){ $('search').value='';$('search').dispatchEvent(new Event('input')) }
 function changePage(next){page=next;render();document.querySelector('main').scrollTop=0}
 function pagination(target,count){
  const pages=Math.max(1,Math.ceil(count/pageSize));if(pages===1){target.innerHTML='';return}
  target.innerHTML=`<span class="pagination-range">${(page*pageSize+1).toLocaleString()}–${Math.min((page+1)*pageSize,count).toLocaleString()} of ${count.toLocaleString()}</span><div class="pagination-actions"><button data-page="${page-1}" ${page===0?'disabled':''} aria-label="Previous page">← Previous</button><span>Page ${page+1} / ${pages.toLocaleString()}</span><button data-page="${page+1}" ${page+1>=pages?'disabled':''} aria-label="Next page">Next →</button></div>`;
  target.querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>changePage(+button.dataset.page));
 }
 function render(){
  if(!records)return;const current=++revision,all=filtered(),groupView=view==='map'&&!topic;
  const sort=$('library-sort').value;
  if(!groupView)all.sort(sort==='title'?(a,b)=>a.t.localeCompare(b.t):(a,b)=>(sort==='oldest'?a.y-b.y:b.y-a.y)||a.t.localeCompare(b.t));
  page=Math.min(page,Math.max(0,Math.ceil(all.length/pageSize)-1));
  const query=$('library-search').value.trim();
  $('library-title').textContent=query?'Search results':view==='map'?groupLabel(topic||area||'Research landscape'):groupLabel(topic||area||'Browse papers');
  const contributionLink=$('library-contribute');contributionLink.hidden=!topic;contributionLink.href='contribute.html?topic='+encodeURIComponent(topic);
  const groups=new Map();if(groupView)for(const p of all){const name=p[area?'topic':'mega'];if(!groups.has(name))groups.set(name,[]);groups.get(name).push(p)}
  $('library-count').textContent=`${all.length.toLocaleString()} ${all.length===1?'paper':'papers'} · ${query?'Matching “'+query+'”':groupView?groups.size+' '+(area?(groups.size===1?'topic':'topics'):(groups.size===1?'research area':'research areas')):'Select a paper to read its abstract'}`;
  $('library-sort-field').hidden=groupView||all.length<2;
  $('library-controls').classList.toggle('group-controls',groupView||all.length<2);
  $('topic-trail').hidden=!area&&!topic&&!query&&!$('library-year').value&&!$('library-venue').value;
  $('topic-trail').innerHTML=`<button id="all-areas">All research</button>${area?`<span class="breadcrumb-divider" aria-hidden="true">/</span><button id="current-area">${esc(groupLabel(area))}</button>`:''}${topic?`<span class="breadcrumb-divider" aria-hidden="true">/</span><span aria-current="page">${esc(groupLabel(topic))}</span>`:''}`;
  $('all-areas').onclick=()=>{area='';topic='';page=0;for(const id of ['library-search','library-year','library-venue'])$(id).value='';clearSearch();render()};
  if(area)$('current-area').onclick=()=>{topic='';page=0;render()};
  if(groupView){
   $('library-content').innerHTML=`<div class="landscape-grid">${[...groups].sort((a,b)=>b[1].length-a[1].length).map(([name,items])=>{
    const topicCount=new Set(items.map(p=>p.topic)).size;
    return `<button class="area-card" data-group="${esc(name)}" style="--area-color:${groupColor(name)}"><span class="area-count">${items.length.toLocaleString()} ${items.length===1?'paper':'papers'}${!area?' · '+topicCount+' '+(topicCount===1?'topic':'topics'):''}</span><h3>${esc(groupLabel(name))}</h3><span class="area-action">${area?'View papers':'View topics'} <span aria-hidden="true">→</span></span></button>`;
   }).join('')}</div>`;
   $('library-content').querySelectorAll('[data-group]').forEach(button=>button.onclick=()=>{if(area)topic=button.dataset.group;else area=button.dataset.group;page=0;render();document.querySelector('main').scrollTop=0});
   $('library-pagination').innerHTML='';$('library-pagination-top').innerHTML='';
  }else{
   const rows=all.slice(page*pageSize,(page+1)*pageSize);
   $('library-content').innerHTML=rows.map((p,i)=>`<article class="library-row ${p.u===selectedURL?'selected':''}" data-row="${i}"><button class="library-paper" data-record="${i}" aria-label="Read ${esc(p.t)}"><div class="library-paper-body"><div class="library-paper-meta">${esc(venueName(p.v))} <span>·</span> ${p.y}</div><h3>${esc(readableText(p.t))}</h3><p class="library-snippet" data-preview="${i}">Loading abstract…</p><div class="library-paper-topic">${esc(groupLabel(p.topic))} <span>Read abstract →</span></div></div></button><button class="paper-evolution-action" data-evolution="${i}" aria-label="Explore evolution of ${esc(p.t)}">Evolution <span aria-hidden="true">→</span></button></article>`).join('');
   function mark(i){selectedURL=rows[i].u;$('library-content').querySelectorAll('[data-row]').forEach(row=>row.classList.toggle('selected',+row.dataset.row===i))}
   $('library-content').querySelectorAll('[data-record]').forEach(button=>button.onclick=()=>{const i=+button.dataset.record;mark(i);selectPaper(rows[i])});
   $('library-content').querySelectorAll('[data-evolution]').forEach(button=>button.onclick=async()=>{
    const i=+button.dataset.evolution;mark(i);button.disabled=true;button.textContent='Opening…';
    try{await openEvolution(rows[i])}finally{if(button.isConnected){button.disabled=false;button.innerHTML='Evolution <span aria-hidden="true">→</span>'}}
   });
   rows.forEach((p,i)=>readPaper(p).then(full=>{
    if(current!==revision)return;const target=$('library-content').querySelector(`[data-preview="${i}"]`);
    if(target){target.textContent=readableText(full.abstract||'Select to view this paper’s details.');renderMath(target)}
   }).catch(()=>{if(current===revision){const target=$('library-content').querySelector(`[data-preview="${i}"]`);if(target)target.textContent='Select to load the abstract.'}}));
   renderMath($('library-content'));
   for(const id of ['library-pagination-top','library-pagination'])pagination($(id),all.length);
  }
  if(!all.length){
   $('library-content').innerHTML='<div class="empty"><h2>No papers found</h2><p>Try a broader title or topic, or clear your filters.</p><button id="clear-library-filters">Clear filters</button></div>';
   $('library-pagination').innerHTML='';$('library-pagination-top').innerHTML='';
   $('clear-library-filters').onclick=()=>{for(const id of ['library-search','library-year','library-venue'])$(id).value='';area='';topic='';page=0;clearSearch();render()};
  }
 }
 for(const id of ['library-search','library-year','library-venue','library-sort'])$(id).addEventListener(id==='library-search'?'input':'change',()=>{page=0;render()});
 return async function open(v,selection=null){
  const opening=++openRevision;view=v;
  if(!records){
   $('library-content').innerHTML='<div class="empty" role="status">Loading the research collection…</div>';
   try{const loaded=await loadCorpus();if(!records){records=loaded;for(const y of [...new Set(records.map(p=>p.y))].sort((a,b)=>b-a))$('library-year').add(new Option(y,y));for(const venue of [...new Set(records.map(p=>p.v))].sort())$('library-venue').add(new Option(venueName(venue),venue))}}
   catch{if(opening===openRevision){$('library-count').textContent='Collection unavailable';$('library-content').innerHTML='<div class="empty"><h2>Collection unavailable</h2><p>The local collection could not be loaded.</p><button id="retry-library">Retry collection</button></div>';$('retry-library').onclick=()=>open(v,selection)}return}
  }
  if(opening!==openRevision)return;
  if(selection){area='';topic=selection.topic||'';page=0;if(!selection.preserveFilters)for(const id of ['library-year','library-venue'])$(id).value='';$('library-search').value=selection.query||''}
  render();
 };
}
