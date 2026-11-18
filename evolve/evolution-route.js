/** A selected paper belongs in the URL so reload and history preserve its timeline. */
export function paperURL(record) {
  return record?.u || record?.source_url || '';
}
export function evolutionHash(record) {
  const url = paperURL(record);
  return '#evolution' + (url ? '?paper=' + encodeURIComponent(url) : '');
}
export function parseRoute(hash) {
  const [path, query = ''] = String(hash || '')
    .replace(/^#/, '')
    .split('?');
  const view = path === 'landscape' || path === 'map' ? 'map' : path === 'browse' ? 'browse' : 'evolution';
  let paper = null;
  if (view === 'evolution') {
    const value = query.split('&').find(part => part.startsWith('paper='));
    if (value) {
      try {
        const url = decodeURIComponent(value.slice(6));
        if (/^https?:\/\/[^\s]+$/i.test(url)) paper = url;
      } catch {}
    }
  }
  return { view, paper };
}
