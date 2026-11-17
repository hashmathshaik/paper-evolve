"""Offline topic-pack preparation and reproducible public contributor bundles.

Export reads the maintainer's caches without fetching sources or calling models.
Catalog/build use committed task packs only, so GitHub Pages needs no backend.
"""
import argparse
import collections
import json
import re
import sqlite3
import zipfile
from pathlib import Path
import community_edges as C
from voyage_pipeline import ROOT, atomic_json, read_records

PORTABLE = ['paper_evolve.py', 'scripts/contribute.py', 'scripts/contribution_workspace.py',
            'scripts/contribution_api.py', 'scripts/community_edges.py', 'scripts/relation_core.py',
            'scripts/edges_jev.py', 'scripts/voyage_pipeline.py', 'community/REVIEW_PROMPT.md',
            'community/decision.schema.json', 'community/API.md', 'community/CLONE.md',
            'scripts/contribution_repository.py', 'scripts/contribution_sources.py', 'community/RESEARCH.md']


def slug(value):
    return (re.sub(r'[^a-z0-9]+', '-', value.casefold()).strip('-')[:65] or 'research')


def corpus_topics(root):
    path = Path(root) / 'evolve/corpus.json'
    topics = collections.defaultdict(lambda: {'papers': 0, 'areas': collections.Counter()})
    if path.exists():
        for row in json.loads(path.read_text()):
            name = row.get('topic') or 'Unclustered'
            topics[name]['papers'] += 1
            topics[name]['areas'][row.get('mega') or 'Unclustered'] += 1
    return topics


def catalog(root=ROOT, write=True):
    root = Path(root)
    community = root / 'community'
    occupied = set()
    for path in sorted((community / 'submissions').glob('*.json')):
        doc = C.read_json(path)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,120}', doc['pack']):raise ValueError('Invalid submission pack ID.')
        pack = C.read_json(community / 'tasks' / (doc['pack'] + '.json'))
        for row in C.validate_submission(pack, doc['submission']):
            occupied.add((row['task_id'], C.task_index(pack)[row['task_id']]['sha256']))
    approved = C.load_approved(community / 'approved')
    for path in (community / 'approved').glob('*.json'):
        doc = C.read_json(path)
        occupied.update((r['task_id'], r['task_sha256']) for r in doc['submission']['decisions'])
    topics = corpus_topics(root)
    packs = []
    issued = set()
    for path in sorted((community / 'tasks').glob('*.json')):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,120}', path.stem):raise ValueError('Task pack filenames must use letters, digits, underscores or hyphens.')
        pack = C.read_json(path)
        tasks = C.task_index(pack)
        fingerprints = {(t['id'], t['sha256']) for t in tasks.values()}
        if issued.intersection(fingerprints):raise ValueError('Task snapshot appears in multiple packs; issue distinct pairs or an explicit evidence revision.')
        issued.update(fingerprints)
        available = [identity for identity in tasks if (identity, tasks[identity]['sha256']) not in occupied]
        topic = pack.get('topic', 'Starter collection')
        area = pack.get('area', 'Across research areas')
        sample = next(iter(tasks.values()), None)
        packs.append({'id': path.stem, 'path': 'tasks/' + path.name, 'tasks': len(tasks),
                      'legacy': 'topic' not in pack,
                      'sha256': C.digest(pack), 'topic': topic, 'area': area,
                      'available_tasks': len(available), 'available_task_ids': available,
                      'fulltext_tasks': sum(tasks[t]['state'].get('source_evidence', {}).get('status') == 'ready' for t in available),
                      'bundle': 'bundles/paper-evolve-' + path.stem + '.zip',
                      'sample': [sample['state']['paper_' + side]['title'] for side in ('a', 'b')] if sample else []})
    topic_rows = []
    for name, stats in sorted(topics.items()):
        matching = [p for p in packs if p['topic'] == name]
        topic_rows.append({'name': name, 'area': stats['areas'].most_common(1)[0][0], 'papers': stats['papers'],
                           'packs': len(matching), 'available_tasks': sum(p['available_tasks'] for p in matching)})
    result = {'version': C.VERSION, 'packs': packs, 'topics': topic_rows,
              'summary': {'topics': len(topic_rows), 'packs': len(packs), 'tasks': sum(p['tasks'] for p in packs),
                          'available_tasks': sum(p['available_tasks'] for p in packs),
                          'fulltext_tasks': sum(p['fulltext_tasks'] for p in packs), 'approved_pairs': len(approved)},
              'availability': 'Snapshot at site build. Coordinate on the pull request to avoid overlapping work.'}
    result['summary']['topic_tasks'] = sum(p['available_tasks'] for p in packs if not p['legacy'])
    result['summary']['topic_fulltext_tasks'] = sum(p['fulltext_tasks'] for p in packs if not p['legacy'])
    if write:atomic_json(community / 'task-manifest.json', result)
    return result


def bundles(root=ROOT, output=None):
    root = Path(root)
    result = catalog(root)
    output = Path(output) if output else root / 'community/bundles'
    output.mkdir(parents=True, exist_ok=True)
    for pack in result['packs']:
        prefix = 'paper-evolve-' + pack['id']
        readme = f'''# Paper Evolve · {pack['topic']}

This bundle contains frozen paper tasks, source passages, the shared prompt,
schema and a Python standard-library contributor tool. Validation needs Python
3.10+ without package installation; full-paper extraction additionally needs
pdftotext or pypdf. No model API key is needed for the agent route.

You can also work directly from a fork/clone of Paper Evolve. All topic packs
are included there. See community/CLONE.md for clone, branch and pull request
instructions. The hosted Pages site serves the app; GitHub receives submissions.

1. Open this folder in your terminal or agent.
2. Prepare up to 10 available tasks (replace name and exact model version):

    python paper_evolve.py start --pack {pack['id']} --name "Your name" --tool "Codex or Claude Code / exact model"

3. Give Claude Code or Codex this instruction:

    Read work/contributions/{pack['id']}/PROMPT.md and community/RESEARCH.md. Download and read full public papers, investigate the contribution link, and register new page excerpts with fetch/cite when needed. Complete submission.json, validate, and prepare a PR without approving or publishing it.

4. Check and export:

    python paper_evolve.py check --workspace work/contributions/{pack['id']}
    python paper_evolve.py export --workspace work/contributions/{pack['id']} --output community/submissions/{pack['id']}-your-name.json

When working in a clone, `python paper_evolve.py pr --workspace
work/contributions/{pack['id']}` can export the submission and generate a PR
description and Git steps instead. It never pushes or creates a PR itself.

Copy the exported JSON into the same path in your fork of Paper Evolve and open
a pull request. Only submit your contribution file. Keep the original task pack
unchanged. A separate maintainer checks the sources and accepts it before it
appears on the public graph. Validation is not scientific verification.

For API inference, read community/API.md and start with --method api in a
different workspace. No request runs until you explicitly run the api command
with your own key, model, current prices and budget. API results use the same
submission format and acceptance process.

Availability is a build-time snapshot. Check existing contributions before
working on a pack. Cloud agent subscriptions remain your own; model weights do
not run on your laptop unless you explicitly use a local model.
'''
        files = {name: (root / name).read_bytes() for name in PORTABLE}
        files['community/tasks/' + pack['id'] + '.json'] = (root / 'community' / pack['path']).read_bytes()
        files['community/task-manifest.json'] = json.dumps({**result, 'packs': [pack]}, ensure_ascii=False, indent=2).encode()
        from contribution_repository import project
        files['community/project.json'] = json.dumps(project(root), indent=2).encode()
        files['README.md'] = readme.encode()
        files['AGENTS.md'] = b'Read README.md and community/RESEARCH.md. Agent reviews may download and read public full papers and register page-specific evidence with fetch/cite. Keep original task packs unchanged. Never access credentials, run paid model API requests, or approve your own contribution.\n'
        files['CLAUDE.md'] = files['AGENTS.md']
        with zipfile.ZipFile(output / ('paper-evolve-' + pack['id'] + '.zip'), 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                info = zipfile.ZipInfo(prefix + '/' + name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
    return result


def export_topics(pack_size=10, packs_per_topic=1, root=ROOT):
    """Prepare topic queues from cached sources first, citations second. No API."""
    root = Path(root)
    if not 1 <= pack_size <= 100 or not 1 <= packs_per_topic <= 10:
        raise ValueError('Use 1–100 tasks per pack and 1–10 packs per topic.')
    import relation_core as H
    import evidence_packets as E
    from edge_priority import citation_pairs
    papers = H.J.papers()
    raw = json.loads((root / 'evolve/corpus.json').read_text())
    records = read_records('corpus', root / 'evolve/corpus.json')
    groups = {p['id']: r for p, r in zip(records, raw)}
    with sqlite3.connect(root / 'work/edges/relations.sqlite3') as db:
        known = {(a, b) for a, b in db.execute("SELECT a,b FROM calls WHERE status IN ('complete','reserved','unknown','invalid','seed_proposed')")}
    for path in (root / 'community/tasks').glob('*.json'):
        known.update((t['a'], t['b']) for t in C.task_index(C.read_json(path)).values())
    known.update(C.load_approved(root / 'community/approved'))
    cites, contexts = H.J.cites(), H.J.contexts()
    chosen = collections.defaultdict(list)
    target = pack_size * packs_per_topic

    def offer(a, b, source):
        if (a, b) in known or a not in papers or b not in papers:return
        topic = groups[b].get('topic') or 'Unclustered'
        if len(chosen[topic]) >= target or papers[a]['year'] >= papers[b]['year']:return
        if E.compact(papers[a]['title']) == E.compact(papers[b]['title']):return
        state = H.make_state(a, b, papers, cites, contexts)
        if source == 'cached_source' and state.get('source_evidence', {}).get('status') != 'ready':return
        if not state.get('source_evidence'):
            state['source_evidence'] = {'status': 'needs_context', 'passages': [], 'documents': {}}
        chosen[topic].append(C.make_task(a, b, state, papers, {'queue': source, 'later_paper_topic': topic}))
        known.add((a, b))

    for path in sorted((root / 'work/evidence/pairs').glob('*.json')):
        packet = C.read_json(path)
        if packet.get('status') == 'ready':offer(packet['a'], packet['b'], 'cached_source')
    candidates = citation_pairs(papers, cites, contexts)
    cached = {}
    for pid, paper in papers.items():
        path = root / 'work/evidence' / (E.digest(paper['source_url']) + '.json')
        if path.exists():
            with path.open() as stream:head = stream.read(200)
            if re.search(r'"status"\s*:\s*"ready"', head):cached[pid] = path
    # Prepare fresh citing paragraphs from documents already on disk. This is
    # deliberately offline: never call document(), get(), or a model here.
    attempts = collections.Counter()
    for a, b in sorted(candidates, key=lambda pair: (not bool(contexts.get((cites[0].get(pair[1]), cites[0].get(pair[0])))), pair)):
        topic = groups[b].get('topic') or 'Unclustered'
        if ((a, b) in known or len(chosen[topic]) >= target or a not in cached or b not in cached
                or attempts[topic] >= 150):continue
        state = H.make_state(a, b, papers, cites, contexts)
        if state.get('source_evidence'):continue  # Unchanged extractor already tried this pair.
        attempts[topic] += 1
        docs = {role: C.read_json(cached[pid]) for role, pid in [('a', a), ('b', b)]}
        passages = E.choose_passages(docs['a'], papers[a]['title'], role='a')
        passages += E.choose_passages(docs['b'], papers[a]['title'], state.get('citing_sentence', ''), role='b')
        packet = {'version': E.VERSION, 'a': a, 'b': b,
                  'input_sha256': E.digest(json.dumps([state['paper_a'], state['paper_b']], sort_keys=True)),
                  'status': 'ready' if any(p['kind'] == 'citation' for p in passages) else 'needs_context',
                  'documents': {role: {k: v for k, v in doc.items() if k != 'text'} for role, doc in docs.items()},
                  'passages': passages}
        atomic_json(root / 'work/evidence/pairs' / (E.digest(a + '|' + b) + '.json'), packet)
        if packet['status'] == 'ready':offer(a, b, 'cached_source')
    for a, b in sorted(candidates):
        offer(a, b, 'citation_needs_source')
    created = []
    for topic, tasks in sorted(chosen.items()):
        area = groups[tasks[0]['b']].get('mega') or 'Unclustered'
        for offset in range(0, len(tasks), pack_size):
            batch = tasks[offset:offset + pack_size]
            identity = slug(topic) + '-' + C.digest(batch)[:10]
            pack = {'version': C.VERSION, 'topic': topic, 'area': area,
                    'description': 'Investigate contribution links from earlier papers to later work in this topic.',
                    'tasks': batch}
            C.task_index(pack)
            path = root / 'community/tasks' / (identity + '.json')
            if path.exists():raise ValueError('Task pack already exists; evidence snapshots are immutable.')
            atomic_json(path, pack)
            created.append(identity)
    catalog(root)
    return {'created_packs': len(created), 'tasks': sum(len(t) for t in chosen.values()), 'ids': created}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['export', 'catalog', 'bundles'])
    ap.add_argument('--pack-size', type=int, default=10)
    ap.add_argument('--packs-per-topic', type=int, default=1)
    args = ap.parse_args()
    result = export_topics(args.pack_size, args.packs_per_topic) if args.command == 'export' else (bundles() if args.command == 'bundles' else catalog())
    print(json.dumps(result.get('summary', result)))


if __name__ == '__main__':main()
