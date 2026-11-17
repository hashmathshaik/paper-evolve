"""Generate edges using only console-verified Model Studio free allowances.

One worker per text model, a shared resumable queue, no paid fallback. The older
QWEN_PAUSED marker continues to block the paid runner. Pause this worker with
work/edges/FREE_QUOTA_PAUSED or SIGTERM. No new Jev calls are made here.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
from urllib import request, error

import qwen_relations as Q

VERSION = 'modelstudio-free-edges-v1'
CONFIG = Q.C.J.E / 'free-quota-models.json'
PAUSE = Q.C.J.E / 'FREE_QUOTA_PAUSED'
MODELS = {
    'qwen3.8-27b', 'kimi-k3', 'kimi-k3.1-pro', 'qwen3.8-max-0902',
    'deepseek-v4.1-flash-1017', 'deepseek-v4.1-flash', 'glm-5.3',
}


def load_config(path=CONFIG, now=None):
    now = now or datetime.now(timezone.utc)
    config = json.loads(Path(path).read_text())
    checked = datetime.fromisoformat(config['verified_at'])
    age = (now - checked).total_seconds()
    if not 0 <= age <= 86400:
        raise ValueError('Refresh the console protection check before starting (24-hour validity).')
    if config.get('region') != 'ap-southeast-1':
        raise ValueError('Free quotas must use the verified Singapore region.')
    seen = set()
    for model in config['models']:
        name = model['model']
        if name not in MODELS or name in seen:
            raise ValueError('Unknown or duplicate model in free-only configuration.')
        seen.add(name)
        if model.get('stop_on_exhaust') is not True or not isinstance(model.get('remaining_tokens'), int) or model['remaining_tokens'] <= 0:
            raise ValueError('Every model must have verified remaining quota and stop-on-exhaust enabled.')
    return sorted((m for m in config['models'] if m['expires'] > now.date().isoformat()), key=lambda m: m['expires'])


def payload(state, model):
    # JSON mode plus an explicit schema works across the different model families;
    # do not send Qwen-only thinking parameters to Kimi/DeepSeek/GLM.
    params = Q.payload(state, model)
    if not state.get('source_evidence'):
        params['messages'][0]['content'] = params['messages'][0]['content'].replace(
            'If related=true, choose at least one a_abstract/a_passage option AND one b_citation option that support the relationship.',
            'If related=true, choose at least one a_abstract option AND one b_abstract option that support the relationship. Abstract-only evidence supports a prediction, not verified influence.')
    schema = params['response_format']['json_schema']['schema']
    params['messages'][0]['content'] += '\nReturn one JSON object matching this schema: ' + json.dumps(schema)
    if model == 'kimi-k3':
        params['messages'][1]['content'] = ('Classify exactly this ONE paper pair using the system rules. Return the classification JSON object '
            '(related, basis, relations, reason, inherited, changed, evidence_ids). Do not return the input data or the schema. '
            'Do not wrap the object in an array.\nResearch data follows:\n' + params['messages'][1]['content'])
    result = {'model': model, 'messages': params['messages'], 'max_completion_tokens': 4096,
              'reasoning_effort': 'low', 'response_format': {'type': 'json_object'}}
    if model in ('qwen3.8-27b', 'qwen3.8-max-0902'):
        del result['reasoning_effort']
        result['thinking_budget'] = 1024
    if model == 'qwen3.8-27b':
        # Open-source Qwen is not in the documented max_completion_tokens list.
        del result['max_completion_tokens']
        result['max_tokens'] = 1536
    return result


def decode(content, state):
    decision = json.loads(content)
    wrapped = isinstance(decision, list)
    if wrapped:
        if len(decision) != 1 or not isinstance(decision[0], dict):
            raise ValueError('Expected exactly one classification object')
        decision = decision[0]
    if not isinstance(decision, dict):
        raise ValueError('Expected a classification object')
    result = Q.decode(decision, state)
    if result['related'] and not state.get('source_evidence'):
        sources = {e['source'] for e in result['evidence']}
        if not {'a_abstract', 'b_abstract'} <= sources:
            raise ValueError('Abstract predictions must quote both papers')
    return {**result, 'singleton_array_unwrapped': wrapped}


def recover_saved(ledger, model):
    """Reparse exact saved answers without sending requests or altering evidence."""
    recovered = accepted = 0
    rows = ledger.db.execute("SELECT c.id,c.a,c.b,c.state,c.usage,c.cost,o.content FROM calls c JOIN free_invalid_output o ON c.id=o.id WHERE c.model=? AND c.status='invalid' AND c.error='Invalid output: AttributeError'", (model,)).fetchall()
    for identity, a, b, state_raw, usage_raw, cost, content_raw in rows:
        try:
            usage = json.loads(usage_raw)
            if not all(isinstance(usage.get(k), int) for k in ('prompt_tokens', 'completion_tokens')):
                continue
            result = decode(json.loads(content_raw), json.loads(state_raw))
            checked = Q.apply_policy(a, b, result, Q.load_policy())
            result = checked if checked is not None else {**result, 'related': False, 'types': {}, 'review_policy_withheld': True}
            result.update(provider='modelstudio', provider_model=model, free_quota_only=True, recovered_from_invalid_output=True)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        ledger.finish(identity, result, usage, cost)
        recovered += 1
        accepted += result['related']
    return {'recovered': recovered, 'accepted': accepted, 'new_requests': 0}


def setup(ledger):
    ledger.db.execute('''CREATE TABLE IF NOT EXISTS free_model_state(
        model TEXT PRIMARY KEY, phase TEXT NOT NULL, detail TEXT, updated_at TEXT NOT NULL)''')
    ledger.db.execute('CREATE TABLE IF NOT EXISTS free_invalid_output(id TEXT PRIMARY KEY,content TEXT)')
    ledger.db.commit()


def phase(ledger, model, value, detail=''):
    ledger.db.execute('INSERT OR REPLACE INTO free_model_state VALUES (?,?,?,?)',
                      (model, value, detail, datetime.now(timezone.utc).isoformat()))
    ledger.db.commit()


def reserve(ledger, identity, a, b, model, state, params):
    # A pair is claimed across all seven workers in the same transaction as the
    # durable request record. Completed earlier reviewers are reused, not resent.
    with ledger.lock:
        ledger.db.execute('BEGIN IMMEDIATE')
        try:
            existing = ledger.db.execute("SELECT 1 FROM calls WHERE a=? AND b=? AND status IN ('complete','reserved','unknown','invalid') LIMIT 1", (a, b)).fetchone()
            if existing or ledger.db.execute('SELECT 1 FROM calls WHERE id=?', (identity,)).fetchone():
                ledger.db.rollback()
                return False
            ledger.db.execute("INSERT INTO calls VALUES (?,?,?,?,?,NULL,0,'reserved',NULL,NULL)",
                              (identity, a, b, model, json.dumps(state)))
            ledger.db.execute('INSERT INTO request_specs VALUES (?,?,?)',
                              (identity, VERSION, hashlib.sha256(params['messages'][0]['content'].encode()).hexdigest()))
            ledger.db.commit()
            return True
        except BaseException:
            ledger.db.rollback()
            raise


def error_code(exc):
    # Never log a provider error body, which can echo prompt content or headers.
    try:
        raw = json.loads(exc.read(65536))
        return str(raw.get('error', {}).get('code') or raw.get('code') or '')
    except (ValueError, AttributeError, TypeError):
        return ''


def review(ledger, a, b, state, model, transport=None):
    if transport is None and PAUSE.exists():
        return 'paused'
    if transport is None and model not in {m['model'] for m in load_config()}:
        raise ValueError('Model has no current verified free-only allowance.')
    if not all(state.get(k, {}).get('abstract', '').strip() for k in ('paper_a', 'paper_b')):
        return 'missing_abstract'
    # Reuse ready passages; otherwise make an explicitly abstract-only prediction.
    # Failed retrieval is retained on disk and never represented as source support.
    if state.get('source_evidence', {}).get('status') != 'ready':
        state = {k: v for k, v in state.items() if k != 'source_evidence'}
    params = payload(state, model)
    body = json.dumps(params, ensure_ascii=False).encode()
    identity = 'free-' + hashlib.sha256(VERSION.encode() + body).hexdigest()
    if not reserve(ledger, identity, a, b, model, state, params):
        return 'cached'
    try:
        if transport:
            raw = transport(params)
        else:
            key, base = Q.connection()
            req = request.Request(base + '/chat/completions', data=body,
                                  headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
            with request.urlopen(req, timeout=240) as response:
                raw = json.load(response)
    except error.HTTPError as exc:
        code = error_code(exc)
        if exc.code == 403 and code == 'AllocationQuota.FreeTierOnly':
            outcome = 'quota_exhausted'
        elif exc.code == 429:
            outcome = 'rate_limited'
        elif exc.code in (400, 404):
            outcome = 'model_unavailable'
        else:
            outcome = 'provider_blocked'
        ledger.finish(identity, None, {}, 0, outcome, f'HTTP {exc.code}; {outcome}')
        return outcome
    except (error.URLError, TimeoutError, OSError, ValueError):
        ledger.finish(identity, None, {}, 0, 'unknown', 'Outcome unknown; do not automatically resend this pair.')
        return 'unknown'
    usage = raw.get('usage', {})
    inp, out = usage.get('prompt_tokens'), usage.get('completion_tokens')
    if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (inp, out)):
        ledger.finish(identity, None, usage, 0, 'invalid', 'Missing usage; halt this model.')
        return 'unknown'
    try:
        choice = raw['choices'][0]
        if choice['finish_reason'] != 'stop':
            raise ValueError('Truncated/refused result')
        decision = decode(choice['message']['content'], state)
        checked = Q.apply_policy(a, b, decision, Q.load_policy())
        if checked is None:
            decision = {**decision, 'related': False, 'types': {}, 'review_policy_withheld': True}
        else:
            decision = checked
        decision.update(provider_model=raw.get('model', model), provider='modelstudio', free_quota_only=True)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        detail = str(exc)[:160] if isinstance(exc, ValueError) else type(exc).__name__
        content = raw.get('choices', [{}])[0].get('message', {}).get('content')
        ledger.db.execute('INSERT OR REPLACE INTO free_invalid_output VALUES (?,?)', (identity, json.dumps(content)))
        ledger.db.commit()
        ledger.finish(identity, None, usage, 0, 'invalid', 'Invalid output: ' + detail)
        return 'invalid'
    ledger.finish(identity, decision, usage, 0)
    return 'accepted' if decision['related'] else 'abstained'


def snapshot(ledger, counts, state, models, queued):
    rows = ledger.db.execute("SELECT model,status,usage FROM calls WHERE id LIKE 'free-%'").fetchall()
    totals = {m['model']: {'tokens': 0, 'reviews': 0, 'accepted': 0} for m in models}
    for model, status, raw in rows:
        if model not in totals:
            continue
        u = json.loads(raw or '{}')
        totals[model]['tokens'] += sum(n for n in (u.get('prompt_tokens'), u.get('completion_tokens')) if isinstance(n, int) and n >= 0)
        totals[model]['reviews'] += status == 'complete'
    for model, count in ledger.db.execute("SELECT model,COUNT(*) FROM calls WHERE id LIKE 'free-%' AND status='complete' AND json_extract(result,'$.related')=1 GROUP BY model"):
        if model in totals:
            totals[model]['accepted'] = count
    phases = {m: {'phase': p, 'detail': d} for m, p, d in ledger.db.execute('SELECT model,phase,detail FROM free_model_state')}
    result = {'phase': state, 'models': {m: {**v, **phases.get(m, {})} for m, v in totals.items()},
              'outcomes_this_run': dict(counts), 'queued_pairs': queued, 'paid_fallback': False,
              'project_budget': ledger.project_snapshot(), 'updated_at': datetime.now(timezone.utc).isoformat()}
    Q.atomic_json(Q.C.J.E / 'free-quota-status.json', result)
    print(json.dumps(result), flush=True)


def publish():
    from edge_publication import publish as publish_locked
    publish_locked()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['plan', 'run'])
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--models', nargs='+', choices=sorted(MODELS))
    args = ap.parse_args()
    if args.limit < 0:
        ap.error('Limit must be nonnegative.')
    models = load_config()
    if args.models:
        models = [m for m in models if m['model'] in args.models]
        if {m['model'] for m in models} != set(args.models):
            raise SystemExit('Every selected model must have a current protected allowance.')
    lock = (Q.C.J.E / 'qwen-worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('An edge reviewer is already running.')
    ledger = Q.C.Ledger(Q.C.J.E / 'relations.sqlite3', 50)
    Q.S.setup(ledger)
    setup(ledger)
    if args.command == 'run':
        for model in models:
            recovered = recover_saved(ledger, model['model'])
            if recovered['recovered']:
                print(json.dumps({'model': model['model'], **recovered}), flush=True)
                publish()
    papers, pairs, cites, contexts = Q.C.candidates()
    selected, screens = Q.S.eligible(ledger, pairs)
    done = {(a, b) for a, b in ledger.db.execute("SELECT a,b FROM calls WHERE status IN ('complete','reserved','unknown','invalid')")}
    selected = [p for p in selected if p not in done]
    # Spend free reviews on new candidates without buying more Jev screening.
    # Keep known negative screens out, except the existing audit sample above.
    selected_set = set(selected)
    remaining = [p for p in pairs if p not in done and p not in selected_set and p not in screens]
    selected = sorted(selected, key=lambda p: Q.C.make_state(*p, papers, cites, contexts).get('source_evidence', {}).get('status') != 'ready') + remaining
    if args.limit:
        selected = selected[:args.limit]
    counts = {}
    if args.command == 'plan':
        snapshot(ledger, counts, 'prepared', models, len(selected))
        return
    if PAUSE.exists():
        raise SystemExit('Free-quota reviews are paused.')
    Q.connection()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    tasks = queue.Queue()
    for pair in selected:
        tasks.put(pair)
    count_lock = threading.Lock()
    def worker(model):
        name = model['model']
        local = Q.C.Ledger(Q.C.J.E / 'relations.sqlite3', 50)
        phase(local, name, 'running')
        try:
            invalid = 0
            while not stopped.is_set() and not PAUSE.exists():
                if datetime.now(timezone.utc).date().isoformat() >= model['expires']:
                    phase(local, name, 'expired')
                    return
                try:
                    a, b = tasks.get_nowait()
                except queue.Empty:
                    phase(local, name, 'queue_complete')
                    return
                outcome = review(local, a, b, Q.C.make_state(a, b, papers, cites, contexts), name)
                with count_lock:
                    counts[outcome] = counts.get(outcome, 0) + 1
                if outcome in ('quota_exhausted', 'rate_limited', 'model_unavailable', 'provider_blocked'):
                    tasks.put((a, b))  # A definitive unbilled rejection can use another model.
                    phase(local, name, outcome)
                    return
                if outcome in ('unknown', 'paused'):
                    phase(local, name, outcome)
                    return
                invalid = invalid + 1 if outcome == 'invalid' else 0
                if invalid >= (8 if name == 'kimi-k3' else 3):
                    phase(local, name, 'invalid_output_stop')
                    return
            phase(local, name, 'paused' if PAUSE.exists() else 'stopped')
        finally:
            local.db.close()
    snapshot(ledger, counts, 'starting', models, tasks.qsize())
    last_publish = last_report = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=len(models) or 1) as pool:
            pending = {pool.submit(worker, model) for model in models}
            while pending:
                finished, pending = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                for future in finished:
                    try:
                        future.result()
                    except BaseException:
                        stopped.set()
                        raise
                if time.monotonic() - last_report >= 15:
                    with count_lock:
                        snapshot(ledger, counts, 'draining' if stopped.is_set() or PAUSE.exists() else 'running', models, tasks.qsize())
                    last_report = time.monotonic()
                if time.monotonic() - last_publish >= 120:
                    publish()
                    last_publish = time.monotonic()
    finally:
        was_stopped = stopped.is_set()
        stopped.set()
        publish()
        state = 'paused' if PAUSE.exists() else ('stopped' if was_stopped else ('models_stopped' if tasks.qsize() else 'complete'))
        snapshot(ledger, counts, state, models, tasks.qsize())


if __name__ == '__main__':
    main()
