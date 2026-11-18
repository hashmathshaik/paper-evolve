# Paper Evolve

Run locally with no API keys or installation:

```sh
python3 -m http.server 8765
```

Open http://localhost:8765. Run from this repository directory. Use HTTP rather than opening index.html directly.

## What works

Evolution opens an exploration start page with real connected papers selected
from the published graph. Search from Evolution opens the selected paper's
actual neighborhood and abstract. **Change paper** returns to the start page.
The focused paper is encoded in the URL, so refresh and browser Back/Forward
restore the selected timeline. No sample topic is loaded as the default.

Landscape drills down from research areas to topics and papers. Browse offers
search, year/venue filters, sorting, pagination and complete abstracts. Both use
the full 70,861-paper corpus. The graph supports moving cards, zoom/pan, filters,
ancestor/descendant highlighting and tracing paths. Connection details retain
source passages, inheritance/change explanations and model/review provenance.
The interface uses FK Grotesk with local/system fallbacks.

## Research scope and limitations

The published graph covers a growing subset of the corpus; not every paper has
a supported contribution relationship. Source-passage-supported predictions are
the default quality filter. Older abstract-only predictions are available under
All connections. Model confidence and model agreement are not calibrated
accuracy or expert human verification. Missing relationships are not fabricated.
Voyage similarity is a separate discovery layer and does not imply influence.

## Architecture and data

`evolve/paper-data.js` reads the static corpus and abstract shards.
`evolve/neighbourhood.js` assembles the selected paper's graph from relationship
shards and the accepted community overlay. `scripts/evolution_starters.py`
selects diverse, connected starting papers using those same public artifacts;
it makes no paid requests and requires no private database on GitHub Pages.
`evolve/evolution-route.js` preserves paper identity in the fragment URL.
The older sample data/preparation files remain development assets and are no
longer loaded by the app at startup.

The upstream Python/Parquet ingestion and clustering utilities remain available;
`build_frontend.py` produces the original atlas rather than Paper Evolve.
For the current app, validate and package the prepared artifacts with:

```sh
python3 -m unittest discover -s tests
python3 build_evolve.py
```

Serve `dist/` to distribute the static application. API computation runs only
through the separately configured local preparation workers below.

## Attribution

Adapted from Paper Atlas by Gnaneswar Villuri: https://github.com/villurignanesh/paper-atlas. Preserve LICENSE (MIT, copyright 2026 Gnaneswar Villuri). Bundled Valley Sans and Instrument Serif retain their SIL OFL notices in fonts/. Research metadata remains with the original authors and venues. Attribution is retained in this document and LICENSE.

## Evolution interface update

The interface uses compact controls, movable paper cards and restrained teal accents. Evolution starts with actual connected papers, with source-supported relationships prioritized in each neighborhood. Revives is available in the schema, renderer, filters, legend and guide, but appears only when explicit revival evidence is available.

## Local computation → GitHub Pages

Run `python3 build_evolve.py` from the repository root to validate accepted community reviews, generate starting papers from the published graph and package `dist/`. The browser reads prepared static JSON. Generating additional relationships is a separate local Qwen job, not a browser action.

Commit the prepared JSON with the app to your own GitHub repository. Enable **Settings → Pages → Source: GitHub Actions**. The included `.github/workflows/pages.yml` validates and packages the already-computed data, then deploys `dist/` after pushes to `main` or `master`. Computation is not repeated in deployment. All app and data URLs are relative, supporting GitHub Pages repository subpaths. Actual GitHub publication has not been performed in this workspace.

Landscape and Browse have an Evolution action for each paper. Paper notes provide the same action. Papers without supported relationships retain their available similarity links; failed or missing data never loads an unrelated example timeline.

## Movable graph

Drag paper cards to rearrange the map. Connections follow the blocks and route around other cards. Arrow keys move a focused card; Shift+arrow moves in smaller steps. The layout persists in local browser storage; Reset layout restores chronological columns. Paper date badges and edge direction retain the research chronology when users manually move cards. Hovering/selecting a paper emphasizes its connections. Fit map scales the canvas to the available width.

## Qwen API edge building

The project API pipeline uses **Qwen only**. Qwen3.7-Flash proposes relationships;
positive candidates receive a separate, blind Qwen3.7-Plus source review. The
reviewer does not see the proposal. Only explicitly supported types agreed by
both enter the new seed pool. These are model predictions, not human-verified
facts or calibrated probabilities. Agreement can share errors.

The five labels are **Extends, Challenges, Combines, Transfers and Revives**.
**Similar** remains an embedding-based discovery link. A shared problem,
reference-list entry, baseline comparison or possible future combination does
not establish an inherited contribution. Revives requires an explicit revival
statement. Missing evidence remains pending rather than producing a forced edge.

Configure `DASHSCOPE_API_KEY` in ignored `.env`; the reviewed endpoint is Singapore.
No key enters browser code, public JSON or a Pages workflow. Source documents are
retrieved locally from official hosts, with title checks, document fingerprints,
page numbers and exact excerpts. Every new seed positive requires a source from
paper A and a citation passage from paper B.

```sh
.venv-voyage/bin/python scripts/pipeline/seed_edges.py plan --scope expanded --max-candidates 0
.venv-voyage/bin/python scripts/pipeline/seed_edges.py run --scope expanded --max-candidates 0 --workers 32 --source-workers 8 --publish-every 200
.venv-voyage/bin/python scripts/pipeline/seed_edges.py status
```

The durable ledger is `work/edges/relations.sqlite3`. Its **$30 cumulative edge
ceiling** includes previous charges/reservations and remains subject to the
**$50 whole-project ceiling**, historical preparation and contingency. Allowances
are reserved before requests. Unknown outcomes retain their allowance and are
not automatically retried. Explicit provider `data_inspection_failed` rejections
skip that pair without changing its text or stopping unrelated comparisons.
Only the provider error code is retained, never the error message or body.
Isolated invalid responses are quarantined; repeated
failures stop the worker. The active run uses cached Jev rankings without new
Jev API calls. Similarity or a Jev score never establishes an edge.

Expanded scope includes in-corpus Semantic Scholar/OpenAlex citations and cached
citing contexts outside the embedding-neighbor queue. It excludes same-title
copies, same-year/reversed citations, and previously completed or quarantined
comparisons. These candidates still require source passages and both Qwen models
before publication. `--max-candidates 0` considers the entire eligible pool so a
small selected batch cannot end the run with budget left; the spending ceiling,
source availability and provider health still bound the run.

Create `work/edges/SEED_PAUSED` or send SIGTERM for a graceful stop. In-flight
responses are collected and accounted for. Results are exported in batches to
static shards and `dist/`; no backend is needed on GitHub Pages. The older direct
and Batch Qwen entry points remain separately paused. A full corpus does not
mean every pair has been reviewed or every paper has a valid evolution parent.

The seed pipeline overlaps source retrieval and model requests. Up to 32 review
pipelines share the same persisted budget, each with its own SQLite connection.
An immediate transaction claims each pair and reserves its maximum allowance
before calling Qwen. Ready source packets are consumed as they finish, so a
slow PDF does not block other papers. Queues are bounded; pauses, budget limits
and provider errors stop admission and drain in-flight work. A coordinator owns
progress/publication and reports active requests every ten seconds. Concurrency
does not change model choices, prompts, source checks or type-agreement rules.

An isolated network/gateway failure is quarantined with its full conservative
allowance retained. That request is not resent; other pairs may continue.
Repeated invalid/uncertain outcomes still stop admission, as do authentication,
billing and other definitive provider errors. Rejected HTTP status codes are
recorded without retaining error bodies or credentials.

The provider-neutral `scripts/relation_core.py` owns relationship rules, exact
quotation validation and shared accounting. It contains no model client or
credential loader. The retired API integration and its local credential have
been removed. Historical results retain their original model provenance and
charges for reproducibility; they are not relabeled as Qwen results.

## Contributions through APIs, Codex, Claude Code or local models

This is a separate contribution path. Contributors use their own assistant
account, a local open-weight model, or manual reading; the project does not need
their API keys. Using Claude Code or Codex in a local terminal does not mean the
model weights run on that machine.

`contribute.html` offers 46 organized topic packs with 10 source-ready tasks
each. Choose an agent or API route and download a self-contained kit with its
prompt, schema, task evidence and portable Python CLI. Landscape topic pages
link directly to the matching contribution pack. No dependency installation is
required for the CLI; the legacy starter pack is also retained.

```sh
python paper_evolve.py list
python paper_evolve.py start --pack PACK_ID --name "Your name" --tool "Actual agent / model version"
python paper_evolve.py check --workspace work/contributions/PACK_ID
python paper_evolve.py export --workspace work/contributions/PACK_ID --output community/submissions/PACK_ID-your-name.json
```

The optional API route uses `--method api` and the separate `api` command.
Contributors supply an OpenAI-compatible endpoint, model, current token rates,
cumulative workspace budget and a key environment variable. The runner reserves
allowances before requests, preserves ambiguous holds, resumes unattempted work
and validates the same decision schema as agents. It never reads the project
`.env`, changes seed-worker pause flags or publishes contributions. See
`community/API.md`. Its HTTP transport was exercised against a local test server;
no live paid provider was called while building this system.

Contributor agents may also research full papers. `fetch` downloads official
PDFs and writes page-marked text; `cite` verifies exact page excerpts against
the PDF and attaches them under `source_material` without changing the initial
task fingerprint. These registered sources work in both agent and API submissions.
Raw PDFs stay local. Maintainers verify new source authenticity separately;
offline quote validation alone does not prove a source matches its public paper.
See `community/RESEARCH.md` and decision 019. This supersedes the original
prepared-excerpts-only agent restriction.

Frozen tasks
include identities, abstracts, source links, available citation passages and
content fingerprints. The standard-library CLI generates a submission template
and checks exact quotes, chronology, labels, duplicates and evidence coverage
without a paid request or private corpus. Maintainer acceptance is separate from
validation. An assistant check is never labeled human verified. Accepted reviews
form a static overlay that can add, correct or withdraw a model prediction.
See `CONTRIBUTING.md` for commands and source-review rules.

## Complete abstract coverage

`python3 scripts/pipeline/audit_corpus.py` checks every corpus URL for a real cached abstract, retrieval provenance, and an embedding cache key matching that exact title/abstract text and configured Voyage model. Per-paper audit records remain in `work/abstracts/audit.jsonl`; a public count-only coverage report is exported to `evolve/generated/coverage.json`.

Missing OpenReview abstracts can be recovered with `.venv-voyage/bin/python scripts/pipeline/recover_mirrors.py --small-only` (requires `pyarrow`). Mirrors are pinned to a dataset commit and accepted only by exact OpenReview note ID and normalized title; contradictory duplicate abstracts are rejected. Dataset file hashes and accepted matches are retained locally. `python3 scripts/pipeline/recover_acl_pdf.py` handles ACL records whose official HTML/XML omit their abstract by extracting the Abstract section from the official PDF, requiring Poppler's `pdftotext`. No missing abstract is synthesized by a model.

After embeddings catch up, `.venv-voyage/bin/python scripts/pipeline/edges_knn.py` rebuilds nearest neighbors over the full current embedding cache and atomically replaces the neighbor file. Run the Qwen seed planner again after the neighbor file changes. Legacy Jev labels are reused for prioritization without paying to classify them again.


### Paper reader and public abstracts

Evolution cards, discovery search results and library rows use the same reader. Selecting a paper shows its full title, real venue/year, available author metadata, complete abstract and source link. Author names are not inferred from venue names. The reader provides the evolution action, while connection views link both endpoint papers back into the same reader. Abstract fetches are guarded against stale responses when the selection changes. Library rows include two-line abstract previews, with newest/oldest/title sorting and bounded pagination.

`scripts/export_abstracts.py` publishes all 70,861 corpus abstracts from the completed local SQLite cache to 142 static files under `evolve/generated/abstracts/`. Each file holds up to 500 papers; the browser lazily fetches only the required files and shares a single corpus/data cache across views. Every row carries its paper URL and is checked against it before display. Retrieval URLs are stripped of private query parameters; public paper IDs remain intact. The static build regenerates this export when the local cache changes. The full corpus export was checked against the exact cached text for every paper. No paid model requests are involved in reading papers.

The larger timeline cards retain complete titles in the DOM and show full titles in tooltips and the reader. The default viewport preserves readable card text with scrolling; Fit explicitly switches to an overview. Moving cards only changes their presentation, not the underlying relationships or chronology.

The Explore research panel stays docked at widths above 760px, including compact desktop browsers. Its heading, search field and compact collection footer stay fixed while only results/filters scroll. Paper details temporarily replace it and closing the reader restores the previous desktop explorer state. Empty search focus keeps filters visible; explicit topic selection opens the topic list. Search includes Clear, keyboard result navigation, cancellation of stale work and a useful retry state. Resizing preserves an open reader.

The explorer was simplified further at the user’s request: one visible search box serves papers and topics throughout the app. The separate Topic and Focus paper controls, duplicate sidebar navigation, and second library search box are removed. Enter opens the full collection results, suggestions open a paper or topic, and Clear resets the active collection search. Timeline filters are collapsed by default, with venue hidden when there is only one venue in that timeline. Library year, venue and sorting controls remain next to their results.


### UI review — 2026-11-14

Landscape now uses stable category colors and meaningful paper/topic counts. Raw `Unclustered` labels display as Uncategorized research. Paper sorting is hidden on area cards. Evolution actions belong to individual paper rows instead of selecting an arbitrary paper globally. Paper lists paginate above and below the results; controls disappear when a single page is sufficient. Header navigation supports browser Back and Forward without losing the current library page.

The reader distinguishes uninspected relationships from an empty filtered graph, and graph-origin connections follow the active evidence filters. Formula formatting uses bundled KaTeX 0.19.1 and local fonts, with its MIT license and provenance under `assets/vendor/katex/`. Common prose formatting commands are cleaned only for display; original cached/exported abstracts remain unchanged. HTTP(S) links are escaped, math trust is disabled, and no third-party requests are needed for math rendering. Source and integration reference: https://katex.org/docs/autorender.

Path tracing now reports its origin, valid paths and missing paths. Fit can zoom below the former 35% floor to actually contain the whole timeline. Drag thresholds use screen pixels, preventing small movements from becoming drags at overview scales. Builds apply a stable content hash to UI asset references so edited modules are not served from stale browser caches.
# Paid Qwen Batch edge generation

**Availability check, November 14, 2026:** The Singapore service accepted the
uploads and created jobs, then rejected both `qwen3.7-flash` and
`qwen3.7-flash-2026-07-15` during validation with `model_not_found` / "not
supported by the Batch API." No inference was performed. Reservations were
released, and no real-time fallback was started. The pricing page's advertised
Batch discount did not establish availability on this endpoint. The worker
blocks repeat submissions to these known unsupported routes. Do not describe
this pipeline as currently running.

The official model list supports Qwen3.7-Flash Batch in Beijing. That route is
implemented but has not been invoked: configure `QWEN_BATCH_BASE_URL` as
`https://dashscope.aliyuncs.com/compatible-mode/v1` and put the Beijing-region
key in `QWEN_BATCH_API_KEY` locally. The existing Singapore key is not reused.
The worker records each request's region, uses that region's prices, and
rejects submission/collection with mismatched regional configuration.

`scripts/pipeline/qwen_batches.py run --watch` uses Qwen3.7-Flash through Model Studio's
OpenAI-compatible Batch API in Singapore. It shares the historical project
ledger and reserves the conservative maximum request cost before submission.
The original $50 total cap, preparation allowances, and contingency remain in
force. It stops admitting jobs when the remaining allowance is insufficient.
There is no real-time fallback and no additional paid Jev screening.

The first job contains 16 real candidates to check API and output compatibility.
After usable results are collected, the worker admits up to three jobs of 5,000
requests each. Charges use the published 50% Batch rates and actual input/output
usage. Unknown submissions, missing result rows, and unreported usage retain
reservations. Completed pairs are not automatically reviewed again. A restart
collects known provider job IDs; ambiguous submissions require reconciliation.

Progress: `work/edges/qwen-batch-status.json`. Local inputs/results:
`work/edges/qwen-batches/`. Create `work/edges/QWEN_BATCH_PAUSED` to stop new
submissions while continuing collection, or send SIGTERM to stop the worker.
Submitted jobs are still accounted for. Accepted predictions are exported to
the static app after collection. The older real-time Qwen runner stays paused.

API and pricing: [Batch API](https://www.alibabacloud.com/help/en/model-studio/batch-interfaces-compatible-with-openai),
[Singapore model pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing).

# Free-quota edge generation

`scripts/pipeline/free_quota_edges.py run` uses all seven text models whose remaining
allowances and Stop-on-Exhaust switches were checked in the Singapore console.
Its local configuration is `work/edges/free-quota-models.json`; verification is
valid for 24 hours when starting requests. It never disables Stop-on-Exhaust,
uses Batch, or falls back to paid inference. The paid Qwen runner stays paused.

Workers share a resumable queue and reuse completed comparisons. Ready citation
packets run first, followed by cached Jev positives and new citation/embedding
candidates. This worker buys no additional Jev screening. If citation passages
are unavailable, both abstracts must support the prediction and the published
edge is labeled abstract-based. Similarity stays a separate link type.

All models write into the existing edge ledger, retaining their exact model IDs
and source excerpts. Accepted edges are exported to the static app every two
minutes and on shutdown. Progress is in `work/edges/free-quota-status.json`.
Create `work/edges/FREE_QUOTA_PAUSED` or send SIGTERM to stop admitting requests;
in-flight requests are drained. Exhausted/unsupported models stop and another
worker can take their unsent pair; uncertain network outcomes are not resent.
