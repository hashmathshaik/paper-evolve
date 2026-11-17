# Voyage embeddings for Paper Evolve

The code is ready for `voyage-4-large`, using 2,048-dimensional float embeddings. All API calls run from your local Python CLI. The website only receives public, precomputed similarity links. No API key is included in the app or GitHub Pages build.

## 1. Get abstracts

The bundled 70,861-record website corpus has titles/topics/links, but **no abstracts**. Original ingestion uses OpenReview for ICLR, ACL Anthology for ACL/EMNLP/NAACL, PMLR for ICML, and NeurIPS proceedings. These official sources supply abstract text; no paid embedding API is needed to retrieve it.

A new stdlib fetcher caches successful source responses and records provenance. Default scope is the current seven-paper research slice, whose source links point to arXiv:

```sh
python3 scripts/fetch_abstracts.py --source research --write-research
```

For a 200-paper corpus pilot:

```sh
python3 scripts/fetch_abstracts.py --source corpus --limit 200
python3 scripts/voyage_pipeline.py estimate --input work/abstracts/papers.jsonl
```

The output contains successfully retrieved abstracts, with a separate `.report.json` recording failures. It never generates missing abstracts. Some OpenReview records require authentication or are unavailable; these remain missing. Requests are paced and successful results are cached. Fetching the entire corpus is a substantial crawl; start with a pilot. Old NeurIPS markup and source changes can still require adapter updates.

Alternatively, supply JSON/JSONL records with `id`, `title`, `abstract`, `source_url`, and `year`. Keep stable IDs when enriching records. Existing upstream `data/normalized/**/*.parquet` records already have abstracts if you have that original dataset; it is not included in this checkout.

## 2. Set your key locally

In zsh/macOS, enter it without echoing it or storing it in shell history:

```sh
read -s 'VOYAGE_API_KEY?Voyage API key: '
export VOYAGE_API_KEY
```

The CLI reads `VOYAGE_API_KEY` from the environment first, then the local project `.env` file. You can place `VOYAGE_API_KEY=your_key` in that ignored file instead of using the shell prompt. `.env.example` is reference documentation only. Never paste the key into JavaScript, JSON, a workflow file, or a commit.

## 3. Estimate and embed the prepared research slice

From this repository's root:

```sh
python3 scripts/voyage_pipeline.py estimate
python3 scripts/voyage_pipeline.py embed
python3 scripts/voyage_pipeline.py candidates --top-k 2
python3 scripts/voyage_pipeline.py publish --top-k 2
python3 build_evolve.py
```

The site automatically uses the generated Voyage similarity artifact when it matches the current research inputs. Otherwise it uses the existing, labeled TF-IDF baseline. Evolution edges and their evidence are unchanged by embedding jobs.

For your enriched pilot use the same `--input` path for estimate, embed, and candidates. `publish` intentionally requires exactly the curated research paper IDs and matching text in `evolve/research.json`; full-corpus candidates stay local for review. To publish abstracts from external input for the curated slice, first add that same abstract text to the corresponding research records.

## Cost, caching and quality controls

`config/voyage.json` fixes the reviewed model, output dimensions, price assumption ($0.12/M tokens), $20 local spending allowance, batch size, and request pacing. Estimates include both approximate token counts and a deliberately conservative UTF-8-byte allowance. These are **not exact tokenizer counts** and assume no free-tier credits. Recheck the provider's price before a large job. The local allowance covers this cache's recorded attempts, not unrelated account usage or another cache. Configure account billing limits separately where supported.

Every attempt reserves its conservative cost in `work/voyage/cache.sqlite3` before sending, including failed/uncertain attempts that may have been billable. Transient errors retry with pacing; completed batches survive interruption. Text/model/dimension changes invalidate only the affected cache keys. Do not delete the spending ledger while running a budgeted job. Input truncation is disabled. Oversized inputs fail before any batch is sent. Invalid response indices, dimensions, non-finite values, and zero vectors stop the job.

Title-only embedding requires an explicit `--allow-title-only`; it is not the recommended quality path. Abstracts are sufficient for semantic retrieval, but detailed relationship verification needs full-paper passages.

## Full collection candidate search

Up to 2,000 records use exact local cosine search. Above that, install the optional local search dependencies:

```sh
python3 -m pip install -r requirements-embedding-search.txt
python3 scripts/voyage_pipeline.py candidates --input work/abstracts/papers.jsonl --search hnsw --top-k 5
```

HNSW avoids computing/storing a full all-pairs similarity matrix. It is approximate; benchmark recall and scientific relevance before scaling the pilot. Embedding/search setup has not yet been tested with a real Voyage key or large-corpus HNSW run. Offline tests use simulated API responses.

## Static delivery

`python3 prepare_local.py` remains the credential-free lexical baseline + tests + static packaging command. It does not spend API credits or overwrite a matching generated Voyage artifact. GitHub Actions builds the checked-in public artifacts; it never invokes Voyage. The build excludes scripts, configs, caches, vectors, and environment files.

Documentation: https://docs.voyageai.com/reference/embeddings-api and https://docs.voyageai.com/docs/tokenization

## Continuous embedding while abstracts download

The active worker is `python3 scripts/embedding_queue.py --refresh-every 10000`.
It reads the shared abstract cache on startup, admits newly downloaded records whenever another 10,000 arrive, and checks for smaller remainders whenever its pending queue empties. The next cycle continues without manual snapshot commands. Exact text/model cache keys prevent re-embedding completed records. The local input snapshot and `work/voyage/embedding-status.json` update with each admission and completed batch.

Voyage Retry-After headers are honored. The worker remains subject to provider rate limits and the conservative $14 embedding allowance, leaving up to $6 for the separate OpenAlex recovery run. Oversized abstracts are recorded for review. SIGINT/SIGTERM stop at a safe batch boundary; relaunching resumes from cached vectors. Do not run `embed_downloaded.py` alongside it; both workers share an exclusive embedding lock.

## Run all workers together

From the repository root, use `python3 scripts/run_pipeline.py`. This supervises source downloads, OpenAlex ICLR recovery, and the continuous Voyage embedding queue. Check `work/pipeline/status.json` for the two progress totals, worker PIDs, phases, and retry times. Individual logs remain in their respective work directories.

Only one supervisor and one worker of each type may hold their locks. SIGTERM/SIGINT requests a graceful shutdown; in-flight batches are saved before the worker stops. Source requests use a bounded worker queue, origin pacing, and shared SQLite WAL storage. Unexpected worker crashes restart with backoff (up to three times). Provider, budget, or invalid-input stops remain visible and are not silently bypassed. Provider throttling waits and retries automatically. The embedding worker starts with conservative request/token pacing and slows further if Voyage returns HTTP 429; this is an adaptive local limit, not a claim about the account's published quota.

A supervised start/stop smoke test passed for all three workers, with cached data preserved and all worker exit codes zero. Live provider quotas can still delay processing.
