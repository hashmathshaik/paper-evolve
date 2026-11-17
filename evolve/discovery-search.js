import {readableText} from './text-format.js?v=3b080bf0551b';
import {renderMath} from './math.js?v=3b080bf0551b';
import {loadCorpus,venueName} from './paper-data.js?v=3b080bf0551b';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Collection search and the explicit topic picker share one bounded, in-panel list.
export function createDiscoverySearch({input,results,selectTopic,selectPaper,searchAll,clearCollectionSearch}){
 let records=null,topics=[],generation=0,timer=null;
 const clearButton=document.getElementById('clear-search');
 const syncClear=()=>{clearButton.hidden=!input.value};
 function close(){clearTimeout(timer);generation++;results.hidden=true;input.setAttribute('aria-expanded','false');results.parentElement.scrollTop=0;syncClear()}
 async function search(browse=false){
  clearTimeout(timer);syncClear();
  const query=input.value.trim().toLowerCase();
  if(!query&&!browse){close();return}
  const current=++generation;
  results.parentElement.scrollTop=0;
  results.hidden=false;input.setAttribute('aria-expanded','true');
  results.innerHTML='<p class="search-status" role="status">Searching the collection…</p>';
  try{
   if(!records){
    records=await loadCorpus();const counts=new Map();
    for(const p of records)if(p.topic)counts.set(p.topic,(counts.get(p.topic)||0)+1);
    topics=[...counts].sort((a,b)=>b[1]-a[1]);
   }
   if(current!==generation)return;
   const words=query.split(/\s+/).filter(Boolean),matches=text=>words.every(word=>text.toLowerCase().includes(word));
   const topicMatches=topics.filter(([name])=>matches(name)),paperMatches=query?records.filter(p=>matches(p.t)).sort((a,b)=>b.y-a.y):[];
   const foundTopics=topicMatches.slice(0,6),foundPapers=paperMatches.slice(0,6);
   results.innerHTML=`<div class="discovery-results-heading"><strong>${query?'Search results':'Choose a topic'}</strong><button type="button" aria-label="Close search results" title="Back to exploration">×</button></div>`+
    (foundTopics.length?`<p class="eyebrow">Topics <span>${topicMatches.length.toLocaleString()}</span></p>`+foundTopics.map(([name,count],i)=>`<button class="discovery-result" data-topic-result="${i}"><span>${esc(name)}</span><small>${count.toLocaleString()} papers · Browse topic →</small></button>`).join(''):'')+
    (foundPapers.length?`<p class="eyebrow">Papers <span>${paperMatches.length.toLocaleString()}</span></p>`+foundPapers.map((p,i)=>`<button class="discovery-result" data-paper-result="${i}"><span>${esc(readableText(p.t))}</span><small>${p.y} · ${esc(venueName(p.v))} · Read abstract →</small></button>`).join(''):'')+
    (query?'<button class="search-all">Search the collection →</button>':'')+
    (!foundTopics.length&&!foundPapers.length?'<div class="search-empty"><strong>No suggestions found</strong><p>Press Enter to search the collection.</p></div>':'');
   renderMath(results);
   results.querySelector('.search-all')?.addEventListener('click',async()=>{await searchAll(input.value.trim());close()});
   results.querySelector('[aria-label="Close search results"]').onclick=()=>{close();input.focus()};
   results.querySelectorAll('[data-topic-result]').forEach(button=>button.onclick=async()=>{
    button.disabled=true;
    try{const name=foundTopics[+button.dataset.topicResult][0];input.value=name;await selectTopic(name);close()}
    catch{button.disabled=false;button.querySelector('small').textContent='Could not open topic. Try again.'}
   });
   results.querySelectorAll('[data-paper-result]').forEach(button=>button.onclick=async()=>{
    button.disabled=true;button.querySelector('small').textContent='Opening paper…';
    try{await selectPaper(foundPapers[+button.dataset.paperResult]);close()}
    catch{button.disabled=false;button.querySelector('small').textContent='Could not open paper. Try again.'}
   });
  }catch{
   if(current!==generation)return;
   records=null;results.innerHTML='<div class="search-empty"><strong>Collection could not be loaded</strong><p>Check the local server and try again.</p><button class="search-retry">Retry search</button></div>';
   results.querySelector('button').onclick=()=>search(browse);
  }
 }
 input.addEventListener('input',()=>{
  syncClear();clearTimeout(timer);generation++;
  if(!input.value.trim()){close();return}
  results.hidden=false;input.setAttribute('aria-expanded','true');
  results.innerHTML='<p class="search-status" role="status">Searching the collection…</p>';
  timer=setTimeout(()=>search(),100);
 });
 input.addEventListener('keydown',async event=>{
  if(event.key==='Escape'&&!results.hidden){event.preventDefault();event.stopPropagation();close();return}
  if(event.key==='ArrowDown'){
   event.preventDefault();if(results.hidden||!results.querySelector('.discovery-result'))await search(!input.value.trim());
   results.querySelector('.discovery-result')?.focus();
  }
  if(event.key==='Enter'){
   event.preventDefault();const query=input.value.trim();
   close();await searchAll(query);
  }
 });
 results.addEventListener('keydown',event=>{
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();input.focus();return}
  const buttons=[...results.querySelectorAll('.discovery-result:not(:disabled)')],index=buttons.indexOf(document.activeElement);
  if(index<0)return;
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
   event.preventDefault();
   if(event.key==='ArrowUp'&&index===0){input.focus();return}
   const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,index+(event.key==='ArrowDown'?1:-1)));
   buttons[next]?.focus();
  }
 });
 clearButton.onclick=()=>{input.value='';close();clearCollectionSearch();input.focus()};
 document.addEventListener('explorer-closed',close);
 document.addEventListener('pointerdown',event=>{
  if(!results.contains(event.target)&&!event.target.closest('.search'))close();
 });
 syncClear();
}
