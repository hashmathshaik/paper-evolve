/** Browser-local navigation. Resize keeps a fitted timeline visible, manual zoom stays put. */
export function createViewport({viewport,surface,graph,width=1320,height=944}){
 let scale=1,pan=null,layoutMode='readable';
 const $=id=>document.getElementById(id),label=$('zoom-level');
 function zoom(next,anchor){
  const old=scale;scale=Math.max(.05,Math.min(2,next));
  const bounds=viewport.getBoundingClientRect(),x=anchor?anchor.x-bounds.left:viewport.clientWidth/2,y=anchor?anchor.y-bounds.top:viewport.clientHeight/2;
  const oldOffset=Math.max(0,(viewport.clientWidth-width*old)/2);
  const worldX=(viewport.scrollLeft+x-oldOffset)/old,worldY=(viewport.scrollTop+y)/old;
  graph.style.transform=`scale(${scale})`;surface.style.width=`${width*scale}px`;surface.style.height=`${height*scale}px`;
  const offset=Math.max(0,(viewport.clientWidth-width*scale)/2);surface.style.marginLeft=offset+'px';
  label.textContent=`${Math.round(scale*100)}%`;viewport.scrollLeft=worldX*scale+offset-x;viewport.scrollTop=worldY*scale-y;
  $('zoom-out').disabled=scale<=.05;$('zoom-in').disabled=scale>=2;
 }
 function arrange(reset=true){
  if(!viewport.clientWidth||!viewport.clientHeight)return;
  const next=layoutMode==='overview'?Math.min((viewport.clientWidth-30)/width,(viewport.clientHeight-55)/height,1):Math.max(.85,Math.min((viewport.clientWidth-30)/width,1));
  zoom(next);if(reset)viewport.scrollTo({left:0,top:0});
 }
 function fit(){layoutMode='overview';arrange()}
 function frame(){layoutMode='readable';arrange()}
 function manual(next,anchor){layoutMode=null;zoom(next,anchor)}
 $('zoom-in').onclick=()=>manual(scale+.15);$('zoom-out').onclick=()=>manual(scale-.15);
 label.onclick=()=>manual(1);$('fit').onclick=fit;
 viewport.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();manual(scale*Math.exp(-e.deltaY*.008),{x:e.clientX,y:e.clientY})}},{passive:false});
 viewport.addEventListener('pointerdown',e=>{if(e.target.closest('button,a,input,select,.edge-hit')||e.button!==0)return;pan={x:e.clientX,y:e.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};viewport.classList.add('panning');viewport.setPointerCapture(e.pointerId);e.preventDefault()});
 viewport.addEventListener('pointermove',e=>{if(!pan)return;viewport.scrollLeft=pan.left-(e.clientX-pan.x);viewport.scrollTop=pan.top-(e.clientY-pan.y)});
 const finish=()=>{pan=null;viewport.classList.remove('panning')};viewport.addEventListener('pointerup',finish);viewport.addEventListener('pointercancel',finish);
 viewport.addEventListener('keydown',e=>{if(e.target!==viewport)return;const delta={ArrowDown:[0,90],ArrowUp:[0,-90],ArrowLeft:[-90,0],ArrowRight:[90,0]}[e.key];if(delta){e.preventDefault();viewport.scrollBy({left:delta[0],top:delta[1],behavior:'smooth'})}});
 new ResizeObserver(()=>{if(layoutMode)arrange(false)}).observe(viewport);
 frame();return {fit,frame,setSize(w,h){if(w===width&&h===height)return;width=w;height=h;if(layoutMode)arrange();else zoom(scale)},reset(){layoutMode=null;zoom(1);viewport.scrollTo({left:0,top:0})}};
}
