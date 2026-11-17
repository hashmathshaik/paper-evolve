// Display helpers only: original titles, abstracts and evidence stay unchanged.
export const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const mathParts=/(\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\\\n])+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\])/g;
function prose(text){
 let value=text.replace(/\\href\{([^{}]+)\}\{([^{}]+)\}/g,(_,url,label)=>label===url?url:`${label} (${url})`).replace(/\\url\{([^{}]+)\}/g,'$1');
 for(let i=0;i<6;i++)value=value.replace(/\\(?:textit|textbf|texttt|textrm|emph)\{([^{}]*)\}/g,'$1');
 return value.replace(/\\([%&_#])/g,'$1').replace(/\\times\b/g,'×').replace(/\\sim\b/g,'∼');
}
export function readableText(text){return String(text??'').split(mathParts).map((part,i)=>i%2?part:prose(part)).join('')}
function links(text){
 const pattern=/https?:\/\/[^\s<>"{}]+/g;let html='',start=0;
 for(const match of text.matchAll(pattern)){
  let url=match[0],tail='';
  while(/[.,;:!?]$/.test(url)||(url.endsWith(')')&&(url.match(/\)/g)||[]).length>(url.match(/\(/g)||[]).length)){tail=url.slice(-1)+tail;url=url.slice(0,-1)}
  html+=escapeHTML(text.slice(start,match.index))+`<a href="${escapeHTML(url)}" target="_blank" rel="noopener">${escapeHTML(url)}</a>`+escapeHTML(tail);start=match.index+match[0].length;
 }
 return html+escapeHTML(text.slice(start));
}
export function textHTML(text){return String(text??'').split(mathParts).map((part,i)=>i%2?escapeHTML(part):links(prose(part))).join('')}
export const paragraphsHTML=text=>String(text??'').split(/\n\s*\n/).filter(Boolean).map(part=>`<p>${textHTML(part.trim())}</p>`).join('');
