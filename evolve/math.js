// KaTeX and fonts are bundled locally. Source text is never trusted as executable HTML.
let loading=null;
function script(file){return new Promise((resolve,reject)=>{const tag=document.createElement('script');tag.src=new URL('../assets/vendor/katex/'+file,import.meta.url).href;tag.onload=resolve;tag.onerror=reject;document.head.append(tag)})}
export async function renderMath(element){
 if(!element||!/[\$]|\\[\(\[]/.test(element.textContent))return;
 try{
  if(!loading){
   const style=document.createElement('link');style.rel='stylesheet';style.href=new URL('../assets/vendor/katex/katex.min.css',import.meta.url).href;document.head.append(style);
   loading=script('katex.min.js').then(()=>script('auto-render.min.js')).catch(error=>{loading=null;throw error});
  }
  await loading;if(!element.isConnected)return;
  window.renderMathInElement(element,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}],throwOnError:false,strict:'ignore',trust:false,maxExpand:1000,maxSize:10,errorColor:'#63775b',ignoredClasses:['katex','ignore-math']});
 }catch{/* Keep the readable original text if an optional formatter is unavailable. */}
}
