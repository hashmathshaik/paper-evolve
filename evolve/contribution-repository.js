// Use an explicit build identity; ordinary github.io URLs are a fallback.
// Never trust arbitrary URLs from metadata or the inherited Git remote.
export function repositoryInfo(config={},pageURL=''){
 let identity=config&&typeof config.repository==='string'?config.repository:'';
 if(!identity){
  const match=String(pageURL).match(/^https?:\/\/([a-z0-9][a-z0-9-]*)\.github\.io(?:\/([^?#]*))?(?:[?#].*)?$/i);if(!match)return null;
  let segment;try{segment=decodeURIComponent((match[2]||'').split('/').filter(Boolean)[0]||'')}catch{return null}
  identity=match[1]+'/'+(!segment||segment.endsWith('.html')?match[1]+'.github.io':segment);
 }
 if(!/^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(identity))return null;
 const url='https://github.com/'+identity;
 return {repository:identity,url,forkURL:url+'/fork',pullsURL:url+'/pulls'};
}
