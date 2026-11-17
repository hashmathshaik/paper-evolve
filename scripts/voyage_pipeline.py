"""Offline preparation for Paper Evolve. Only the `embed` command contacts Voyage.
No third-party dependencies for API jobs or small exact neighbor searches.
API reference: https://docs.voyageai.com/reference/embeddings-api
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import struct
import sys
import time
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
API_URL = 'https://api.voyageai.com/v1/embeddings'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def load_config(path):
    config = json.loads(Path(path).read_text())
    if config['model'] != 'voyage-4-large':
        raise ValueError('This cost/context configuration is reviewed for voyage-4-large only.')
    if config['output_dimension'] not in [256, 512, 1024, 2048]:
        raise ValueError('Unsupported output dimension.')
    if config.get('input_type') is not None:
        raise ValueError('Paper-to-paper similarity uses symmetric inputs (input_type: null).')
    if not 0 < config['budget_usd'] <= 20:
        raise ValueError('Budget must be above zero and at most the authorized $20 cap.')
    if not 1 <= config['batch_size'] <= 1000 or not 1 <= config['max_attempts'] <= 10:
        raise ValueError('Invalid batch size or attempt count.')
    if config['requests_per_minute'] <= 0 or config['price_per_million_tokens'] <= 0:
        raise ValueError('Rate and price must be positive.')
    if not 0 < config['max_batch_token_bound'] <= 120000 or not 0 < config['max_document_token_bound'] <= 32000:
        raise ValueError('Configured token bounds exceed reviewed model limits.')
    return config


def model_identity(config):
    return {k: config[k] for k in ['model', 'output_dimension', 'input_type']}


def read_records(source, input_path=None, allow_title_only=False, limit=None):
    if input_path:
        path = Path(input_path)
        raw = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.suffix == '.jsonl' else json.loads(path.read_text())
        rows = raw['papers'] if isinstance(raw, dict) else raw
        contributions = raw.get('contributions', []) if isinstance(raw, dict) else []
    elif source == 'corpus':
        rows = json.loads((ROOT / 'evolve/corpus.json').read_text())
        contributions = []
    else:
        raw = json.loads((ROOT / 'evolve/research.json').read_text())
        rows, contributions = raw['papers'], raw['contributions']
    records, seen = [], set()
    for row in rows:
        title = row.get('title', row.get('t', '')).strip()
        url = row.get('source_url', row.get('u', '')).strip()
        identity = row.get('paper_id', row.get('id')) or 'paper-' + digest(url or title)[:24]
        if identity in seen:
            raise ValueError(f'Duplicate paper identity: {identity}')
        seen.add(identity)
        abstract = (row.get('abstract') or '').strip()
        summaries = [c['label'] for c in contributions if c['paper_id'] == identity]
        if not title:
            raise ValueError(f'Missing title for {identity}')
        text = title
        quality = 'title_only'
        if abstract:
            text += '\n\nAbstract:\n' + abstract
            quality = 'title_abstract'
        if summaries:
            text += '\n\nCurated contributions:\n' + '\n'.join(summaries)
            if not abstract:
                quality = 'title_curated_summary'
        records.append({'id': identity, 'title': title, 'source_url': url, 'year': row.get('year', row.get('y')),
                        'text': text, 'text_hash': digest(text), 'quality': quality})
        if limit and len(records) >= limit:
            break
    if not records:
        raise ValueError('No paper records found.')
    return records


def token_bound(text):
    # Conservative UTF-8 byte allowance plus special-token headroom. Not an exact tokenizer count.
    return len(text.encode('utf-8')) + 32


def cache_key(record, config):
    return digest({'paper_id': record['id'], 'text_hash': record['text_hash'], **model_identity(config)})


class Cache:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, paper_id TEXT, text_hash TEXT, dimension INTEGER, vector BLOB, metadata TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, reserved_usd REAL NOT NULL, actual_tokens INTEGER, status TEXT NOT NULL)')
        self.db.commit()

    def get(self, record, config):
        row = self.db.execute('SELECT dimension, vector FROM vectors WHERE key=?', (cache_key(record, config),)).fetchone()
        return list(struct.unpack('<' + str(row[0]) + 'f', row[1])) if row else None

    def spent_bound(self):
        # Includes failed/uncertain attempts: a retry can itself be billable.
        return self.db.execute('SELECT COALESCE(SUM(reserved_usd),0) FROM attempts').fetchone()[0]

    def reserve(self, amount, cap):
        self.db.execute('BEGIN IMMEDIATE')
        if self.spent_bound() + amount > cap:
            self.db.rollback()
            raise ValueError('Local spending allowance exhausted; no request sent.')
        cursor = self.db.execute('INSERT INTO attempts(reserved_usd,status) VALUES (?,?)', (amount, 'reserved'))
        self.db.commit()
        return cursor.lastrowid

    def finish(self, attempt_id, status, actual_tokens=None):
        self.db.execute('UPDATE attempts SET status=?,actual_tokens=? WHERE id=?', (status, actual_tokens, attempt_id))
        self.db.commit()

    def save(self, records, vectors, config):
        for record, vector in zip(records, vectors):
            self.db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?,?)',
                            (cache_key(record, config), record['id'], record['text_hash'], len(vector),
                             struct.pack('<' + str(len(vector)) + 'f', *vector), json.dumps(model_identity(config))))
        self.db.commit()


def plan(records, config, cache=None):
    quality = {}
    for r in records:
        quality[r['quality']] = quality.get(r['quality'], 0) + 1
    pending = [r for r in records if cache is None or cache.get(r, config) is None]
    bound = sum(token_bound(r['text']) for r in pending)
    estimated = sum(max(1, math.ceil(len(r['text']) / 5)) for r in pending)
    return {'model': config['model'], 'dimensions': config['output_dimension'], 'records': len(records), 'quality': quality,
            'cached': len(records) - len(pending), 'pending': len(pending),
            'approximate_tokens': estimated, 'approximate_cost_usd': round(estimated / 1e6 * config['price_per_million_tokens'], 6),
            'conservative_token_allowance': bound, 'conservative_cost_usd': round(bound / 1e6 * config['price_per_million_tokens'], 6),
            'reserved_cost_so_far_usd': round(cache.spent_bound(), 6) if cache else 0,
            'budget_usd': config['budget_usd'], 'free_allowance_assumed': False,
            'notes': ['Estimates are not exact tokenizer counts. Conservative allowances use UTF-8 byte length plus headroom.',
                      'Embeddings create similarity candidates, never verified evolution edges.']}


def batches(records, config):
    batch, count = [], 0
    for record in records:
        bound = token_bound(record['text'])
        if bound > config['max_document_token_bound']:
            raise ValueError(f"{record['id']}: conservative input bound too long. Supply a shorter abstract; no silent truncation.")
        if batch and (len(batch) >= config['batch_size'] or count + bound > config['max_batch_token_bound']):
            yield batch
            batch, count = [], 0
        if bound > config['max_batch_token_bound']:
            raise ValueError('Document exceeds batch token allowance.')
        batch.append(record)
        count += bound
    if batch:
        yield batch


def http_embed(payload, key):
    body = json.dumps(payload).encode()
    req = request.Request(API_URL, data=body, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    with request.urlopen(req, timeout=90) as response:
        return json.load(response)


def validate_response(response, size, dimension):
    rows = response.get('data', [])
    if len(rows) != size or {r.get('index') for r in rows} != set(range(size)):
        raise ValueError('Embedding response has missing or duplicate indices.')
    vectors = [row.get('embedding') for row in sorted(rows, key=lambda r: r['index'])]
    for v in vectors:
        if not isinstance(v, list) or len(v) != dimension or any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in v):
            raise ValueError('Embedding response has invalid dimensions or values.')
        if not any(v):
            raise ValueError('Embedding response contains a zero vector.')
    return vectors


def run_embeddings(records, config, cache, key, transport=http_embed, pause=time.sleep):
    pending = [r for r in records if cache.get(r, config) is None]
    batch_list = list(batches(pending, config))  # Validate every input before the first paid request.
    report = plan(records, config, cache)
    if report['conservative_cost_usd'] + cache.spent_bound() > config['budget_usd']:
        raise ValueError('Conservative job estimate exceeds remaining local budget. Reduce the input or pilot size.')
    completed = 0
    for batch in batch_list:
        payload = {'input': [r['text'] for r in batch], **model_identity(config), 'output_dtype': 'float', 'truncation': False}
        amount = sum(token_bound(r['text']) for r in batch) / 1e6 * config['price_per_million_tokens']
        for attempt in range(config['max_attempts']):
            if completed or attempt:
                pause(60 / config['requests_per_minute'])
            attempt_id = cache.reserve(amount, config['budget_usd'])
            try:
                response = transport(payload, key)
                vectors = validate_response(response, len(batch), config['output_dimension'])
                usage = response.get('usage', {}).get('total_tokens')
                cache.save(batch, vectors, config)
                cache.finish(attempt_id, 'completed', usage)
                completed += len(batch)
                print(f'Cached {completed}/{len(pending)} new embeddings; reserved allowance ${cache.spent_bound():.4f}', flush=True)
                break
            except error.HTTPError as exc:
                cache.finish(attempt_id, f'http_{exc.code}')
                # Never print provider response bodies or request headers (could contain secrets).
                if exc.code not in [429, 500, 502, 503, 504] or attempt + 1 >= config['max_attempts']:
                    raise ValueError(f'Voyage request failed (HTTP {exc.code}); completed batches are cached.') from None
                pause(min(30, 2 ** attempt))
            except (error.URLError, TimeoutError, OSError):
                cache.finish(attempt_id, 'network_uncertain')
                if attempt + 1 >= config['max_attempts']:
                    raise ValueError('Network request failed; completed batches are cached.') from None
                pause(min(30, 2 ** attempt))
            except (ValueError, TypeError, KeyError):
                cache.finish(attempt_id, 'invalid_response')
                raise ValueError('Invalid embedding response; stopped without publishing results.') from None
    return completed


def normalized(vector):
    norm = math.sqrt(sum(x*x for x in vector))
    return [x/norm for x in vector]


def neighbors(records, vectors, top_k=5, method='auto'):
    if len(records) < 2:
        return []
    k = min(top_k, len(records)-1)
    if method == 'auto':
        method = 'exact' if len(records) <= 2000 else 'hnsw'
    if method == 'exact' and len(records) > 2000:
        raise ValueError('Exact search is limited to 2,000 papers. Use hnsw for the full collection.')
    vectors = [normalized(v) for v in vectors]
    pairs = {}
    if method == 'hnsw':
        try:
            import numpy as np
            import hnswlib
        except ImportError:
            raise ValueError('Large local search requires: pip install -r requirements-embedding-search.txt') from None
        matrix = np.asarray(vectors, dtype=np.float32)
        index = hnswlib.Index(space='cosine', dim=matrix.shape[1])
        index.init_index(max_elements=len(records), ef_construction=200, M=32, random_seed=42)
        index.add_items(matrix, np.arange(len(records)), num_threads=1)
        index.set_ef(max(100, k*4))
        labels, distances = index.knn_query(matrix, k=k+1, num_threads=1)
        iterable = ((i, [(int(j), float(1-score)) for j, score in zip(labels[i], distances[i]) if int(j) != i][:k]) for i in range(len(records)))
    else:
        iterable = ((i, sorted(((j, sum(a*b for a,b in zip(v,other))) for j,other in enumerate(vectors) if j != i), key=lambda item: (-item[1], records[item[0]]['id']))[:k]) for i,v in enumerate(vectors))
    for i, matches in iterable:
        for j, score in matches:
            a,b = sorted([records[i]['id'], records[j]['id']])
            pairs[(a,b)] = {'id': 'sim-' + digest([a,b])[:20], 'a': a, 'b': b, 'score': round(max(-1, min(1,score)),6),
                            'method': 'voyage-4-large-cosine', 'search': method,
                            'evidence_status': 'unverified', 'kind': 'conceptual_similarity'}
    return sorted(pairs.values(), key=lambda e: (-e['score'],e['id']))


def load_api_key(path=None):
    key = os.environ.get('VOYAGE_API_KEY', '').strip()
    if key:
        return key
    path = Path(path) if path else ROOT/'.env'
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        name, separator, value = line.strip().removeprefix('export ').partition('=')
        if separator and name.strip() == 'VOYAGE_API_KEY':
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ["'", '"']:
                value = value[1:-1]
            return value.strip() or None
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['estimate','embed','candidates','publish'])
    parser.add_argument('--source', choices=['research','corpus'], default='research')
    parser.add_argument('--input', help='Enriched JSON/JSONL with id, title, abstract, source_url, year')
    parser.add_argument('--config', default=str(ROOT/'config/voyage.json'))
    parser.add_argument('--cache', default=str(ROOT/'work/voyage/cache.sqlite3'))
    parser.add_argument('--limit', type=int)
    parser.add_argument('--allow-title-only', action='store_true', help='Explicitly accept reduced-quality title-only inputs')
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--search', choices=['auto','exact','hnsw'], default='auto')
    parser.add_argument('--output', help='Candidate artifact location; default: work/voyage/candidates.json')
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1 or args.top_k < 1:
        parser.error('Limit and top-k must be positive.')
    config = load_config(args.config)
    records = read_records(args.source,args.input,args.allow_title_only,args.limit)
    cache = Cache(args.cache)
    report = plan(records, config, cache)
    if args.command == 'estimate':
        print(json.dumps(report, indent=2))
        return
    if args.command == 'embed':
        if report['quality'].get('title_only') and not args.allow_title_only:
            raise ValueError('Title-only inputs found. Supply abstracts using --input, or explicitly use --allow-title-only. No API request sent.')
        key = load_api_key()
        if not key:
            raise ValueError('Set VOYAGE_API_KEY in your shell or the project .env file. Never commit it.')
        run_embeddings(records, config, cache, key)
        return
    vectors = [cache.get(r,config) for r in records]
    if any(v is None for v in vectors):
        raise ValueError('Some embeddings are missing or stale. Run embed with these same inputs first.')
    similarities = neighbors(records, vectors, args.top_k, args.search)
    artifact = {'schema_version': 1, 'model': model_identity(config), 'input_fingerprint': digest([(r['id'],r['text_hash']) for r in records]),
                'papers': [{k:r[k] for k in ['id','title','source_url','year','quality']} for r in records], 'similarities': similarities,
                'notice': 'Computed similarity candidates only. Relationship type and historical influence require separate evidence review.'}
    output = Path(args.output) if args.output else ROOT/'work/voyage/candidates.json'
    atomic_json(output, artifact)
    print(f'Wrote {len(similarities)} similarity candidates to {output}')
    if args.command == 'publish':
        research = json.loads((ROOT/'evolve/research.json').read_text())
        ids = {p['id'] for p in research['papers']}
        if {r['id'] for r in records} != ids:
            raise ValueError('Publication requires embeddings for exactly the current research papers. Full-corpus candidates stay in work/ for review.')
        atomic_json(ROOT/'evolve/generated/similarities.json', {'model': artifact['model'], 'input_fingerprint': artifact['input_fingerprint'],
                    'text_hashes': {r['id']:r['text_hash'] for r in records}, 'similarities': similarities})
        print('Published semantic similarities for the current evolution slice. Verified edges unchanged. Run build_evolve.py next.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as exc:
        print('Stopped: ' + str(exc), file=sys.stderr)
        sys.exit(1)
