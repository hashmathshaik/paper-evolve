# Paper Evolve

Explore how research contributions develop across 70,861 papers. Follow
evidence-backed connections—Extends, Challenges, Combines, Transfers and
Revives—and use semantic similarity as a separate discovery layer.

The app runs as a static site on GitHub Pages. Papers, topic clusters and
prepared contribution packs are included; contributors do not need the private
embedding/source caches or a backend.

## Contribute from a clone

Fork this repository on GitHub, copy your fork's clone URL, then:

```sh
git clone YOUR_FORK_URL paper-evolve
cd paper-evolve
python paper_evolve.py list
python paper_evolve.py start --pack PACK_ID --name "Your name" \
  --tool "Actual Claude Code or Codex / model version"
```

Choose an actual pack ID from `list`. Open the cloned folder in Claude Code or
Codex and give your agent the generated workspace's `PROMPT.md`. It has the paper
pairs, source passages, relationship rules and submission template. Root
`AGENTS.md` and `CLAUDE.md` explain the workflow. Validation and PR preparation
need only Python 3.10+; agents use their own account and PDF research tools.

Agents can actively research full papers, not just classify prepared snippets.
Use `fetch` to download/title-check PDFs and extract page-marked text, then
`cite` to attach newly found evidence with URL, page and document fingerprint.
PDF extraction needs an existing Poppler/pdftotext or pypdf installation;
validation stays standard-library-only. See [RESEARCH.md](community/RESEARCH.md).

Then prepare your pull request:

```sh
python paper_evolve.py check --workspace work/contributions/PACK_ID
python paper_evolve.py pr --workspace work/contributions/PACK_ID
```

The second command exports a validated JSON into `community/submissions/` and
writes `GIT_STEPS.md` and `PULL_REQUEST.md` in your ignored workspace. Follow the
generated steps to commit only that submission, push to your fork and open a
pull request. The tool itself does not push or publish anything.

**Prefer your own API?** Start with `--method api` and follow
[the API guide](community/API.md). Select your own compatible endpoint, model,
token prices, credentials and cumulative workspace budget. This uses the same
tasks, evidence requirements and submission format as agents.

**Prefer a download?** The contribution page offers portable kits containing
one topic pack and the same tools. Copy the exported JSON into your fork when
ready to submit.

**One command.** With the `claude` or `codex` command line tool signed in,
`python paper_evolve.py run --pack PACK_ID --name "Your name" --agent claude`
prepares the workspace, has your agent review each pair, validates the result
and prints the Git steps.

**Your own pair.** Any two papers in the collection can be connected:
`python paper_evolve.py run --earlier "Earlier paper" --later "Later paper"
--name "Your name"`. The contribution page builds this command for you.

**New papers and venues.** The collection itself is open: add papers, or a
whole conference, with `python paper_evolve.py add-venue` and `add-papers`.
See [the papers guide](community/PAPERS.md).

See [the clone guide](community/CLONE.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
There are 46 organized topic packs with 10 source-ready tasks each, and every
other pair in the collection is open to propose. Finding that two papers are
unrelated is a welcome contribution too.

## Repository map

| Path | What it holds |
|---|---|
| `index.html`, `contribute.html`, `evolve/` | The static site: pages, scripts, styles and the published data (`evolve/corpus.json`, `evolve/generated/`). |
| `community/` | Everything contributors touch: task packs, submissions, accepted reviews, paper additions, the venue registry and the guides. |
| `paper_evolve.py`, `scripts/contribut*.py`, `scripts/community_edges.py` | The contributor tool and its validators. Standard library only. |
| `scripts/` (the rest) | Maintainer preparation: abstracts, embeddings, citation data and model-reviewed connections. Needs the private `work/` caches. |
| `build_evolve.py`, `scripts/ui_assets.py` | Packages the site into `dist/`; run by the Pages workflow. |
| `tests/` | Unit tests for the tools, validators and front-end logic. |
| `paper_atlas/`, `config/`, `remote_jobs/` | The ingestion adapters, per-venue settings and GPU jobs that built the original collection and its topics. |
| `docs/` | Decision logs, reproduction notes, review notes and screenshots. |
| `legacy/` | The earlier single-page Paper Atlas and its builders, kept for reference. |

## How contributions reach the map

1. Contributors investigate prepared paper pairs and submit quoted evidence.
2. Pull-request CI checks identities, frozen fingerprints, quotes, types and
   duplicate task versions.
3. A maintainer separately checks the interpretation and records acceptance.
4. Merging accepted records triggers the Pages build and updates the public graph.

Accepted connections carry the contributor's name and the reviewer's note.
Pages serves the app and task catalog; GitHub pull requests receive the
contributions. Open tasks refresh with each site build, and a fresh clone also
reads committed submissions, so a look at current PRs shows what is in progress.

## Run the app locally

```sh
python build_evolve.py
python -m http.server 8765 --directory dist
```

Open `http://localhost:8765/`. The build uses committed public artifacts and
produces `dist/`, including portable contributor kits. It does not call a model
or require API keys. The ignored `work/` directory holds private preparation
caches, temporary agent workspaces and local API ledgers.

## Publish on GitHub Pages

Use the repository's GitHub Actions Pages workflow. Push the complete project
to the Paper Evolve repository and select GitHub Actions as the Pages source.
The workflow tests, validates, builds and deploys `dist/`. It supplies the actual
repository identity for Fork/PR links. Custom hosting can set
`community/project.json` to `{"repository":"OWNER/REPO"}` or use
`PAPER_EVOLVE_REPOSITORY=OWNER/REPO` at build time. Do not put a key there.

Repository links are not derived from the starter project's inherited Git remote.
Deployment and repository administration are separate from preparing the local
app; no workflow publishes from a contributor's local workspace automatically.

## Development and evidence rules

Run `python -m unittest discover -s tests` and
`python scripts/community_edges.py check` before proposing changes.
[EVOLVE.md](EVOLVE.md) describes the app and preparation pipeline;
[decision logs](docs/decisions/) explain model, evidence and architecture choices.
Historical ingestion and clustering experiments remain in `paper_atlas/`,
`remote_jobs/`, `docs/` and `legacy/`. Contributors never need to run them.

## License

Code is [MIT licensed](LICENSE); retain its copyright notices. Bundled fonts
have SIL Open Font Licenses in `fonts/`, and bundled libraries retain their
licenses. Paper metadata and source excerpts remain attributable to their
original authors and publishers.
