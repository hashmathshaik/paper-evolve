"""Portable, API-free edge review tasks, validation and maintainer acceptance.

Export needs the local corpus. Validation and acceptance use Python's standard
library and prepared/registered source snapshots. Neither executes a model or submitted code.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import relation_core as H
from voyage_pipeline import ROOT, atomic_json

VERSION = 'paper-evolve-review-v1'
COMMUNITY = ROOT / 'community'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise ValueError('Review file exceeds 20 MB; split it into smaller packs.')
    return json.loads(path.read_text())


def make_task(a, b, state, papers, priority=None):
    task = {'id': 'edge-' + hashlib.sha256((a + '|' + b).encode()).hexdigest()[:24],
            'a': a, 'b': b, 'state': state,
            'sources': {side: {'paper_id': pid, 'url': papers[pid]['source_url']}
                        for side, pid in [('a', a), ('b', b)]},
            'priority': priority or {}}
    task['sha256'] = digest(task)
    return task


def task_index(pack):
    if not isinstance(pack, dict) or pack.get('version') != VERSION or not isinstance(pack.get('tasks'), list):
        raise ValueError('Unsupported task pack.')
    result = {}
    for task in pack['tasks']:
        if task.get('sha256') != digest({k: v for k, v in task.items() if k != 'sha256'}):
            raise ValueError('Task evidence fingerprint does not match.')
        identity = task['id']
        expected = 'edge-' + hashlib.sha256((task['a'] + '|' + task['b']).encode()).hexdigest()[:24]
        if identity != expected or identity in result or task['a'] == task['b']:
            raise ValueError('Invalid or duplicate task identity.')
        state = task['state']
        for side in ('a', 'b'):
            paper = state['paper_' + side]
            if not all(isinstance(paper.get(k), str) and paper[k].strip() for k in ('title', 'abstract')):
                raise ValueError('Both paper titles and abstracts are required.')
            if type(paper.get('year')) is not int:
                raise ValueError('Publication years must be integers.')
            source = task['sources'][side]
            if source['paper_id'] != task[side] or not source['url'].startswith('https://'):
                raise ValueError('Missing paper source URL.')
        if state['paper_a']['year'] >= state['paper_b']['year']:
            raise ValueError('Task must point from an earlier to a later paper.')
        result[identity] = task
    return result


def validate_decision(decision, state):
    if not isinstance(decision, dict) or set(decision) != set(H.SCHEMA['properties']):
        raise ValueError('Decision must match the supplied schema exactly.')
    if type(decision['related']) is not bool:
        raise ValueError('related must be a boolean.')
    for field in ('reason', 'inherited', 'changed'):
        if not isinstance(decision[field], str) or len(decision[field]) > 4000:
            raise ValueError('Invalid explanation.')
    if not decision['reason'].strip():
        raise ValueError('Explain the decision, including an abstention.')
    if not isinstance(decision['relations'], list) or not isinstance(decision['evidence'], list):
        raise ValueError('Relations and evidence must be lists.')
    seen = set()
    for relation in decision['relations']:
        if not isinstance(relation, dict) or set(relation) != {'type', 'confidence'}:
            raise ValueError('Invalid relation entry.')
        name, confidence = relation['type'], relation['confidence']
        if name not in H.TYPES or name in seen or type(confidence) not in (int, float) or not math.isfinite(confidence) or not .85 <= confidence <= 1:
            raise ValueError('Unknown/duplicate type or confidence outside .85–1.')
        seen.add(name)
    if len(decision['evidence']) > 16:
        raise ValueError('Use at most 16 diagnostic quotations.')
    for entry in decision['evidence']:
        if not isinstance(entry, dict) or set(entry) != {'source', 'quote'} or not isinstance(entry['quote'], str):
            raise ValueError('Evidence must contain a source ID and exact quote.')
    result = H.validate(decision, state)
    # H.validate is tolerant for provider outputs; public submissions fail on
    # *any* fabricated quotation instead of silently dropping the bad entries.
    if len(result['evidence']) != len(decision['evidence']):
        raise ValueError('Every quotation must match its named task source exactly.')
    if decision['related']:
        if not result['related'] or set(result['types']) != seen:
            raise ValueError('Positive decision lacks the required evidence or valid types.')
        sources = {entry['source'] for entry in result['evidence']}
        if not any(s.startswith('a_') for s in sources) or not any(s.startswith('b_') or s == 'citing_sentence' for s in sources):
            raise ValueError('Positive edges need evidence from both papers.')
        if result['basis'] != 'explicit_statement':
            raise ValueError('Community seed edges need an explicit contribution link; abstain if uncertain.')
    elif decision['relations'] or decision['inherited'].strip() or decision['changed'].strip():
        raise ValueError('Abstentions cannot carry relationship labels or inherited/changed claims.')
    return result


def validate_submission(pack, submission):
    tasks = task_index(pack)
    if not isinstance(submission, dict) or set(submission) != {'version', 'contributor', 'decisions'} or submission['version'] != VERSION:
        raise ValueError('Unsupported submission format.')
    contributor = submission['contributor']
    if not isinstance(contributor, dict) or set(contributor) != {'name', 'tool', 'method'}:
        raise ValueError('Declare contributor name, tool/model version and method.')
    if contributor['method'] not in ('manual', 'local_model', 'assistant', 'api') or not all(isinstance(contributor[k], str) and 0 < len(contributor[k].strip()) <= 300 for k in contributor):
        raise ValueError('Invalid contributor metadata.')
    rows = submission['decisions']
    if not isinstance(rows, list) or not rows:
        raise ValueError('Submission must contain at least one decision.')
    seen = set()
    output = []
    for row in rows:
        if not isinstance(row, dict) or set(row) not in ({'task_id', 'task_sha256', 'decision'}, {'task_id', 'task_sha256', 'decision', 'source_material'}):
            raise ValueError('Invalid task decision envelope.')
        identity = row['task_id']
        if identity in seen or identity not in tasks:
            raise ValueError('Duplicate or unknown task ID.')
        seen.add(identity)
        task = tasks[identity]
        if row['task_sha256'] != task['sha256']:
            raise ValueError('Submission uses a different task/evidence version.')
        state = task['state']
        if 'source_material' in row:
            from contribution_sources import augment
            state = augment(task,row['source_material'])
        result = validate_decision(row['decision'], state)
        if 'source_material' in row:result['research_provenance'] = state['source_evidence']['research_provenance']
        output.append({'a': task['a'], 'b': task['b'], 'state': state, 'result': result, 'task_id': identity})
    return output


def accept(pack, submission, destination, reviewer, reviewer_kind, note):
    rows = validate_submission(pack, submission)
    if reviewer_kind not in ('human', 'assistant') or not reviewer.strip() or not note.strip():
        raise ValueError('Record who reviewed the source evidence and their review note.')
    # Save the original inputs. Publication revalidates them; a contributor's
    # self-declared confidence never bypasses this separate maintainer decision.
    approved = {'version': VERSION, 'pack': pack, 'submission': submission,
                'submission_sha256': digest(submission),
                'review': {'reviewer': reviewer, 'kind': reviewer_kind, 'note': note,
                           'reviewed_at': datetime.now(timezone.utc).isoformat()}}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x') as handle:
        json.dump(approved, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    return rows


def load_approved(directory=None):
    best = {}
    for path in sorted((Path(directory) if directory else COMMUNITY / 'approved').glob('*.json')):
        document = read_json(path)
        submission = document['submission']
        review = document['review']
        if document['submission_sha256'] != digest(submission) or review.get('kind') not in ('human', 'assistant') or not review.get('reviewer') or not review.get('note'):
            raise ValueError(f'Invalid acceptance record: {path.name}')
        for row in validate_submission(document['pack'], submission):
            key = (row['a'], row['b'])
            if key in best:
                raise ValueError(f'Duplicate approved pair {key}; reconcile the reviews explicitly.')
            row['result'].update(provider='community', community_review={**review, 'contributor': submission['contributor'],
                'submission_sha256': document['submission_sha256'], 'task_id': row['task_id']},
                human_verified=review['kind'] == 'human')
            row['model'] = submission['contributor']['tool']
            best[key] = row
    return best


def export_static(output=None, corpus_path=None, approved_directory=None):
    """An overlay keeps GitHub Pages builds independent of private SQLite caches.

    Accepted corrections/abstentions override the paid prediction for that pair.
    The base shards are untouched, so removing an acceptance is reversible.
    """
    from voyage_pipeline import read_records
    from relation_review_policy import apply_policy, load_policy
    records = read_records('corpus', input_path=corpus_path)
    index = {row['id']: i for i, row in enumerate(records)}
    entries = {}
    approved = load_approved(approved_directory)
    positives = human = 0
    policies = load_policy()
    for (a, b), row in approved.items():
        for side, pid in [('a', a), ('b', b)]:
            if pid not in index:
                raise ValueError('Approved edge contains an unknown corpus paper.')
            record = records[index[pid]]
            paper = row['state']['paper_' + side]
            if (paper['title'], paper['year']) != (record['title'], record['year']):
                raise ValueError('Approved edge paper metadata differs from the corpus.')
        ia, ib = index[a], index[b]
        for source, target in [(ia, ib), (ib, ia)]:
            item = entries.setdefault(str(source), {'c': [], 'overrides': [], 'checked': 0})
            item['overrides'].append(target)
            item['checked'] += 1
        result = apply_policy(a, b, row['result'], policies)
        if result is None or not result['related']:
            continue
        info = {k: result[k] for k in ('reason', 'inherited', 'changed', 'basis', 'evidence', 'quality_tier', 'community_review', 'human_verified')}
        if result.get('research_provenance'):info['research_provenance']=result['research_provenance']
        info.update(model=row['model'], version=VERSION, citation_backed=row['state'].get('reference_list_contains_a') == 1)
        data = [result['types'], max(result['types'].values()), result['inherited'], result['changed'], None, 'community', info]
        entries[str(ia)]['c'].append([ib, 1] + data)
        entries[str(ib)]['c'].append([ia, -1] + data)
        positives += 1
        human += bool(result['human_verified'])
    payload = {'version': VERSION, 'entries': entries, 'meta': {'approved_pairs': len(approved),
               'positive_edges': positives, 'human_reviewed_edges': human}}
    atomic_json(output or ROOT / 'evolve/generated/community.json', payload)
    return payload


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    export.add_argument('--limit', type=int, default=100)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--pair', nargs=2, action='append', metavar=('EARLIER_ID', 'LATER_ID'), help='Issue a correction task for an existing pair.')
    template = commands.add_parser('template')
    template.add_argument('--pack', type=Path, required=True)
    template.add_argument('--output', type=Path, required=True)
    template.add_argument('--name', required=True)
    template.add_argument('--tool', required=True)
    template.add_argument('--method', choices=['manual', 'local_model', 'assistant', 'api'], required=True)
    for name in ('validate', 'accept'):
        sub = commands.add_parser(name)
        sub.add_argument('--pack', type=Path, required=True)
        sub.add_argument('--submission', type=Path, required=True)
        if name == 'accept':
            sub.add_argument('--reviewer', required=True)
            sub.add_argument('--reviewer-kind', choices=['human', 'assistant'], required=True)
            sub.add_argument('--note', required=True)
    commands.add_parser('check')
    args = ap.parse_args()
    if args.command == 'export':
        if not 1 <= args.limit <= 1000:
            ap.error('Export between 1 and 1000 tasks per pack.')
        if args.output.exists():
            raise ValueError('Task packs are frozen. Use a new filename for a new evidence version.')
        from edge_priority import prepare
        issued = set()
        for path in (COMMUNITY / 'tasks').glob('*.json'):
            issued.update((task['a'], task['b']) for task in task_index(read_json(path)).values())
        ledger, papers, cites, contexts, rows = prepare(args.limit + len(issued))
        if args.pair:
            rows = [{'a': a, 'b': b, 'purpose': 'source_review_or_correction'} for a, b in args.pair]
            if any(r['a'] not in papers or r['b'] not in papers for r in rows):
                raise ValueError('Unknown paper identity in requested pair.')
        else:
            rows = [r for r in rows if (r['a'], r['b']) not in issued][:args.limit]
        tasks = [make_task(r['a'], r['b'], H.make_state(r['a'], r['b'], papers, cites, contexts), papers, r) for r in rows]
        pack = {'version': VERSION, 'tasks': tasks}
        task_index(pack)
        atomic_json(args.output, pack)
        print(json.dumps({'tasks': len(tasks), 'pack_sha256': digest(pack), 'output': str(args.output)}))
    elif args.command == 'template':
        pack = read_json(args.pack)
        tasks = task_index(pack)
        submission = {'version': VERSION, 'contributor': {'name': args.name, 'tool': args.tool, 'method': args.method},
                      'decisions': [{'task_id': task['id'], 'task_sha256': task['sha256'],
                                     'decision': {'related': False, 'basis': 'insufficient_evidence', 'relations': [],
                                                  'reason': '', 'inherited': '', 'changed': '', 'evidence': []}}
                                    for task in tasks.values()]}
        atomic_json(args.output, {'pack': args.pack.stem, 'submission': submission})
        print('Template created. Review the sources and fill each reason; remove tasks you did not review.')
    elif args.command in ('validate', 'accept'):
        pack, submission = read_json(args.pack), read_json(args.submission)
        if isinstance(submission, dict) and set(submission) == {'pack', 'submission'}:
            if submission['pack'] != args.pack.stem:
                raise ValueError('Submission names a different task pack.')
            submission = submission['submission']
        if args.command == 'accept':
            rows = accept(pack, submission, COMMUNITY / 'approved' / (digest(submission) + '.json'), args.reviewer, args.reviewer_kind, args.note)
        else:
            rows = validate_submission(pack, submission)
        print(json.dumps({'validated': len(rows), 'positive_edges': sum(r['result']['related'] for r in rows), 'published': False}))
    else:
        packs = {}
        for path in sorted((COMMUNITY / 'tasks').glob('*.json')):
            pack = read_json(path)
            task_index(pack)
            if pack.get('origin') == 'contributor_proposal' or path.stem.startswith('proposal-'):
                # Contributor-authored packs must match the public corpus exactly.
                from contribution_proposals import verify
                verify(path.stem, pack)
            packs[path.stem] = pack
        count = 0
        seen = set()
        for path in sorted((COMMUNITY / 'submissions').glob('*.json')):
            envelope = read_json(path)
            if set(envelope) != {'pack', 'submission'} or envelope['pack'] not in packs:
                raise ValueError('Submission must identify a committed task pack.')
            rows = validate_submission(packs[envelope['pack']], envelope['submission'])
            for row in rows:
                key = (row['a'], row['b'], next(t['task_sha256'] for t in envelope['submission']['decisions'] if t['task_id'] == row['task_id']))
                if key in seen:raise ValueError('Duplicate submitted pair; reconcile the submissions.')
                seen.add(key)
            count += len(rows)
        approved = load_approved()
        from contribution_packs import catalog
        catalog(ROOT, write=False)
        print(json.dumps({'task_packs': len(packs), 'validated_submissions': count, 'approved_pairs': len(approved)}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit(f'Review validation failed: {exc}')
