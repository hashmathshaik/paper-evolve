/** Landscape timeline: one stacked band per research area (or topic) across publication years. */
export const HUES=['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#6250d6','#e34948'],NEUTRAL='#b4b2a9';
// Bands stack in hue order: that order was checked so touching bands stay distinguishable for colour-blind readers.
export const AREA_ORDER=['Natural Language Processing & LLMs','Multimodal Understanding & Reasoning','3D Generation & Reconstruction','Generative Modeling and Inference','Graph Neural Networks & Molecular AI','Optimization & Federated Learning','Online Learning and Bandits','Reinforcement Learning','Cross-Cutting & Specialized Research','Unclustered'];
export const areaColor=name=>{const i=AREA_ORDER.indexOf(name);return i>=0&&i<HUES.length?HUES[i]:name==='Cross-Cutting & Specialized Research'?'#888780':NEUTRAL};
const node=(tag,props,...children)=>{const n=Object.assign(document.createElement(tag),props);n.append(...children);return n};
const percent=v=>`${+(v*100).toFixed(v<.1?1:0)}%`;
function niceStep(peak){const raw=peak/4,pow=10**Math.floor(Math.log10(raw)),m=raw/pow-1e-9;return (m<=1?1:m<=2?2:m<=2.5?2.5:m<=5?5:10)*pow}
export function createLandscapeTimeline({onGroup}){
 const host=node('div',{className:'landscape-timeline'});
 host.innerHTML='<div class="timeline-head"><p></p><div class="timeline-mode" role="group" aria-label="Measure"><button data-mode="share" aria-pressed="true">Share</button><button data-mode="count" aria-pressed="false">Papers</button></div></div><div class="timeline-plot"><svg role="img" aria-label="Stacked chart of paper groups by year. The same groups are listed as buttons below the chart."></svg><div class="timeline-labels" aria-hidden="true"></div><div class="timeline-tip" hidden></div></div><p class="timeline-note" hidden></p>';
 const plot=host.querySelector('.timeline-plot'),svg=plot.querySelector('svg'),labelLayer=plot.querySelector('.timeline-labels'),tip=plot.querySelector('.timeline-tip'),heading=host.querySelector('.timeline-head p'),note=host.querySelector('.timeline-note');
 let state=null,mode='share',frame=null,active='',firstTouch=false;
 const value=(s,i)=>mode==='share'?s.counts[i]/state.totals[i]:s.counts[i];
 function highlight(name){
  active=name;
  svg.querySelectorAll('[data-series]').forEach(path=>path.classList.toggle('dim',!!name&&state.series[path.dataset.series].name!==name));
  labelLayer.querySelectorAll('button').forEach(button=>button.classList.toggle('muted',!!name&&button.dataset.group!==name));
 }
 function render(){
  if(!state||!plot.clientWidth)return;
  const {years,series,partial,selectedYear}=state,W=plot.clientWidth,H=plot.clientHeight,gutter=W>=900?276:16,left=46,top=10,bottom=28,right=W-gutter,n=years.length;
  heading.textContent=mode==='share'?'Share of each year’s papers':'Papers published each year';
  note.hidden=!partial;if(partial)note.textContent=`* ${partial.year} so far covers ${partial.venues.join(' and ')} only.`;
  // stack[k][i] = [lower, upper] edge of band k in year i
  const sums=years.map(()=>0),stack=series.map(s=>years.map((_,i)=>{const from=sums[i];sums[i]+=value(s,i);return [from,sums[i]]}));
  const peak=Math.max(...sums),step=niceStep(peak),max=mode==='share'&&peak>.999?1:Math.ceil(peak/step-1e-9)*step;
  const x=i=>left+(right-left)*i/(n-1),y=v=>H-bottom-(H-top-bottom)*v/max,f=v=>v.toFixed(1);
  let out='';
  for(let v=0;v<=max+step/2;v+=step)out+=`<line class="grid${v?'':' axis'}" x1="${left}" x2="${right}" y1="${f(y(v))}" y2="${f(y(v))}"/><text x="${left-8}" y="${f(y(v)+4)}" text-anchor="end">${mode==='share'?percent(v):Math.round(v).toLocaleString()}</text>`;
  const tight=(right-left)/(n-1)<44; // phone width: four-digit years would run into each other
  years.forEach((year,i)=>{out+=`<text class="${year===selectedYear?'on':''}" x="${f(x(i))}" y="${H-8}" text-anchor="${i===n-1&&gutter<100&&!tight?'end':'middle'}">${tight?'’'+String(year).slice(2):year}${partial&&i===n-1?'*':''}</text>`});
  const band=(k,from,to)=>{let d='';for(let i=from;i<=to;i++)d+=`${i===from?'M':'L'}${f(x(i))} ${f(y(stack[k][i][1]))}`;for(let i=to;i>=from;i--)d+=`L${f(x(i))} ${f(y(stack[k][i][0]))}`;return d+'Z'};
  if(partial)out+=`<rect class="blank" x="${f(x(n-2))}" y="${top}" width="${f(x(n-1)-x(n-2))}" height="${H-top-bottom}"/>`; // keeps gridlines from showing through the lighter last year
  series.forEach((s,k)=>{
   const solid=partial?n-2:n-1,shape=`data-series="${k}" fill="${s.color}"`;
   if(solid>0)out+=`<path class="${s.folded?'folded':''}" ${shape} d="${band(k,0,solid)}"/>`;
   if(partial)out+=`<path class="partial${s.folded?' folded':''}" ${shape} d="${band(k,n-2,n-1)}"/>`; // lighter: the last year is still filling in
  });
  const marked=years.indexOf(selectedYear);if(marked>=0)out+=`<line class="year" x1="${f(x(marked))}" x2="${f(x(marked))}" y1="${top}" y2="${H-bottom}"/>`;
  out+=`<line class="cross" y1="${top}" y2="${H-bottom}" visibility="hidden"/>`;
  // Name each band beside its right-hand end; names that would collide are spread apart and joined by a leader.
  labelLayer.replaceChildren();
  if(gutter>100){
   const ends=series.map((s,k)=>({s,at:y((stack[k][n-1][0]+stack[k][n-1][1])/2)})).filter(e=>e.s.counts[n-1]).sort((a,b)=>a.at-b.at);
   ends.forEach((e,i)=>{e.top=Math.max(e.at,i?ends[i-1].top+20:top+8)});
   for(let i=ends.length-1;i>=0;i--)ends[i].top=Math.min(ends[i].top,(i<ends.length-1?ends[i+1].top:H-bottom+12)-20);
   for(const e of ends){
    out+=`<path class="leader" d="M${right+3} ${f(e.at)}h6L${right+18} ${f(e.top)}h6"/>`;
    const button=node('button',{tabIndex:-1},node('span',{textContent:e.s.label}));button.dataset.group=e.s.name;
    button.style.cssText=`left:${right+28}px;top:${Math.round(e.top-10)}px;max-width:${gutter-32}px;--area-color:${e.s.color}`;
    if(e.s.folded)button.disabled=true;else button.onclick=()=>onGroup(e.s.name);
    button.onpointerenter=()=>highlight(e.s.name);button.onpointerleave=()=>highlight('');labelLayer.append(button);
   }
  }
  svg.innerHTML=out;frame={left,right,n,x};highlight(active);tip.hidden=true;
 }
 function point(event){
  const r=svg.getBoundingClientRect(),px=event.clientX-r.left,py=event.clientY-r.top,cross=svg.querySelector('.cross');
  if(!frame||px<frame.left-12||px>frame.right+12){leave();return}
  const i=Math.max(0,Math.min(frame.n-1,Math.round((px-frame.left)/(frame.right-frame.left)*(frame.n-1)))),k=event.target.dataset?.series,name=k===undefined?'':state.series[k].name;
  firstTouch=event.pointerType==='touch'&&name!==active;
  cross.setAttribute('x1',frame.x(i));cross.setAttribute('x2',frame.x(i));cross.setAttribute('visibility','visible');highlight(name);
  // One readout for the year: every group, largest first, with the hovered band marked.
  const rows=state.series.map(s=>({s,v:value(s,i)})).filter(row=>row.s.counts[i]).sort((a,b)=>b.v-a.v);
  tip.replaceChildren(node('strong',{textContent:`${state.years[i]}${state.partial&&i===frame.n-1?' so far':''}`}),...rows.map(({s})=>{
   const share=percent(s.counts[i]/state.totals[i]),count=s.counts[i].toLocaleString(),key=node('i');key.style.background=s.color;
   return node('div',{className:s.name===name?'on':''},key,node('b',{textContent:mode==='share'?share:count}),node('span',{textContent:s.label}),node('em',{textContent:mode==='share'?count:share}));
  }));
  tip.hidden=false;
  const tw=tip.offsetWidth,th=tip.offsetHeight,tx=frame.x(i)+16+tw>plot.clientWidth?frame.x(i)-16-tw:frame.x(i)+16;
  tip.style.transform=`translate(${Math.round(Math.max(4,tx))}px,${Math.round(Math.max(0,Math.min(plot.clientHeight-th,py-th/2)))}px)`;
 }
 function leave(){tip.hidden=true;svg.querySelector('.cross')?.setAttribute('visibility','hidden');highlight('')}
 svg.addEventListener('pointermove',point);svg.addEventListener('pointerdown',point);
 svg.addEventListener('pointerleave',event=>{if(event.pointerType!=='touch')leave()});
 svg.addEventListener('click',event=>{
  const k=event.target.dataset?.series;if(k===undefined)return;
  if(firstTouch){firstTouch=false;return} // on touch the first tap reads the band, the second opens it
  if(!state.series[k].folded)onGroup(state.series[k].name);
 });
 host.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{
  mode=button.dataset.mode;host.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();
 });
 new ResizeObserver(render).observe(plot);
 return {element:host,highlight,update(next){state=next;active='';render()}};
}
