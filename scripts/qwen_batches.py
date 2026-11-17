"""Resumable Qwen3.7-Flash Batch reviews within the existing $50 project cap.

No real-time fallback and no new Jev screening. Stop admitting jobs with
work/edges/QWEN_BATCH_PAUSED; submitted jobs remain accounted for and collected.
An ambiguous submission retains its full reservation and is never resubmitted.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid
from urllib import request, error, parse

import qwen_relations as Q

MODEL = 'qwen3.7-flash'
SUPPORTED_VARIANTS = ('qwen3.7-flash', 'qwen3.7-flash-2026-07-15')
VERSION = 'qwen-batch-relations-v1'
MAX_OUTPUT = 3072
WORK = Q.C.J.E / 'qwen-batches'
PAUSE = Q.C.J.E / 'QWEN_BATCH_PAUSED'
TERMINAL = {'completed', 'failed', 'expired', 'cancelled'}
SINGAPORE = 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
BEIJING = 'https://dashscope.aliyuncs.com/compatible-mode/v1'


def base_url():
    base = Q.local('QWEN_BATCH_BASE_URL', SINGAPORE).rstrip('/')
    if base not in (SINGAPORE, BEIJING):
        raise ValueError('Use an official Singapore or Beijing Batch endpoint.')
    return base


def connection():
    base = base_url()
    key = Q.local('QWEN_BATCH_API_KEY')
    if not key and base == SINGAPORE:
        key, _ = Q.connection()
    if not key:
        raise RuntimeError('Configure QWEN_BATCH_API_KEY with a Beijing-region key locally; the Singapore key is not reused across regions.')
    return key, base


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def api(path, body=None, upload=None, content=False):
    if not re.fullmatch(r'/(?:files|batches)(?:/[A-Za-z0-9_-]+(?:/content)?)?', path):
        raise ValueError('Unexpected Batch API path')
    key, base = connection()
    headers = {'Authorization': 'Bearer ' + key}
    data = None
    if upload is not None:
        boundary = 'PaperEvolve' + uuid.uuid4().hex
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nbatch\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="requests.jsonl"\r\nContent-Type: application/jsonl\r\n\r\n').encode()
        data += Path(upload).read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
    elif body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = request.Request(base + path, data=data, headers=headers)
    with request.build_opener(NoRedirect).open(req, timeout=180) as response:
        return response.read() if content else json.load(response)


def state_for(state):
    if state.get('source_evidence', {}).get('status') != 'ready':
        return {k: v for k, v in state.items() if k != 'source_evidence'}
    return state


def payload(state):
    result = Q.payload(state, MODEL)
    if not state.get('source_evidence'):
        result['messages'][0]['content'] = result['messages'][0]['content'].replace(
            'If related=true, choose at least one a_abstract/a_passage option AND one b_citation option that support the relationship.',
            'If related=true, choose at least one a_abstract option AND one b_abstract option that support the relationship. This is an abstract-based prediction.')
    result['max_completion_tokens'] = MAX_OUTPUT
    return result


def bound_for(params):
    upper = len(json.dumps(params, ensure_ascii=False).encode()) + 8192
    pin, pout = price(params['model'], upper)
    return (upper * pin + (MAX_OUTPUT + 16) * pout) / 2e6


def price(model, tokens, endpoint=None):
    if model not in SUPPORTED_VARIANTS:
        raise ValueError('Unapproved Batch model')
    if (endpoint or base_url()) == BEIJING:
        return (.028, .110) if tokens <= 32000 else ((.083, .330) if tokens <= 256000 else (.165, .660))
    return Q.price('qwen3.7-flash', tokens)


def setup(ledger):
    ledger.db.execute('''CREATE TABLE IF NOT EXISTS qwen_batches(
        id TEXT PRIMARY KEY, input_file TEXT, provider_id TEXT, requests TEXT NOT NULL,
        phase TEXT NOT NULL, summary TEXT)''')
    ledger.db.commit()


def require_available(ledger, model):
    blocked = ledger.db.execute("SELECT 1 FROM calls WHERE model=? AND status='batch_rejected' AND error LIKE '%not supported by the Batch API%' AND COALESCE(json_extract(state,'$._batch_base_url'),?)=? LIMIT 1", (model, SINGAPORE, base_url())).fetchone()
    if blocked:
        raise RuntimeError('This model was rejected as unsupported by this regional Batch API. Configure the supported Beijing route and its own key.')


def set_job(ledger, local, phase, **values):
    allowed = {'input_file', 'provider_id', 'summary'}
    if set(values) - allowed:
        raise ValueError('Unknown job field')
    fields = ['phase=?'] + [k + '=?' for k in values]
    ledger.db.execute('UPDATE qwen_batches SET ' + ','.join(fields) + ' WHERE id=?', [phase, *values.values(), local])
    ledger.db.commit()


def prepare(ledger, pairs, papers, cites, contexts, size):
    rows = []
    total_bytes = 0
    known = {(a, b) for a, b in ledger.db.execute("SELECT a,b FROM calls WHERE status IN ('complete','reserved','unknown','invalid')")}
    for a, b in pairs:
        if PAUSE.exists():
            break
        if (a, b) in known:
            continue
        state = state_for(Q.C.make_state(a, b, papers, cites, contexts))
        params = payload(state)
        identity = 'qb-' + hashlib.sha256(VERSION.encode() + base_url().encode() + json.dumps(params, sort_keys=True).encode()).hexdigest()
        row = {'custom_id': identity, 'method': 'POST', 'url': '/v1/chat/completions', 'body': params}
        line = json.dumps(row, ensure_ascii=False).encode()
        if len(line) > 1000000:
            continue
        if total_bytes + len(line) > 80000000:
            break
        bound = bound_for(params)
        state = {**state, '_batch_base_url': base_url()}
        if not ledger.reserve(identity, a, b, MODEL, state, bound, unique_pair=True):
            if ledger.project_snapshot()['remaining_request_allowance_usd'] < bound:
                break
            continue
        ledger.db.execute('INSERT OR REPLACE INTO request_specs VALUES (?,?,?)',
                          (identity, VERSION, hashlib.sha256(params['messages'][0]['content'].encode()).hexdigest()))
        ledger.db.commit()
        rows.append(row)
        known.add((a, b))
        total_bytes += len(line)
        if len(rows) >= size:
            break
    if not rows:
        return None
    # Keep each explicitly restarted, definitively rejected attempt separate.
    # Ambiguous submissions remain reserved and cannot reach this path.
    local = hashlib.sha256(json.dumps([r['custom_id'] for r in rows]).encode() + uuid.uuid4().bytes).hexdigest()
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / (local + '.jsonl')
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    ledger.db.execute("INSERT INTO qwen_batches VALUES (?,NULL,NULL,?,'prepared',NULL)",
                      (local, json.dumps([r['custom_id'] for r in rows])))
    ledger.db.commit()
    return local


def reject(ledger, local, ids, detail, diagnostic=None):
    for identity in ids:
        ledger.finish(identity, None, {}, 0, 'batch_rejected', detail)
    set_job(ledger, local, 'rejected', summary=json.dumps({'error': detail, 'diagnostic': diagnostic}))


def submit(ledger, local, transport=api):
    input_file, provider, ids_raw, phase = ledger.db.execute(
        'SELECT input_file,provider_id,requests,phase FROM qwen_batches WHERE id=?', (local,)).fetchone()
    ids = json.loads(ids_raw)
    if provider:
        return provider
    if phase not in ('prepared', 'uploaded'):
        raise RuntimeError('Ambiguous earlier upload/submission; reservations retained. Reconcile the job before continuing.')
    endpoints = {json.loads(raw).get('_batch_base_url', SINGAPORE) for (raw,) in ledger.db.execute(
        'SELECT state FROM calls WHERE id IN (' + ','.join('?' for _ in ids) + ')', ids)}
    if endpoints != {base_url()}:
        raise RuntimeError('This batch was prepared for a different region; do not submit it using the current endpoint.')
    stage = 'upload' if not input_file else 'create_batch'
    try:
        if not input_file:
            set_job(ledger, local, 'uploading')
            uploaded = transport('/files', upload=WORK / (local + '.jsonl'))
            input_file = uploaded['id']
            set_job(ledger, local, 'uploaded', input_file=input_file)
        stage = 'create_batch'
        set_job(ledger, local, 'submitting')
        job = transport('/batches', body={'input_file_id': input_file, 'endpoint': '/v1/chat/completions',
                                        'completion_window': '24h',
                                        'metadata': {'ds_name': 'Paper Evolve ' + local[:16], 'paper_evolve_job': local}})
    except error.HTTPError as exc:
        # Explicit HTTP rejection does not create inference work. No auto retry.
        if exc.code in (400, 401, 402, 403, 404, 413, 422, 429):
            diagnostic = {'http_status': exc.code, 'stage': stage, 'endpoint': base_url()}
            try:
                raw = json.load(exc)
                provider_error = raw.get('error') or raw
                detail = str(provider_error.get('message', ''))[:300]
                diagnostic['provider_code'] = provider_error.get('code')
                diagnostic['request_id'] = raw.get('request_id') or raw.get('requestId') or exc.headers.get('x-request-id') or exc.headers.get('x-dashscope-request-id')
            except (ValueError, AttributeError):
                detail = ''
            message = f'Batch HTTP {exc.code}: {detail}'
            reject(ledger, local, ids, message, diagnostic)
            raise RuntimeError(message) from None
        raise RuntimeError('Batch submission outcome uncertain; reservations retained.') from None
    except (error.URLError, TimeoutError, OSError, ValueError, KeyError):
        raise RuntimeError('Batch submission outcome uncertain; do not resubmit automatically.') from None
    set_job(ledger, local, job['status'], provider_id=job['id'], summary=json.dumps(job))
    return job['id']


def ingest(ledger, row, expected):
    identity = row.get('custom_id')
    if identity not in expected:
        raise ValueError('Unknown result ID')
    model, state_raw, reserved, status = ledger.db.execute('SELECT model,state,cost,status FROM calls WHERE id=?', (identity,)).fetchone()
    state = json.loads(state_raw)
    if status != 'reserved':
        return False
    response = row.get('response') or {}
    raw = response.get('body') or {}
    usage = raw.get('usage') or {}
    inp, out = usage.get('prompt_tokens'), usage.get('completion_tokens')
    valid_usage = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (inp, out))
    if response.get('status_code') != 200:
        # Failed rows are not assumed free unless the provider confirms no usage.
        cost = reserved
        if valid_usage:
            pin, pout = price(model, inp, state.get('_batch_base_url', SINGAPORE))
            cost = (inp * pin + out * pout) / 2e6
        ledger.finish(identity, None, usage, cost, 'batch_errored', 'Provider error row; conservative allowance retained when usage is absent.')
        return False
    if not valid_usage:
        ledger.finish(identity, None, usage, reserved, 'invalid', 'Missing usage; reservation retained.')
        return False
    pin, pout = price(model, inp, state.get('_batch_base_url', SINGAPORE))
    cost = (inp * pin + out * pout) / 2e6
    try:
        choice = raw['choices'][0]
        if choice['finish_reason'] != 'stop':
            raise ValueError('Incomplete output')
        decision = Q.decode(json.loads(choice['message']['content']), state)
        if decision['related'] and not state.get('source_evidence') and not {'a_abstract', 'b_abstract'} <= {e['source'] for e in decision['evidence']}:
            raise ValueError('Abstract prediction must quote both papers')
        checked = Q.apply_policy(*ledger.db.execute('SELECT a,b FROM calls WHERE id=?', (identity,)).fetchone(), decision, Q.load_policy())
        decision = checked if checked is not None else {**decision, 'related': False, 'types': {}, 'review_policy_withheld': True}
        decision.update(provider='modelstudio', provider_model=raw.get('model', model), inference_method='batch')
    except (ValueError, TypeError, AttributeError, KeyError, IndexError):
        ledger.finish(identity, None, usage, cost, 'invalid', 'Invalid output; not published.')
        return False
    ledger.finish(identity, decision, usage, cost)
    return True


def collect(ledger, transport=api):
    completed = 0
    jobs = ledger.db.execute("SELECT id,provider_id,requests FROM qwen_batches WHERE provider_id IS NOT NULL AND phase NOT IN ('collected','rejected')").fetchall()
    for local, provider, ids_raw in jobs:
        first = json.loads(ids_raw)[0]
        saved = json.loads(ledger.db.execute('SELECT state FROM calls WHERE id=?', (first,)).fetchone()[0])
        if saved.get('_batch_base_url', SINGAPORE) != base_url():
            raise RuntimeError('An active batch belongs to a different region; collect it with its original endpoint and key.')
        job = transport('/batches/' + provider)
        set_job(ledger, local, job['status'], summary=json.dumps(job))
        if job['status'] not in TERMINAL:
            continue
        expected = set(json.loads(ids_raw))
        seen = set()
        for field in ('output_file_id', 'error_file_id'):
            if not job.get(field):
                continue
            data = transport('/files/' + job[field] + '/content', content=True)
            (WORK / (local + '-' + field + '.jsonl')).write_bytes(data)
            for line in data.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                identity = row.get('custom_id')
                if identity in seen:
                    raise ValueError('Duplicate batch result ID')
                seen.add(identity)
                completed += ingest(ledger, row, expected)
        if job['status'] == 'failed' and not seen and job.get('errors'):
            reject(ledger, local, expected, 'Provider rejected batch validation: ' + json.dumps(job['errors'])[:500])
            raise RuntimeError('Qwen rejected Batch validation; no more jobs will be submitted. See the saved job summary.')
        if seen != expected:
            raise RuntimeError('Missing batch result rows; reservations retained. No new batches admitted.')
        set_job(ledger, local, 'collected', summary=json.dumps(job))
    return completed


def snapshot(ledger, phase, total):
    jobs = [{'local_id': a, 'provider_id': b, 'phase': c, 'summary': json.loads(d or '{}')}
            for a, b, c, d in ledger.db.execute('SELECT id,provider_id,phase,summary FROM qwen_batches')]
    counts = dict(ledger.db.execute("SELECT status,count(*) FROM calls WHERE id LIKE 'qb-%' GROUP BY status"))
    report = {'phase': phase, 'model': MODEL, 'inference_method': 'batch', 'candidate_pairs_in_queue_at_start': total,
              'endpoint': base_url(),
              'request_states': counts, 'batches': jobs, 'project_budget': ledger.project_snapshot(),
              'updated_at': time.time(), 'realtime_fallback': False}
    Q.atomic_json(Q.C.J.E / 'qwen-batch-status.json', report)
    print(json.dumps(report), flush=True)


def publish():
    from edge_publication import publish as publish_locked
    publish_locked()


def main():
    global MODEL
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['plan', 'run', 'collect'])
    ap.add_argument('--batch-size', type=int, default=5000)
    ap.add_argument('--max-active', type=int, default=3)
    ap.add_argument('--watch', action='store_true')
    ap.add_argument('--model', choices=SUPPORTED_VARIANTS, default=MODEL)
    args = ap.parse_args()
    MODEL = args.model
    if not 1 <= args.batch_size <= 5000 or not 1 <= args.max_active <= 3:
        ap.error('Batch size must be 1–5000 and active jobs 1–3.')
    WORK.mkdir(parents=True, exist_ok=True)
    lock = (Q.C.J.E / 'qwen-batch-worker.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another Qwen edge worker is running.')
    ledger = Q.C.Ledger(Q.C.J.E / 'relations.sqlite3', 50)
    setup(ledger)
    budget = ledger.project_snapshot()
    if not budget or budget['maximum_usd'] > 50:
        raise SystemExit('A project budget of at most $50 must be configured first.')
    papers, pairs, cites, contexts = Q.C.candidates()
    selected, screens = Q.S.eligible(ledger, pairs)
    selected_set = set(selected)
    selected += [p for p in pairs if p not in screens and p not in selected_set]
    done = {(a, b) for a, b in ledger.db.execute("SELECT a,b FROM calls WHERE status IN ('complete','reserved','unknown','invalid')")}
    selected = [p for p in selected if p not in done]
    if args.command == 'plan':
        snapshot(ledger, 'prepared', len(selected))
        return
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        if args.command == 'run':
            require_available(ledger, MODEL)
            connection()
        while True:
            n = collect(ledger)
            if n:
                publish()
            successful = ledger.db.execute("SELECT count(*) FROM calls WHERE id LIKE 'qb-%' AND status='complete'").fetchone()[0]
            invalid = ledger.db.execute("SELECT count(*) FROM calls WHERE id LIKE 'qb-%' AND status IN ('invalid','batch_errored')").fetchone()[0]
            if invalid and not successful:
                raise RuntimeError('The first batch returned no usable structured results; stop before submitting larger batches.')
            ambiguous = ledger.db.execute("SELECT id FROM qwen_batches WHERE provider_id IS NULL AND phase IN ('uploading','submitting')").fetchone()
            if ambiguous:
                raise RuntimeError('An earlier submission is ambiguous; reconcile it before submitting more.')
            active = ledger.db.execute("SELECT count(*) FROM qwen_batches WHERE provider_id IS NOT NULL AND phase NOT IN ('collected','rejected')").fetchone()[0]
            ready = ledger.db.execute("SELECT id FROM qwen_batches WHERE phase IN ('prepared','uploaded')").fetchall()
            paused = stopped or PAUSE.exists()
            if args.command == 'run' and not paused:
                for (local,) in ready:
                    submit(ledger, local)
                    active += 1
                confirmed = successful > 0
                allowed = args.max_active if confirmed else 1
                while active < allowed:
                    local = prepare(ledger, selected, papers, cites, contexts, args.batch_size if confirmed else min(16, args.batch_size))
                    if not local:
                        break
                    if stopped or PAUSE.exists():
                        break
                    submit(ledger, local)
                    active += 1
            phase = 'paused_collecting' if paused and active else ('paused' if paused else ('batch_processing' if active else 'budget_limited_or_queue_complete'))
            snapshot(ledger, phase, len(selected))
            if not args.watch or (not active and (paused or not ready)):
                break
            for _ in range(30):
                if stopped:
                    break
                time.sleep(1)
            if stopped:
                snapshot(ledger, 'stopped_with_jobs_accounted_for', len(selected))
                break
    except BaseException:
        snapshot(ledger, 'failed_no_fallback', len(selected))
        raise


if __name__ == '__main__':
    main()
