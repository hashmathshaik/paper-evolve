"""Opt-in, resumable contributor API inference with a private spending ledger.

Uses the same frozen tasks and validator as agents. No project keys, seed worker,
provider-specific rates, automatic retries, or automatic publication.
"""
import json
import math
import os
import sqlite3
from pathlib import Path
from urllib import request, error, parse
import community_edges as C
import contribution_workspace as W
from voyage_pipeline import atomic_json

VERSION = 'paper-evolve-contributor-api-v1'


def claim_workspace(handle):
    """Nonblocking process lock; closing the handle releases it on either OS."""
    try:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            handle.write('0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise ValueError('An API runner is already using this workspace.') from None


def endpoint(base):
    parsed = parse.urlsplit(base)
    local = parsed.hostname in {'localhost', '127.0.0.1', '::1'}
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and local))):
        raise ValueError('Use an HTTPS API base URL without credentials/query parameters (HTTP is allowed on loopback).')
    return base.rstrip('/'), local


def parameters(task, model, max_output):
    rules = (W.ROOT / 'community/REVIEW_PROMPT.md').read_text()
    schema = json.loads(json.dumps(C.H.SCHEMA))
    schema['properties']['evidence']['items']['properties']['source']['enum'] += [p['id'] for p in task['state'].get('source_evidence',{}).get('passages',[]) if p['id'] not in schema['properties']['evidence']['items']['properties']['source']['enum']]
    return {'model': model, 'max_tokens': max_output,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': rules + '\nReturn only ONE decision object matching this JSON schema:\n' + json.dumps(schema)},
                         {'role': 'user', 'content': json.dumps({'task_id': task['id'], 'sources': task['sources'],
                                                                'state': task['state']}, ensure_ascii=False)}]}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise error.HTTPError(req.full_url, code, 'API redirects are disabled.', headers, fp)


def send(base, key, body):
    req = request.Request(base + '/chat/completions', data=body,
                          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    with request.build_opener(NoRedirect()).open(req, timeout=180) as response:
        return json.load(response)


class Ledger:
    def __init__(self, path, config):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS config(value TEXT NOT NULL)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS attempts(
            task_id TEXT PRIMARY KEY, status TEXT NOT NULL, cost REAL NOT NULL,
            decision TEXT, input_tokens INTEGER, output_tokens INTEGER, diagnostic TEXT)''')
        encoded = json.dumps(config, sort_keys=True)
        saved = self.db.execute('SELECT value FROM config').fetchone()
        if saved and saved[0] != encoded:
            self.db.close()
            raise ValueError('This workspace already has a different API model, endpoint, rates, prompt or source evidence. Use a new workspace.')
        if not saved:self.db.execute('INSERT INTO config VALUES (?)', (encoded,))
        self.db.commit()

    def spent(self):
        return self.db.execute('SELECT COALESCE(sum(cost),0) FROM attempts').fetchone()[0]

    def reserve(self, task_id, bound, cap):
        self.db.execute('BEGIN IMMEDIATE')
        if self.db.execute('SELECT 1 FROM attempts WHERE task_id=?', (task_id,)).fetchone():
            self.db.rollback()
            return 'already_attempted'
        if self.spent() + bound > cap:
            self.db.rollback()
            return 'budget_limited'
        self.db.execute("INSERT INTO attempts(task_id,status,cost) VALUES (?,'reserved',?)", (task_id, bound))
        self.db.commit()
        return 'reserved'

    def finish(self, task_id, status, cost, decision=None, usage=(None, None), diagnostic=None):
        self.db.execute('UPDATE attempts SET status=?,cost=?,decision=?,input_tokens=?,output_tokens=?,diagnostic=? WHERE task_id=?',
                        (status, cost, json.dumps(decision) if decision is not None else None, *usage, diagnostic, task_id))
        self.db.commit()

    def restore(self, envelope, tasks, materials=None):
        decisions = {row['task_id']: row for row in envelope['submission']['decisions']}
        # Recover a completed decision if an interruption occurred between the
        # transaction and the atomic submission write. Uncertain calls stay held.
        for task_id, raw in self.db.execute("SELECT task_id,decision FROM attempts WHERE status IN ('complete','source_missing')"):
            if task_id not in tasks:raise ValueError('Ledger task differs from workspace.')
            decisions[task_id] = {'task_id': task_id, 'task_sha256': tasks[task_id]['sha256'], 'decision': json.loads(raw)}
            if materials and task_id in materials:decisions[task_id]['source_material'] = materials[task_id]
        envelope['submission']['decisions'] = list(decisions.values())


def run(destination, base, model, key_env, input_rate, output_rate, budget, max_output=2048, limit=10, transport=None):
    base, local = endpoint(base)
    if (not model.strip() or any(not math.isfinite(v) or v < 0 for v in (input_rate, output_rate))
            or (not local and input_rate + output_rate <= 0)
            or not math.isfinite(budget) or budget <= 0 or not 128 <= max_output <= 16384 or not 1 <= limit <= 1000):
        raise ValueError('Provide a model, current per-million token prices, a positive cumulative budget, 128–16384 output tokens and 1–1000 tasks.')
    key = os.environ.get(key_env, '')
    if transport is None and not key:
        raise ValueError('Set the selected API key environment variable. No key is read from project .env files.')
    destination = Path(destination)
    with (destination / 'api.lock').open('a+') as lock:
        claim_workspace(lock)
        workspace, pack, envelope = W.load(destination)
        if envelope['submission']['contributor']['method'] != 'api':
            raise ValueError('Start a separate workspace with --method api.')
        tasks = C.task_index(pack)
        materials = {r['task_id']:r['source_material'] for r in envelope['submission']['decisions'] if 'source_material' in r}
        database = destination / 'api.sqlite3'
        if database.exists():
            with sqlite3.connect(database) as recovery:
                saved = recovery.execute('SELECT value FROM config').fetchone()
            current_ids = {r['task_id'] for r in envelope['submission']['decisions']}
            for identity,material in (json.loads(saved[0]).get('source_materials',{}) if saved else {}).items():
                if identity not in current_ids:materials.setdefault(identity,material)
        if materials:
            from contribution_sources import augment
            tasks = {identity:({**task,'state':augment(task,materials[identity])} if identity in materials else task) for identity,task in tasks.items()}
        config = {'version': VERSION, 'base_url': base, 'model': model, 'input_rate': input_rate,
                  'output_rate': output_rate, 'max_output': max_output, 'pack_sha256': C.digest(pack),
                  'prompt_sha256': C.digest((W.ROOT / 'community/REVIEW_PROMPT.md').read_text()),
                  'schema_sha256': C.digest(C.H.SCHEMA)}
        if materials:config['source_materials'] = materials
        ledger = Ledger(destination / 'api.sqlite3', config)
        try:
            ledger.restore(envelope, tasks, materials)
            envelope['submission']['contributor']['tool'] = 'API / ' + model
            rows = {r['task_id']: r for r in envelope['submission']['decisions']}
            stats = {'phase': 'complete', 'requests': 0, 'valid_decisions': 0, 'invalid': 0, 'source_missing': 0}

            def decision_row(task_id,decision):
                row = {'task_id':task_id,'task_sha256':tasks[task_id]['sha256'],'decision':decision}
                if task_id in materials:row['source_material']=materials[task_id]
                return row

            def save():
                # Blank template rows never masquerade as completed abstentions.
                envelope['submission']['decisions'] = list(rows.values())
                atomic_json(destination / 'submission.json', envelope)
                attempted = dict(ledger.db.execute('SELECT status,count(*) FROM attempts GROUP BY status'))
                status = {**stats, 'attempts': attempted, 'spent_or_reserved_usd': round(ledger.spent(), 8), 'budget_usd': budget,
                          'price_source': 'contributor-supplied per-million token rates', 'published': False}
                atomic_json(destination / 'api-status.json', status)
                return status

            for task_id in workspace['selected_task_ids']:
                if stats['requests'] >= limit:
                    stats['phase'] = 'task_limit'
                    break
                existing = rows.get(task_id)
                if existing and existing['decision'].get('reason', '').strip():
                    C.validate_decision(existing['decision'], tasks[task_id]['state'])
                    continue
                task = tasks[task_id]
                params = parameters(task, model, max_output)
                body = json.dumps(params, ensure_ascii=False).encode()
                # UTF-8 bytes plus framing headroom conservatively bound input
                # tokens; the provider's requested output limit bounds generation.
                input_bound = len(body) + 512
                bound = (input_bound * input_rate + max_output * output_rate) / 1e6
                packet = task['state'].get('source_evidence', {})
                if packet.get('status') != 'ready':bound = 0
                reserved = ledger.reserve(task_id, bound, budget)
                if reserved == 'budget_limited':
                    stats['phase'] = reserved
                    break
                if reserved == 'already_attempted':
                    rows.pop(task_id, None)
                    continue
                if packet.get('status') != 'ready':
                    decision = {**W.blank_decision(), 'reason': 'Not sent to the model: prepared source passages are incomplete. A maintainer should refresh the evidence task.'}
                    ledger.finish(task_id, 'source_missing', 0, decision)
                    rows[task_id] = decision_row(task_id,decision)
                    stats['source_missing'] += 1
                    save()
                    continue
                stats['requests'] += 1
                try:
                    raw = transport(params) if transport else send(base, key, body)
                except error.HTTPError as exc:
                    uncertain = exc.code in {408, 500, 502, 503, 504}
                    ledger.finish(task_id, 'unknown' if uncertain else 'rejected', bound if uncertain else 0,
                                  diagnostic='http_' + str(exc.code))
                    rows.pop(task_id, None)
                    stats['phase'] = 'provider_http_' + str(exc.code)
                    break
                except BaseException as exc:
                    ledger.finish(task_id, 'unknown', bound, diagnostic=type(exc).__name__)
                    rows.pop(task_id, None)
                    stats['phase'] = 'uncertain_request'
                    save()
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):raise
                    break
                usage = raw.get('usage') or {} if isinstance(raw, dict) else {}
                if not isinstance(usage, dict):usage = {}
                inp, out = usage.get('prompt_tokens'), usage.get('completion_tokens')
                if not all(type(n) is int and n >= 0 for n in (inp, out)):
                    ledger.finish(task_id, 'unknown', bound, diagnostic='missing_usage')
                    rows.pop(task_id, None)
                    stats['phase'] = 'uncertain_usage'
                    break
                cost = (inp * input_rate + out * output_rate) / 1e6
                try:
                    choice = raw['choices'][0]
                    if choice['finish_reason'] != 'stop':raise ValueError('Output was incomplete.')
                    decision = json.loads(choice['message']['content'])
                    C.validate_decision(decision, task['state'])
                except (KeyError, IndexError, ValueError, TypeError, AttributeError):
                    ledger.finish(task_id, 'invalid', cost, usage=(inp, out), diagnostic='invalid_decision')
                    rows.pop(task_id, None)
                    stats['invalid'] += 1
                else:
                    ledger.finish(task_id, 'complete', cost, decision, (inp, out))
                    rows[task_id] = decision_row(task_id,decision)
                    stats['valid_decisions'] += 1
                if inp > input_bound or out > max_output:
                    stats['phase'] = 'provider_token_bound_exceeded'
                    save()
                    break
                save()
            # Remove unprocessed template rows from the portable submission.
            rows = {k: v for k, v in rows.items() if v['decision'].get('reason', '').strip()}
            unresolved = ledger.db.execute("SELECT count(*) FROM attempts WHERE status IN ('unknown','reserved','invalid','rejected')").fetchone()[0]
            if stats['phase'] == 'complete' and unresolved:stats['phase'] = 'complete_with_unresolved'
            return save()
        finally:
            ledger.db.close()
