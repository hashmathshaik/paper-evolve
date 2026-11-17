// Presentation-only layout. Moving cards never changes chronology or research records.
export const CARD={width:244,height:228};
export const STAGE={width:1320,height:944};
const step=10;
export function routeConnection(a,b,obstacles,bounds=STAGE){
 const start={x:a.x+CARD.width,y:a.y+CARD.height/2},end={x:b.x,y:b.y+CARD.height/2};
 const snap=p=>({x:Math.round(p.x/step),y:Math.round(p.y/step)});
 const s=snap({x:start.x+22,y:start.y}),t=snap({x:end.x-22,y:end.y});
 const key=p=>p.x+','+p.y;
 const blocked=(x,y)=>obstacles.some(p=>x*step>p.x-10&&x*step<p.x+CARD.width+10&&y*step>p.y-10&&y*step<p.y+CARD.height+10);
 const open=[{...s,g:0,f:0}],cost=new Map([[key(s),0]]),previous=new Map();let found=false,visits=0;
 while(open.length&&visits++<12000){let best=0;for(let i=1;i<open.length;i++)if(open[i].f<open[best].f)best=i;const cur=open.splice(best,1)[0];if(cur.g!==cost.get(key(cur)))continue;if(key(cur)===key(t)){found=true;break}
  for(const [dx,dy] of [[1,0],[0,1],[-1,0],[0,-1]]){const n={x:cur.x+dx,y:cur.y+dy};if(n.x<1||n.x>(bounds.width-10)/step||n.y<5||n.y>(bounds.height-20)/step||blocked(n.x,n.y))continue;const g=cur.g+1;if(g>=(cost.get(key(n))??Infinity))continue;cost.set(key(n),g);previous.set(key(n),cur);open.push({...n,g,f:g+Math.abs(n.x-t.x)+Math.abs(n.y-t.y)})}
 }
 let points;
 if(found){let p=t;points=[end,{x:t.x*step,y:t.y*step}];while(key(p)!==key(s)){p=previous.get(key(p));points.push({x:p.x*step,y:p.y*step})}points.push(start);points.reverse()}
 else points=[start,{x:start.x+20,y:start.y},{x:start.x+20,y:bounds.height-25},{x:end.x-20,y:bounds.height-25},{x:end.x-20,y:end.y},end];
 // Retain bends only, then place the label on the longest visible segment.
 points=points.filter((p,i,all)=>i===0||i===all.length-1||!((all[i-1].x===p.x&&p.x===all[i+1].x)||(all[i-1].y===p.y&&p.y===all[i+1].y)));
 let segment=0,length=0;for(let i=0;i<points.length-1;i++){const n=Math.hypot(points[i+1].x-points[i].x,points[i+1].y-points[i].y);if(n>length){length=n;segment=i}}
 const p=points[segment],q=points[segment+1];
 return {d:roundedPath(points),label:{x:(p.x+q.x)/2,y:(p.y+q.y)/2}};
}
export function wireMovableCards({graph,positions,position,render,onSave}){
 let drag=null,frame=0,suppressUntil=0;
 graph.addEventListener('pointerdown',e=>{const card=e.target.closest('[data-paper]');if(!card||e.button!==0)return;const p=position(card.dataset.paper);const rect=graph.getBoundingClientRect();drag={id:card.dataset.paper,startX:e.clientX,startY:e.clientY,x:p.x,y:p.y,scale:rect.width/graph.offsetWidth,moved:false};});
 document.addEventListener('pointermove',e=>{if(!drag)return;const dx=(e.clientX-drag.startX)/drag.scale,dy=(e.clientY-drag.startY)/drag.scale;if(!drag.moved&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<5)return;drag.moved=true;e.preventDefault();positions.set(drag.id,{x:Math.max(16,Math.min(graph.offsetWidth-CARD.width-20,drag.x+dx)),y:Math.max(64,Math.min(graph.offsetHeight-CARD.height-24,drag.y+dy))});if(!frame)frame=requestAnimationFrame(()=>{frame=0;render();graph.querySelector(`[data-paper="${drag?.id}"]`)?.classList.add('dragging')})},{passive:false});
 const finish=()=>{if(!drag)return;if(drag.moved){suppressUntil=Date.now()+300;onSave();render()}drag=null;};
 document.addEventListener('pointerup',finish);document.addEventListener('pointercancel',finish);
 graph.addEventListener('click',e=>{if(Date.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation()}},true);
 graph.addEventListener('keydown',e=>{const card=e.target.closest('[data-paper]');if(!card||!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const p=position(card.dataset.paper),n=e.shiftKey?5:20;positions.set(card.dataset.paper,{x:Math.max(16,Math.min(graph.offsetWidth-CARD.width-20,p.x+({'ArrowRight':n,'ArrowLeft':-n}[e.key]||0))),y:Math.max(64,Math.min(graph.offsetHeight-CARD.height-24,p.y+({'ArrowDown':n,'ArrowUp':-n}[e.key]||0)))});render();graph.querySelector(`[data-paper="${card.dataset.paper}"]`)?.focus();onSave()});
}

function roundedPath(points){
 let d=`M${points[0].x},${points[0].y}`;
 for(let i=1;i<points.length-1;i++){
  const before=points[i-1],p=points[i],after=points[i+1];const incoming=Math.hypot(p.x-before.x,p.y-before.y),outgoing=Math.hypot(after.x-p.x,after.y-p.y);
  if(!incoming||!outgoing)continue;const r=Math.min(12,incoming/2,outgoing/2);
  const a={x:p.x-(p.x-before.x)/incoming*r,y:p.y-(p.y-before.y)/incoming*r},b={x:p.x+(after.x-p.x)/outgoing*r,y:p.y+(after.y-p.y)/outgoing*r};
  d+=` L${a.x},${a.y} Q${p.x},${p.y} ${b.x},${b.y}`;
 }
 const last=points.at(-1);return d+` L${last.x},${last.y}`;
}
