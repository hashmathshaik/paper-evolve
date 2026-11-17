# Contributing to Paper Evolve

## Fork, clone and contribute

You can do the entire contribution inside a repository clone. Fork Paper Evolve
on GitHub, then clone your fork and choose a topic pack:

```sh
git clone YOUR_FORK_URL paper-evolve
cd paper-evolve
python paper_evolve.py list
python paper_evolve.py start --pack PACK_ID --name "Your name" \
  --tool "Actual Claude Code or Codex / model version"
```

Open the cloned folder in your agent and give it the generated `PROMPT.md`.
Root `AGENTS.md` and `CLAUDE.md` direct agents to the contribution workflow.
For the API route, add `--method api` when preparing the workspace and follow
[the API guide](community/API.md).

```sh
python paper_evolve.py check --workspace work/contributions/PACK_ID
python paper_evolve.py pr --workspace work/contributions/PACK_ID
```

The `pr` command exports the validated contribution and prepares a branch name,
Git commands and PR description. It does not execute Git operations or contact
GitHub. Follow the generated `GIT_STEPS.md` to commit only the submission, push
to your fork, and open a pull request. See [the full clone guide](community/CLONE.md).

GitHub Pages hosts the app and task packs. GitHub pull requests receive the
contributions. CI validates them; a maintainer separately accepts the evidence.
Merging an acceptance rebuilds the Pages graph. No upload server is needed.

## Or start with a downloaded topic kit

Open [Contribute connections](contribute.html), choose a research topic, then
choose **Claude Code / Codex** or **Your API**. Download and unzip the kit. Each
new topic pack has 10 paper pairs with prepared source passages, source links,
the common prompt, a decision schema and a portable Python contributor tool.
Validation needs only Python 3.10+ and no private corpus. For full-paper
extraction, use your existing pdftotext/Poppler or pypdf installation; see
[RESEARCH.md](community/RESEARCH.md).

From a repository checkout or extracted kit:

```sh
python paper_evolve.py list
python paper_evolve.py start --pack PACK_ID --name "Your name" \
  --tool "Actual tool / model version"
```

**Agent route:** give your Claude Code/Codex agent the generated `PROMPT.md`.
It researches full public papers and fills `submission.json` using prepared
evidence plus any newly registered page excerpts. Use `fetch` to download and
extract the papers and `cite` to attach exact quotes without altering the task
pack. See [the research guide](community/RESEARCH.md). The workspace includes
`AGENTS.md` and `CLAUDE.md`. Your agent uses your own account; Paper Evolve does
not need its credentials. You can also use a local model or read manually.

**API route:** start a separate workspace with `--method api`, then follow
[the API guide](community/API.md). You explicitly select a compatible endpoint,
model, current token prices and cumulative budget. The key stays in your local
environment. The API command never starts the maintainer's Qwen seed worker.

Both routes finish with the same commands:

```sh
python paper_evolve.py check --workspace work/contributions/PACK_ID
python paper_evolve.py export --workspace work/contributions/PACK_ID \
  --output community/submissions/PACK_ID-your-name.json
```

Replace placeholders with your actual pack/name. Export refuses invalid
evidence and will not overwrite an existing contribution file. Open a pull
request containing that JSON in the public project repository. When working
from a downloaded kit, copy the exported file into the same path in your fork.
Do not include workspace files or credentials. Submission and acceptance are
separate; only a maintainer should approve an edge after checking its sources.

Availability updates when the site builds. Check existing pull requests before
working on a pack to avoid overlap. Tasks are selected by the later paper's
topic; earlier papers may come from another field. Missing evidence is a useful
abstention, and source readiness does not imply that a true relationship exists.

## Lower-level review commands

No API key, embedding download, private cache or paid request is required.
Use Python 3.10+ and a task pack from `community/tasks/`. Start with a few pairs.
You can read them yourself, use a local open-weight model, or use your own
Claude Code/Codex account. Running an assistant in a terminal does not mean its
model weights run locally. The project never needs your assistant credentials.

1. Download or clone this repository and choose a committed task pack.
2. Generate a submission with the task IDs and evidence fingerprints filled in:

   ```bash
   python scripts/community_edges.py template \
     --pack community/tasks/starter-001.json \
     --output community/submissions/your-name.json \
     --name "Your name" --tool "Exact tool/model version" --method assistant
   ```

   Use `--method local_model` for inference on your machine or `manual` for
   unaided reading. The blank template is deliberately invalid until reviewed.

3. Give your tool `community/REVIEW_PROMPT.md`, `community/decision.schema.json`,
   the pack and your submission file. Review the actual quoted sources yourself
   when possible. Keep only the tasks you reviewed in the decisions array.
4. Validate locally, then open a pull request containing the submission:

   ```bash
   python scripts/community_edges.py validate \
     --pack community/tasks/starter-001.json \
     --submission community/submissions/your-name.json
   python scripts/community_edges.py check
   ```

Each positive needs an explicit link between the particular contributions,
quotes from both papers, what was retained, and what changed. When full-text
passages are supplied, quote a `b_citation_*` passage and a source from A. A
missing-context task should stay an abstention until its evidence is improved.
Keep original source IDs and task fingerprints unchanged. Agents may retrieve
and read full papers, trace references and add page-specific evidence with
`fetch`/`cite`. The additive source snapshots travel in the submission; PDFs
stay in the ignored workspace. Maintainers verify new excerpts against the
published paper. Do not silently rewrite the original task evidence.

Allowed types are **Extends, Challenges, Combines, Transfers and Revives**.
Several types may apply when each has evidence. Similarity is a separate
discovery layer; a reference list entry or shared vocabulary is insufficient.
Abstentions and corrections are welcome. Confidence is a self-assessment, not
measured accuracy, and never replaces source review.

## Maintainer review and publication

CI checks formats, identities, duplicate submissions, exact quotes and evidence
coverage. It does not judge whether a quote really supports the claimed type.
Read the source evidence before accepting. Contributors submit proposals;
maintainers alone should change `community/approved/`. Require maintainer PR
approval/branch protection on the eventual public repository.

```bash
python scripts/community_edges.py accept \
  --pack community/tasks/starter-001.json \
  --submission community/submissions/your-name.json \
  --reviewer "Reviewer name" --reviewer-kind human \
  --note "Explain the contribution link and any type corrections."
python scripts/community_edges.py check
python build_evolve.py
```

Use `--reviewer-kind assistant` for an AI-assisted check without actual human
review. It will not be labeled human verified. The immutable acceptance record
retains the original submission and evidence snapshot. Reconcile an existing
approval explicitly when correcting it; duplicate approved pairs fail the build.
Accepted abstentions can withdraw unsupported paid predictions. The static
community overlay overrides a paid result for the same pair and requires no
backend or private SQLite database on GitHub Pages. Submissions are never
published automatically just because a validator passes.

To issue a task for a correction to an already reviewed edge, add
`--pair EARLIER_PAPER_ID LATER_PAPER_ID` to the export command. Use a new pack
filename when refreshing source evidence; task fingerprints must not change
silently in an existing pack. Normal exports skip previously issued pairs.

To issue new tasks using a maintainer's local corpus:

```bash
python scripts/community_edges.py export --limit 100 \
  --output community/tasks/next-pack.json
```

## Budgeted seed generation (maintainer only)

```bash
.venv-voyage/bin/python scripts/seed_edges.py plan
.venv-voyage/bin/python scripts/seed_edges.py pilot
.venv-voyage/bin/python scripts/seed_edges.py run --max-candidates 30000 --workers 32 --source-workers 8
.venv-voyage/bin/python scripts/seed_edges.py status
```

These paid commands use the existing Singapore Qwen key in ignored `.env`.
Qwen3.7-Flash proposes relationships; positive candidates receive a separate,
blind Qwen3.7-Plus review. Only explicit, passage-supported types agreed by both
enter the new seed pool. Agreement is a quality filter, not measured accuracy.
The shared ledger enforces a **$30 cumulative edge ceiling**, including previous
edge spending, and the **$50 overall project ceiling**. Cached Jev scores rank
candidates; this worker sends no new Jev requests. It fetches source evidence
first, skips already reviewed/reserved pairs, and holds funds for ambiguous
requests rather than retrying them. Create `work/edges/SEED_PAUSED` to stop new
requests safely; an in-flight response is still collected and accounted for.
The older direct/Batch workers remain paused. Source retrieval failures do not
become invented edges. A completed priority queue can finish below the cap.
Review concurrency is bounded to 32; source retrieval runs separately. Workers
claim/reserve through immediate SQLite transactions, so increasing concurrency
does not raise the budget or pay twice for the same pair. Source results are
consumed out of order to avoid blocking ready comparisons on one slow PDF.

The maintainer's Qwen credentials have been removed and all seed pause flags are
set. Contributor kits operate independently and do not clear those flags.
Prepare additional packs from local caches without inference/network requests:

```sh
.venv-voyage/bin/python scripts/contribution_packs.py export --pack-size 10
python scripts/contribution_packs.py catalog
python build_evolve.py
```

The export starts with unused cached source packets, then extracts new citing
passages from already cached PDFs, and marks any remaining source gaps honestly.
It never overwrites an existing evidence pack. Public kits are regenerated from
an explicit file whitelist at build time; `.env`, private caches and ledgers are
excluded. `community/bundles/` is a reproducible, ignored output directory.

## Existing pipeline development notes

Thanks for looking at this. A few things about how this repo works, so your first PR
doesn't need three rounds of "actually, here's why we didn't do it that way."

## Read the decision logs first

`docs/decisions/` is the actual history of this project: every non-trivial choice
(which embedding model, how clusters are built, why one source was picked over
another) is written up there, with the options considered, what was chosen, why, and
what would change the decision. Before touching a phase, read the relevant log. Before
*proposing* a change to a phase, check whether it's already been tried and rejected.
Several approaches in `011-clustering.md` in particular were tested and abandoned for
measured, not assumed, reasons.

**If you make a non-trivial decision in your PR, add a log entry for it**, same format
as the existing ones: context, options considered, what you chose, why, what would
make you revisit it. This is the single most important convention in this repo. It's
what makes the project reproducible and defensible, not just working.

## Local setup

```bash
uv sync          # installs the project's Python environment
```

Data (`data/`) is gitignored and not checked in; you'll need to run the ingestion
adapters yourself (`paper_atlas/adapters/`) to build a local corpus, or ask in an issue
if you need a copy of the processed Parquet files for development.

## The GPU / remote-job pattern

Several phases (embedding, projection, clustering) are compute-heavy enough that they
were run on a remote GPU box during development, not the author's laptop
(`docs/compute.md` has the reasoning; the honest summary is a 4096-dim embedding over
70k+ papers is a bad time on 8GB of unified memory). The `remote_jobs/` directory holds
self-contained scripts meant to be pushed to *any* GPU machine and run there. They
don't depend on the rest of this package, only on the normalized Parquet files.

If you have GPU access: `remote_jobs/RUN.md` shows the push → run → pull pattern.
Genericize the hostnames to your own machine. The ones in earlier project history
pointed at a specific university lab box and have been scrubbed from this public
version.

If you don't: most experiments are still doable on CPU at reduced scale (subsample the
corpus, use a smaller embedding model). Say so in your PR and it's a fine tradeoff for
a first pass.

## Before proposing changes to Phases 2-6

Embedding model choice, projection settings, clustering approach, and evaluation
methodology are all *measured* decisions with numbers behind them, not defaults. If you
think one should change, the strongest PR includes a comparison: old approach vs. new,
on the same data, not just an assertion that the new approach is generally better.
This project's whole ethos is "measure, don't guess" (see the noise-baseline and
seed-stability work in `docs/decisions/003-success-criteria.md` and
`011-clustering.md` for what that looks like in practice). PRs are held to the same
bar.

## Task backlog

`future_work.md` has scoped-out tasks with suggested approaches and open questions,
roughly ordered by difficulty within each item. Good first issues are marked as such.
If you want to take one on, comment on the corresponding issue (or open one if it
doesn't exist yet) before starting; some of these have real architectural forks in
them worth agreeing on before writing code.

## Long-term direction

[papercopilot.com](https://papercopilot.com) is the closest thing to a scale reference
for where this project could grow: submission/acceptance statistics, reviewer score
dynamics, institution rankings, live-updated, at a similar corpus size. It does **not**
have a semantic content map; that's this project's actual differentiator and isn't
something later tasks should trade away in pursuit of feature parity. Tasks 6-8 in
`future_work.md` are the direct Paper-Copilot-inspired additions (institution rankings,
submission/acceptance rates, review-and-rebuttal analytics), each is scoped as its own
significant undertaking, not a quick add-on, because each needs data this project does
not currently collect. Read the "why this is hard" section of each before starting one.

## What a good PR looks like here

- Cites the relevant decision log(s) it builds on or changes.
- If it changes methodology (not just UI/tooling), includes before/after numbers.
- Adds its own decision log entry if it made a non-trivial call.
- Doesn't silently widen scope: if you notice something else that's broken while
  working on your task, mention it in the PR description rather than fixing it inline,
  unless it's trivial.
