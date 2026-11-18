"""Contributor-added papers and venues. Standard library only; nothing is downloaded.

A contributor, usually through an agent, submits a small JSON file of papers
under community/papers/. Validation checks its structure, the venue registry,
the official host and duplicates against the published collection. A maintainer
reviews the pull request and runs `apply`, which appends the papers to
evolve/corpus.json and the abstract shards. New papers start without
connections, so they are open for anyone to propose pairs.
"""
import argparse
import collections
import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse
import community_edges as C
from voyage_pipeline import ROOT, atomic_json

VERSION = 'paper-evolve-papers-v1'
VENUES_VERSION = 'paper-evolve-venues-v1'
FIELDS = {'title', 'year', 'venue', 'url', 'abstract', 'abstract_source_url', 'retrieved_at', 'topic'}
LOOSE = 'Unclustered'  # the collection's name for "no topic assigned yet"
compact = lambda text: ''.join(c.casefold() for c in text if c.isalnum())
clean = lambda text: ' '.join(text.split())


def registry(root=ROOT):
    """Venue id -> {'id', 'name', 'hosts'}: the one place a venue is declared."""
    document = C.read_json(Path(root) / 'community/venues.json')
    if document.get('version') != VENUES_VERSION or not isinstance(document.get('venues'), list):
        raise ValueError('Unsupported venue registry.')
    venues = {}
    for venue in document['venues']:
        if (not isinstance(venue, dict) or set(venue) != {'id', 'name', 'hosts'}
                or not isinstance(venue['id'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,30}', venue['id']) or venue['id'] in venues
                or not isinstance(venue['name'], str) or not 2 <= len(venue['name'].strip()) <= 60
                or not isinstance(venue['hosts'], list) or not venue['hosts']
                or any(not isinstance(h, str) or not re.fullmatch(r'(?:[a-z0-9-]+\.)+[a-z]{2,}', h) for h in venue['hosts'])):
            raise ValueError('Each venue needs a unique lowercase id, a display name and its official host names.')
        venues[venue['id']] = venue
    return venues


def add_venue(identity, name, hosts, root=ROOT):
    path = Path(root) / 'community/venues.json'
    document = C.read_json(path)
    if identity in registry(root):
        raise ValueError(f'Venue {identity} is already registered.')
    document['venues'].append({'id': identity, 'name': name.strip(), 'hosts': [h.strip().lower() for h in hosts]})
    previous = path.read_text()
    atomic_json(path, document)
    try:
        registry(root)
    except ValueError:
        path.write_text(previous)
        raise
    return {'venue': identity, 'file': path.relative_to(root).as_posix()}


def topics(root=ROOT):
    """Topic -> research area, as the published collection groups them."""
    areas = collections.defaultdict(collections.Counter)
    for row in json.loads((Path(root) / 'evolve/corpus.json').read_text()):
        areas[row.get('topic') or LOOSE][row.get('mega') or LOOSE] += 1
    # A paper without a topic also has no area, whichever area most untopiced papers happen to sit in.
    return {**{topic: counts.most_common(1)[0][0] for topic, counts in areas.items()}, LOOSE: LOOSE}


def public_url(url, hosts):
    p = parse.urlsplit(url) if isinstance(url, str) else None
    if (not p or p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443) or p.fragment
            or {k.lower() for k in parse.parse_qs(p.query)} & {'token', 'api_key', 'apikey', 'access_token', 'secret', 'password'}):
        return ''
    return url


class Known:
    """What is already in the collection, so a paper is never listed twice."""

    def __init__(self, rows):
        self.urls = {row['u'].rstrip('/') for row in rows}
        self.titles = {(compact(row['t']), row['y']) for row in rows}

    def claim(self, paper):
        key = (compact(paper['title']), paper['year'])
        if paper['url'].rstrip('/') in self.urls or key in self.titles:
            raise ValueError(f"Already in the collection: {paper['title']} ({paper['year']})")
        self.urls.add(paper['url'].rstrip('/'))
        self.titles.add(key)


def validate(document, root=ROOT, known=None, areas=None):
    """Return the collection rows and abstract records for one submitted file."""
    root = Path(root)
    venues, areas = registry(root), areas or topics(root)
    known = known or Known(json.loads((root / 'evolve/corpus.json').read_text()))
    every_host = {host for venue in venues.values() for host in venue['hosts']}
    if not isinstance(document, dict) or set(document) != {'version', 'contributor', 'papers'} or document['version'] != VERSION:
        raise ValueError('Unsupported paper submission format.')
    contributor = document['contributor']
    if (not isinstance(contributor, dict) or set(contributor) != {'name', 'tool'}
            or not all(isinstance(v, str) and 0 < len(v.strip()) <= 300 for v in contributor.values())):
        raise ValueError('Declare the contributor name and the tool or agent used.')
    papers = document['papers']
    if not isinstance(papers, list) or not 1 <= len(papers) <= 5000:
        raise ValueError('Submit between 1 and 5000 papers per file.')
    this_year, rows = datetime.now(timezone.utc).year, []
    for paper in papers:
        if not isinstance(paper, dict) or set(paper) != FIELDS:
            raise ValueError('Each paper needs exactly: ' + ', '.join(sorted(FIELDS)))
        title, abstract = paper['title'], paper['abstract']
        label = title if isinstance(title, str) else 'a paper'
        if not isinstance(title, str) or title != clean(title) or not 5 <= len(title) <= 400:
            raise ValueError(f'{label}: the title must be 5–400 characters with single spaces.')
        if not isinstance(abstract, str) or abstract != clean(abstract) or not 80 <= len(abstract) <= 12000:
            raise ValueError(f'{label}: the abstract must be the full published abstract (80–12000 characters).')
        if type(paper['year']) is not int or not 1950 <= paper['year'] <= this_year + 1:
            raise ValueError(f'{label}: the publication year is out of range.')
        if paper['venue'] not in venues:
            raise ValueError(f"{label}: venue {paper['venue']!r} is not registered. Add it with the add-venue command first.")
        if not public_url(paper['url'], venues[paper['venue']]['hosts']):
            raise ValueError(f"{label}: use the paper's public HTTPS page on {' or '.join(venues[paper['venue']]['hosts'])}.")
        if not public_url(paper['abstract_source_url'], every_host | {'arxiv.org'}):
            raise ValueError(f'{label}: the abstract source must be a public page on a registered venue host or arxiv.org.')
        try:
            stamp = datetime.fromisoformat(paper['retrieved_at'])
        except (TypeError, ValueError):
            stamp = None
        if stamp is None or stamp.tzinfo is None:
            raise ValueError(f'{label}: retrieved_at must be an ISO timestamp with a timezone.')
        if paper['topic'] not in areas:
            raise ValueError(f"{label}: unknown topic {paper['topic']!r}. List topics with the topics command, or use {LOOSE!r}.")
        known.claim(paper)
        rows.append(paper)
    return rows


def submit(source, name, tool, root=ROOT):
    """Turn an agent-written list of papers into a validated submission file plus Git steps."""
    root = Path(root)
    listed = C.read_json(source)
    listed = listed.get('papers') if isinstance(listed, dict) else listed
    if not isinstance(listed, list) or not all(isinstance(p, dict) for p in listed):
        raise ValueError('The input file must be a JSON list of papers.')
    now, papers = datetime.now(timezone.utc).isoformat(), []
    for paper in listed:
        missing = {'title', 'year', 'venue', 'url', 'abstract'} - set(paper)
        if missing or set(paper) - FIELDS:
            raise ValueError('Each paper needs title, year, venue, url and abstract; optional: abstract_source_url, retrieved_at, topic.')
        papers.append({'title': clean(str(paper['title'])), 'year': paper['year'], 'venue': paper['venue'], 'url': paper['url'],
                       'abstract': clean(str(paper['abstract'])), 'abstract_source_url': paper.get('abstract_source_url') or paper['url'],
                       'retrieved_at': paper.get('retrieved_at') or now, 'topic': paper.get('topic') or LOOSE})
    document = {'version': VERSION, 'contributor': {'name': name.strip(), 'tool': tool.strip()}, 'papers': papers}
    known, areas = Known(json.loads((root / 'evolve/corpus.json').read_text())), topics(root)
    for path in sorted((root / 'community/papers').glob('*.json')):  # submissions still waiting for review count too
        validate(C.read_json(path), root, known, areas)
    validate(document, root, known, areas)
    slug = lambda text: re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:35]
    venues = sorted({p['venue'] for p in papers})
    identity = f"{'-'.join(venues)[:40]}-{slug(name) or 'contributor'}-{C.digest(document)[:8]}"
    path = root / 'community/papers' / (identity + '.json')
    atomic_json(path, document)
    relative, branch = path.relative_to(root).as_posix(), 'papers/' + identity
    return {'papers': len(papers), 'venues': venues, 'output': relative, 'branch': branch, 'pushed': False,
            'commands': [f'git switch -c {shlex.quote(branch)}', 'python scripts/community_edges.py check',
                         f'git add -- {shlex.quote(relative)} community/venues.json',
                         f'git commit -m {shlex.quote(f"Add {len(papers)} paper(s): " + ", ".join(venues))}',
                         f'git push -u origin {shlex.quote(branch)}']}


def check(root=ROOT):
    """Validate the registry and every submission still waiting for a maintainer."""
    root = Path(root)
    registry(root)
    known, areas, count = Known(json.loads((root / 'evolve/corpus.json').read_text())), topics(root), 0
    for path in sorted((root / 'community/papers').glob('*.json')):
        try:
            count += len(validate(C.read_json(path), root, known, areas))
        except ValueError as exc:
            raise ValueError(f'{path.name}: {exc}') from None
    return count


def apply(root=ROOT):
    """Maintainer step: append every waiting submission to the published collection."""
    from export_abstracts import write_json
    root = Path(root)
    pending = sorted((root / 'community/papers').glob('*.json'))
    corpus_path, shards = root / 'evolve/corpus.json', root / 'evolve/generated/abstracts'
    rows, meta = json.loads(corpus_path.read_text()), json.loads((shards / 'meta.json').read_text())
    if meta['total'] != len(rows):
        raise ValueError('Abstract shards and the collection disagree; rebuild the abstracts before adding papers.')
    known, areas, added = Known(rows), topics(root), []
    for path in pending:
        added += validate(C.read_json(path), root, known, areas)
    if not added:
        return {'applied_files': 0, 'papers': 0, 'total': len(rows)}
    size, first = meta['shard_size'], len(rows)
    for paper in added:
        rows.append({'t': paper['title'], 'v': paper['venue'], 'y': paper['year'], 'u': paper['url'], 'mega': areas[paper['topic']],
                     'topic': paper['topic'], 'leaf': LOOSE, 'src': 'community'})
    for shard in range(first // size, (len(rows) - 1) // size + 1):
        path = shards / f'{shard:03d}.json'
        entries = json.loads(path.read_text()) if path.exists() else []
        entries += [{'url': p['url'], 'abstract': p['abstract'], 'source_url': p['abstract_source_url'], 'retrieved_at': p['retrieved_at']}
                    for p in added[max(0, shard * size - first):(shard + 1) * size - first]]
        write_json(path, entries)
    write_json(shards / 'meta.json', {**meta, 'total': len(rows), 'abstracts': len(rows), 'shards': (len(rows) + size - 1) // size,
                                      'updated_at': datetime.now(timezone.utc).isoformat()})
    corpus_path.write_text(json.dumps(rows, separators=(',', ':')))  # the published file's exact formatting
    (root / 'community/papers/applied').mkdir(exist_ok=True)
    for path in pending:
        path.rename(path.parent / 'applied' / path.name)
    return {'applied_files': len(pending), 'papers': len(added), 'total': len(rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['check', 'apply'])
    args = ap.parse_args()
    print(json.dumps({'waiting_papers': check()} if args.command == 'check' else apply()))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit(f'Paper additions failed: {exc}')
