"""Build an evidence-first seed pool within the cumulative $30 edge ceiling.

Singapore Qwen3.7-Flash proposals and Qwen3.7-Plus review of positive candidates.
Regular requests; no Beijing and no Batch dependency.
Jev's existing scores rank candidates without new Jev calls. Missing sources are
left for contributors, not converted to unsupported relationships.
"""
import argparse
import fcntl
import json
import signal
import sqlite3
import time
import threading
import edge_priority as P
import evidence_packets as E
import qwen_grouped_edges as G
from edge_publication import publish
from project_budget import configure_edges
from voyage_pipeline import atomic_json
from edge_pipeline import events

WORK = P.H.J.E
PAUSE = WORK / 'SEED_PAUSED'
STATUS = WORK / 'seed-status.json'
REVIEW_MODEL = 'qwen3.7-plus'


def content_rejection(outcome):
    return outcome.get('http_status') == 400 and outcome.get('provider_error_code') == 'data_inspection_failed'


def agree(proposal, review):
    """The second Qwen model sees no proposal; require source-backed type overlap."""
    allowed = {name: score for name, score in review.get('types', {}).items()
               if name in proposal['result'].get('types', {})}
    ready = review.get('quality_tier') == 'fulltext_supported_prediction' and review.get('basis') == 'explicit_statement'
    allowed = allowed if ready and review.get('related') else {}
    result = {**review, 'types': allowed, 'related': bool(allowed),
              'inherited': review['inherited'] if allowed else '', 'changed': review['changed'] if allowed else '',
              'verification': {'method': 'two_qwen_model_agreement', 'proposal_model': G.MODEL,
                               'review_model': REVIEW_MODEL, 'agreed_types': sorted(allowed), 'human_verified': False}}
    checked = G.Q.apply_policy(proposal['a'], proposal['b'], result, G.Q.load_policy())
    return checked if checked is not None else {**result, 'types': {}, 'related': False, 'inherited': '', 'changed': '', 'review_policy_withheld': True}


def verify_proposal(ledger, proposal, transport=None):
    state = proposal['state']
    if state.get('source_evidence', {}).get('status') != 'ready':
        raise ValueError('Seed verification requires a ready source packet.')
    # The reviewer sees only the source state, never the Flash suggestion.
    group = G.reserve_group(ledger, [(proposal['a'], proposal['b'], state)], ledger.budget,
                            model=REVIEW_MODEL, verification=True)
    if isinstance(group, str):
        return {'valid': 0, 'accepted': 0, 'status': group}
    outcome = G.review_group(ledger, group, transport=transport, transform=lambda _, review: agree(proposal, review))
    phase = 'verified' if outcome['valid'] == 1 else ('verification_invalid' if outcome['status'] == 'group_complete' else ('verification_unknown' if outcome['status'] == 'group_unknown' else ('provider_http_' + str(outcome['http_status']) if outcome.get('http_status') else 'verification_needs_attention')))
    return {**outcome, 'status': phase}


def process_review(ledger, job, should_stop, proposal_transport=None, review_transport=None):
    """One bounded pipeline: a proposal then blind review of its positives."""
    stats = {'reviewed': 0, 'proposed': 0, 'verified': 0, 'accepted_predictions': 0,
             'invalid': 0, 'requests': 0, 'verification_requests': 0, 'quarantined_requests': 0}
    kind, value = job
    if should_stop():return {**stats, 'halt': 'paused'}
    if kind == 'verify':
        proposals = [value]
    else:
        group = G.reserve_group(ledger, value, ledger.budget)
        if isinstance(group, str):
            return {**stats, **({'halt': group} if group != 'cached' else {})}
        if should_stop():
            G.settle(ledger, group, {}, 0, failure='rejected')
            return {**stats, 'halt': 'paused'}
        group['verify_positives'] = True
        outcome = G.review_group(ledger, group, transport=proposal_transport)
        stats.update(requests=1, reviewed=outcome['valid'], proposed=outcome['accepted'],
                     invalid=outcome['pairs'] - outcome['valid'])
        if outcome['status'] == 'group_unknown':
            stats['quarantined_requests'] += 1
            return stats
        if content_rejection(outcome):
            stats['invalid'] = 0
            stats['quarantined_requests'] += 1
            return stats
        if outcome['status'] != 'group_complete':
            reason = 'provider_http_' + str(outcome['http_status']) if outcome.get('http_status') else 'review_needs_attention'
            return {**stats, 'halt': reason}
        proposals = []
        for child in group['children']:
            record = ledger.db.execute("SELECT result FROM calls WHERE id=? AND status='seed_proposed'", (child['id'],)).fetchone()
            if record:proposals.append({**child, 'result': json.loads(record[0])})
    for proposal in proposals:
        if should_stop():return {**stats, 'halt': 'paused'}
        verdict = verify_proposal(ledger, proposal, transport=review_transport)
        stats['verification_requests'] += int(verdict.get('pairs', 0) > 0)
        stats['verified'] += verdict['valid']
        stats['accepted_predictions'] += verdict['accepted']
        if not verdict['valid']:
            if verdict['status'] == 'cached':continue
            if content_rejection(verdict):
                stats['quarantined_requests'] += 1
                continue
            if verdict['status'] == 'verification_unknown':
                stats['invalid'] += 1
                stats['quarantined_requests'] += 1
                continue
            stats['invalid'] += int(verdict['status'] == 'verification_invalid')
            if verdict['status'] != 'verification_invalid':return {**stats, 'halt': verdict['status']}
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['plan', 'pilot', 'run', 'status'])
    ap.add_argument('--max-candidates', type=int, default=5000)
    ap.add_argument('--scope', choices=['priority', 'expanded'], default='priority',
                    help='Expanded also checks corpus citations outside embedding neighbours.')
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--source-workers', type=int, default=8)
    ap.add_argument('--group-size', type=int, default=1)
    ap.add_argument('--publish-every', type=int, default=200)
    args = ap.parse_args()
    if args.command == 'status':
        print(STATUS.read_text() if STATUS.exists() else '{"phase":"not_started"}')
        return
    if args.max_candidates < 0 or not 1 <= args.source_workers <= 16 or not 1 <= args.workers <= 32 or not 1 <= args.group_size <= 3 or args.publish_every < 1:
        ap.error('Use a nonnegative candidate limit (0 means all), 1–32 review workers, 1–16 source workers, and groups of 1–3.')
    if args.command != 'plan' and (PAUSE.exists() or G.PAUSE.exists()):
        raise SystemExit('Seed review is paused.')
    WORK.mkdir(parents=True, exist_ok=True)
    lock = (WORK / 'qwen-group-worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A seed/grouped review worker is already running.')
    ledger, papers, cites, contexts, rows = P.prepare(args.max_candidates, budget=30, scope=args.scope)
    if not ledger.project_snapshot():
        raise SystemExit('Historical project accounting is required.')
    workers = min(args.workers, 2) if args.command == 'pilot' else args.workers
    if args.command == 'plan':
        print(json.dumps({'phase': 'plan', 'priority_version': P.VERSION, 'candidate_scope': args.scope, 'ranked_candidates': len(rows),
                          'workers': workers, 'source_workers': args.source_workers,
                          'source_context_candidates': sum(r['citing_context'] for r in rows),
                          'citation_backed_candidates': sum(r['citation_backed'] for r in rows),
                          'budget': ledger.project_snapshot()}))
        return
    configure_edges(ledger, 30)
    G.Q.connection()
    stopped = threading.Event()
    admission_stop = threading.Event()
    def stop(*_):stopped.set()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    def should_stop():
        return stopped.is_set() or PAUSE.exists() or G.PAUSE.exists()
    with sqlite3.connect(P.H.ROOT / 'work/abstracts/cache.sqlite3') as db:
        alternates = dict(db.execute('SELECT url,endpoint FROM abstracts'))
    stats = {'source_checked': 0, 'source_ready': 0, 'needs_context': 0, 'source_errors': 0,
             'reviewed': 0, 'proposed': 0, 'verified': 0, 'accepted_predictions': 0,
             'invalid': 0, 'requests': 0, 'verification_requests': 0, 'quarantined_requests': 0}
    started = time.monotonic()
    initial_spend = ledger.spent()
    ceiling = min(30, initial_spend + .05) if args.command == 'pilot' else 30
    ledger.budget = ceiling
    path = ledger.db.execute('PRAGMA database_list').fetchone()[2]
    def ledger_factory():return P.H.Ledger(path, ceiling)
    published_at = 0
    halt = None
    invalid_streak = 0
    active = {'active_requests': 0, 'active_sources': 0, 'ready_queue': 0}
    last_report = 0
    def report(phase):
        nonlocal last_report
        result = {'phase': phase, 'proposal_model': G.MODEL, 'review_model': REVIEW_MODEL,
                  'method': 'two_qwen_model_agreement', 'priority_version': P.VERSION,
                  'candidate_scope': args.scope,
                  'ranked_candidates': len(rows), 'group_size': args.group_size,
                  'workers': workers, 'source_workers': args.source_workers, **active,
                  **stats, 'elapsed_seconds': round(time.monotonic() - started),
                  'new_cost_or_reservation_usd': round(ledger.spent() - initial_spend, 6),
                  'project_budget': ledger.project_snapshot()}
        atomic_json(STATUS, result)
        print(json.dumps(result), flush=True)
        last_report = time.monotonic()
    def source(row):
        if should_stop():return row, None
        a, b = row['a'], row['b']
        state = P.H.make_state(a, b, papers, cites, contexts)
        if not state.get('source_evidence'):
            packet = E.build_packet(a, b, state, papers, alternates)
            state = {**state, 'source_evidence': packet}
        return row, state
    pending = [{'a': a, 'b': b, 'state': json.loads(state), 'result': json.loads(result)}
               for a, b, state, result in ledger.db.execute("""SELECT a,b,state,result FROM calls AS proposal
                 WHERE status='seed_proposed' AND NOT EXISTS (SELECT 1 FROM calls AS verdict
                 WHERE verdict.a=proposal.a AND verdict.b=proposal.b AND verdict.model=?
                 AND verdict.status IN ('complete','reserved','unknown','invalid'))""", (REVIEW_MODEL,))]
    report('starting')
    try:
        for event in events(rows, pending, source, process_review, ledger_factory,
                            workers=workers, source_workers=args.source_workers,
                            group_size=args.group_size, should_stop=should_stop,
                            admission_stop=admission_stop):
            if event['kind'] == 'source':
                stats['source_checked'] += 1
                stats['source_ready' if event['ready'] else 'needs_context'] += 1
            elif event['kind'] == 'source_error':
                stats['source_checked'] += 1
                stats['source_errors'] += 1
            elif event['kind'] == 'model':
                for name in stats:stats[name] += event.get(name, 0)
                if event.get('halt') and (halt is None or (halt == 'paused' and event['halt'] != 'paused')):
                    halt = event['halt']
                if event.get('invalid'):invalid_streak += 1
                elif event.get('reviewed') or event.get('verified'):invalid_streak = 0
                if invalid_streak >= 3:
                    halt = halt or 'repeated_invalid_outputs'
                    admission_stop.set()
                if args.command == 'pilot' and stats['reviewed'] >= 12:
                    halt = halt or 'pilot_complete'
                    admission_stop.set()
                if stats['reviewed'] + stats['verified'] - published_at >= args.publish_every:
                    publish()
                    published_at = stats['reviewed'] + stats['verified']
            else:
                active = {name: event[name] for name in active}
            if time.monotonic() - last_report >= 10:
                report('draining' if should_stop() or halt else 'running')
    except BaseException:
        report('failed')
        raise
    if stats['reviewed'] + stats['verified'] > published_at:publish()
    report('paused' if should_stop() else halt or ('expanded_queue_complete' if args.scope == 'expanded' else 'priority_queue_complete'))


if __name__ == '__main__':
    main()
