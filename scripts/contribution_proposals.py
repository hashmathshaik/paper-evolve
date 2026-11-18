"""Contributor-proposed pairs: a one-task pack rebuilt from public corpus files only.

A proposal carries no prepared passages. Its state is a pure function of
evolve/corpus.json and the published abstract shards, so validation regenerates
it and rejects a pack whose title, year, abstract or source URL was altered.
Full-text evidence arrives only through fetch/cite, with page provenance.
"""
import json
from pathlib import Path
import community_edges as C
from voyage_pipeline import ROOT, atomic_json, read_records

ORIGIN = 'contributor_proposal'
# Must stay identical to the venue names in edges_jev.papers(), which built the prepared packs.
VENUES = {'aclanthology.org': 'ACL Anthology', 'openreview.net': 'ICLR', 'papers.nips.cc': 'NeurIPS',
          'proceedings.mlr.press': 'ICML'}
compact = lambda text: ''.join(c.casefold() for c in text if c.isalnum())


def corpus(root=ROOT):
    path = Path(root) / 'evolve/corpus.json'
    return read_records('corpus', input_path=path), json.loads(path.read_text())


def find(query, records, raw):
    """Indices of papers matching an ID, a source URL, an exact title, or else every title word."""
    q = query.strip()
    hits = [i for i, r in enumerate(records) if q == r['id'] or q.rstrip('/') == r['source_url'].rstrip('/')]
    hits = hits or [i for i, r in enumerate(records) if compact(r['title']) == compact(q)]
    words = q.casefold().split()
    return hits or [i for i, r in enumerate(records) if words and all(w in r['title'].casefold() for w in words)]


def describe(index, records, raw):
    r = records[index]
    return {'id': r['id'], 'year': r['year'], 'title': r['title'], 'url': r['source_url'], 'topic': raw[index].get('topic', '')}


def card(index, records, raw, root):
    meta = json.loads((Path(root) / 'evolve/generated/abstracts/meta.json').read_text())
    shard = Path(root) / 'evolve/generated/abstracts' / f"{index // meta['shard_size']:03d}.json"
    row = json.loads(shard.read_text())[index % meta['shard_size']]
    record = records[index]
    if row['url'] != record['source_url']:
        raise ValueError('Published abstracts are out of date for this paper.')
    if raw[index].get('src') == 'community':  # contributor-added paper: its venue comes from the registry
        from contribution_papers import registry
        venue = registry(root)[raw[index]['v']]['name']
    else:
        venue = VENUES.get(record['source_url'].split('/')[2], '')
    return {'title': record['title'], 'year': record['year'], 'venue': venue, 'abstract': row['abstract']}


def build(a, b, records, raw, root=ROOT):
    state = {'paper_a': card(a, records, raw, root), 'paper_b': card(b, records, raw, root),
             'reference_list_contains_a': None,  # unavailable in a clone; None never means absent
             'citing_sentence': '',
             'source_evidence': {'status': 'needs_context', 'passages': [], 'documents': {}}}
    topic = raw[b].get('topic') or 'Unclustered'
    papers = {records[i]['id']: records[i] for i in (a, b)}
    task = C.make_task(records[a]['id'], records[b]['id'], state, papers, {'queue': ORIGIN, 'later_paper_topic': topic})
    return {'version': C.VERSION, 'topic': topic, 'area': raw[b].get('mega') or 'Unclustered', 'origin': ORIGIN,
            'description': 'A contributor proposed this pair. All evidence must come from the full papers.',
            'tasks': [task]}


def propose(earlier, later, root=ROOT):
    root = Path(root)
    records, raw = corpus(root)

    def one(query, role):
        hits = find(query, records, raw)
        if len(hits) != 1:
            shown = '\n'.join(f"  {records[i]['id']}  {records[i]['year']}  {records[i]['title']}" for i in hits[:8])
            raise ValueError(f'{role} paper: ' + (f'{len(hits)} papers match; use one of these IDs:\n{shown}' if hits
                                                  else 'no paper matches. Try the find command.'))
        return hits[0]

    a, b = one(earlier, 'Earlier'), one(later, 'Later')
    if records[a]['year'] >= records[b]['year']:
        raise ValueError('The earlier paper must be from an earlier year than the later one; swap them or pick another pair.')
    pack = build(a, b, records, raw, root)
    task = pack['tasks'][0]
    for path in sorted((root / 'community/tasks').glob('*.json')):
        if any((t['a'], t['b']) == (task['a'], task['b']) for t in C.read_json(path)['tasks']):
            raise ValueError(f'This pair is already a task in pack {path.stem}. Use: start --pack {path.stem} --task {task["id"]}')
    if (task['a'], task['b']) in C.load_approved(root / 'community/approved'):
        raise ValueError('This pair has already been accepted into the graph.')
    path = root / 'community/tasks' / ('proposal-' + task['id'][5:] + '.json')
    atomic_json(path, pack)
    return {'pack': path.stem, 'path': path.relative_to(root).as_posix(), 'task_id': task['id'],
            'earlier': describe(a, records, raw), 'later': describe(b, records, raw)}


def is_proposal(name, pack):
    return pack.get('origin') == ORIGIN or name.startswith('proposal-')


def verify(name, pack, root=ROOT):
    """A proposal pack must be exactly what this module builds from the public corpus."""
    tasks = pack.get('tasks', [])
    if pack.get('origin') != ORIGIN or len(tasks) != 1 or name != 'proposal-' + tasks[0]['id'][5:]:
        raise ValueError(f'{name}: a proposal pack holds one contributor-proposed pair under its task name.')
    records, raw = corpus(root)
    index = {r['id']: i for i, r in enumerate(records)}
    a, b = index.get(tasks[0]['a']), index.get(tasks[0]['b'])
    if a is None or b is None or C.digest(build(a, b, records, raw, root)) != C.digest(pack):
        raise ValueError(f'{name}: proposal differs from the public corpus record for this pair.')
