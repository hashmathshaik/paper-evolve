// Presentation-only layout. Moving cards never changes chronology or research records.
export const CARD={width:244,height:228};
export const STAGE={width:1320,height:944};
const step=10,BEND=5,SHARED=6,BESIDE=1,CROSS=.5,FAN=7,DIRS=[[1,0],[0,1],[-1,0],[0,-1]];
/** Orthogonal A* (state = cell + heading) on a 10px grid, routed shortest connection first.
 A cell that already carries a line in the same direction costs SHARED extra and a cell next to
 one costs BESIDE, so connections spread into parallel tracks instead of stacking on one corridor.
 Labels go on the longest segment that is clear of cards and of labels placed earlier. */
export function routeConnections(links,obstacles,bounds=STAGE){
 const W=Math.floor((bounds.width-10)/step)+1,H=Math.floor((bounds.height-20)/step)+1,MINX=1,MINY=5;
 const blocked=new Uint8Array(W*H),used=new Uint8Array(W*H); // used bit 1: horizontal line, bit 2: vertical line
 for(const p of obstacles)for(let y=Math.max(0,Math.floor((p.y-10)/step)+1);y<H&&y*step<p.y+CARD.height+10;y++)for(let x=Math.max(0,Math.floor((p.x-10)/step)+1);x<W&&x*step<p.x+CARD.width+10;x++)blocked[y*W+x]=1;
 // Leave from the side that faces the other card: right→left by default, left→right when the target
 // sits in an earlier column, bottom→top (or top→bottom) when both share a column.
 const ends=links.map(({a,b})=>{
  const dx=b.x-a.x,dy=b.y-a.y;
  if(Math.abs(dx)<CARD.width&&Math.abs(dy)>=CARD.height){const v=dy>0?1:-1;return {start:{x:a.x+CARD.width/2,y:v>0?a.y+CARD.height:a.y},end:{x:b.x+CARD.width/2,y:v>0?b.y:b.y+CARD.height},ux:0,uy:v}}
  const h=dx+CARD.width<=0?-1:1;return {start:{x:h>0?a.x+CARD.width:a.x,y:a.y+CARD.height/2},end:{x:h>0?b.x:b.x+CARD.width,y:b.y+CARD.height/2},ux:h,uy:0};
 });
 const reach=({start,end})=>Math.abs(end.x-start.x)+Math.abs(end.y-start.y);
 const order=links.map((_,i)=>i).sort((i,j)=>reach(ends[i])-reach(ends[j])),out=new Array(links.length),placed=[];
 const g=new Float32Array(W*H*4),previous=new Int32Array(W*H*4);
 for(const index of order){
  const {start,end,ux,uy}=ends[index],sx=Math.round((start.x+22*ux)/step),sy=Math.round((start.y+22*uy)/step),tx=Math.round((end.x-22*ux)/step),ty=Math.round((end.y-22*uy)/step);
  const inside=(x,y)=>x>=MINX&&x<W&&y>=MINY&&y<H&&!blocked[y*W+x];
  let goal=-1;
  if(inside(sx,sy)&&inside(tx,ty)){
   g.fill(Infinity);previous.fill(-1);
   const heap=[],push=(f,state)=>{let i=heap.length;heap.push([f,state]);while(i){const up=(i-1)>>1;if(heap[up][0]<=heap[i][0])break;[heap[up],heap[i]]=[heap[i],heap[up]];i=up}};
   const pop=()=>{const top=heap[0],last=heap.pop();if(heap.length){heap[0]=last;let i=0;for(;;){let m=i;const l=2*i+1,r=l+1;if(l<heap.length&&heap[l][0]<heap[m][0])m=l;if(r<heap.length&&heap[r][0]<heap[m][0])m=r;if(m===i)break;[heap[m],heap[i]]=[heap[i],heap[m]];i=m}}return top};
   const first=(sy*W+sx)*4+DIRS.findIndex(([x,y])=>x===ux&&y===uy);g[first]=0;push(0,first);let visits=0;
   while(heap.length&&visits++<60000){
    const [f,state]=pop(),dir=state&3,cell=state>>2,x=cell%W,y=(cell-x)/W;
    if(f-Math.abs(x-tx)-Math.abs(y-ty)>g[state]+1e-6)continue;
    if(x===tx&&y===ty){goal=state;break}
    for(let d=0;d<4;d++){
     if(d===(dir+2)%4)continue;const nx=x+DIRS[d][0],ny=y+DIRS[d][1];if(!inside(nx,ny))continue;
     const n=ny*W+nx,along=d%2?2:1,u=used[n];let cost=1+(d===dir?0:BEND);
     // Fanning out of one card (or into one) within the first gutter is free; long shared runs are not.
     const fan=Math.abs(nx-sx)+Math.abs(ny-sy)<=FAN||Math.abs(nx-tx)+Math.abs(ny-ty)<=FAN;
     if(u&along){if(!fan)cost+=SHARED}else{if(u)cost+=CROSS;const side=d%2?1:W;if(!fan&&(used[n-side]|used[n+side])&along)cost+=BESIDE}
     const next=n*4+d,total=g[state]+cost;if(total>=g[next])continue;
     g[next]=total;previous[next]=state;push(total+Math.abs(nx-tx)+Math.abs(ny-ty),next);
    }
   }
  }
  let points;
  if(goal>=0){
   const cells=[];for(let state=goal;state>=0;state=previous[state])cells.push(state>>2);cells.reverse();
   for(let i=1;i<cells.length;i++){const bit=cells[i]-cells[i-1]===1||cells[i-1]-cells[i]===1?1:2;used[cells[i]]|=bit;used[cells[i-1]]|=bit}
   const grid=cells.map(c=>({x:(c%W)*step,y:Math.floor(c/W)*step})),axis=uy?'x':'y',from=grid[0][axis],to=grid.at(-1)[axis];
   if(grid.every(p=>p[axis]===from))points=[start,end];
   else{
    // Cards sit off-grid after dragging: keep the first and last runs in line with their card.
    let i=0,j=grid.length-1;while(i<grid.length&&grid[i][axis]===from)i++;while(j>=i&&grid[j][axis]===to)j--;
    grid.forEach((p,k)=>{if(k<i)p[axis]=start[axis];else if(k>j)p[axis]=end[axis]});
    points=[start,...grid,end];
   }
  }else points=[start,{x:start.x+20,y:start.y},{x:start.x+20,y:bounds.height-25},{x:end.x-20,y:bounds.height-25},{x:end.x-20,y:end.y},end];
  // Retain bends only.
  points=points.filter((p,i,all)=>i===0||i===all.length-1||!((all[i-1].x===p.x&&p.x===all[i+1].x)||(all[i-1].y===p.y&&p.y===all[i+1].y)));
  const segments=points.slice(1).map((q,i)=>({p:points[i],q,length:Math.hypot(q.x-points[i].x,q.y-points[i].y)})).sort((m,n)=>n.length-m.length);
  const w=(links[index].text||'').length*5.8+20,h=22,box=c=>({l:c.x-w/2,r:c.x+w/2,t:c.y-h/2,b:c.y+h/2});
  const clear=c=>{const k=box(c);return !placed.some(o=>k.l<o.r+4&&k.r>o.l-4&&k.t<o.b+4&&k.b>o.t-4)&&!obstacles.some(o=>k.l<o.x+CARD.width&&k.r>o.x&&k.t<o.y+CARD.height&&k.b>o.y)};
  const options=segments.flatMap(({p,q})=>[.5,.32,.68,.18,.82].map(t=>({x:p.x+(q.x-p.x)*t,y:p.y+(q.y-p.y)*t})));
  const label=options.find(clear)||options[0];placed.push(box(label));
  out[index]={d:roundedPath(points),label};
 }
 return out;
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
