function sourceIdentity(value) {
  let source = String(value || '')
    .trim()
    .replace(/#.*$/, '')
    .replace(/^http:\/\//, 'https://');
  const arxiv = source.match(
    /^https:\/\/(?:www\.)?arxiv\.org\/(?:abs|pdf)\/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?(?:[?].*)?$/i,
  );
  if (arxiv) return 'arxiv:' + arxiv[1];
  return source.replace(/\/$/, '');
}
const titleIdentity = value =>
  String(value || '')
    .normalize('NFKC')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
export function samePaper(record, paper) {
  const a = sourceIdentity(record.u || record.source_url),
    b = sourceIdentity(paper.u || paper.source_url);
  if (a && b) return a === b;
  const title = titleIdentity(record.t || record.title);
  return Boolean(title) && title === titleIdentity(paper.t || paper.title);
}
