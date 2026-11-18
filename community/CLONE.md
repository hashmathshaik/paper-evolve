# Contribute from a repository clone

The GitHub Pages site serves the app and prepared paper packs. Contributions
arrive through GitHub pull requests. Both the agent and API routes work directly
from a clone; downloading a kit is optional.

## Fork and clone

Open the Paper Evolve repository linked on the contribution page and fork it
into your GitHub account. Copy your fork's clone URL, then run:

```sh
git clone YOUR_FORK_URL paper-evolve
cd paper-evolve
python paper_evolve.py list
python paper_evolve.py start --pack PACK_ID --name "Your name" \
  --tool "Actual Claude Code or Codex / model version"
```

Replace the placeholders with your fork URL, selected pack ID and contributor
details. Python 3.10+ is enough. No embedding downloads, private caches, package
installation or API key are needed for agent contributions. `origin` should
point to your fork. Use your existing agent account.

Open the cloned repository in Claude Code or Codex and give it this prompt:

> Read AGENTS.md and community/CLONE.md. Work on pack PACK_ID using the prepared
> workspace's PROMPT.md. Fill submission.json using exact source quotes; abstain
> when full-paper research still leaves insufficient evidence. Use fetch/cite
> from community/RESEARCH.md to download papers and attach new page excerpts.
> Run the check and prepare a pull request with
> `python paper_evolve.py pr --workspace work/contributions/PACK_ID`. Keep the
> frozen tasks unchanged. Do not approve your output, run API requests, push or
> open a pull request without my instruction.

For API inference, start with `--method api --tool "Your API model"` and follow
[API.md](API.md). The same clone, task packs and submission workflow apply.

## One command with Claude Code or Codex

If the `claude` or `codex` command line tool is installed and signed in, `run`
does the steps above for you: it prepares the workspace, has the agent review
each pair, validates the result and exports the submission.

```sh
python paper_evolve.py run --pack PACK_ID --name "Your name" --agent claude
python paper_evolve.py run --count 3 --topic "reinforcement" --name "Your name" --agent codex
```

`--pack` can be repeated; `--count N` takes the next N packs that still have open
tasks. Rerun the same command to resume after an interruption. The agent uses
your own account; no API key is read. It works inside the ignored workspace and
may only edit files there and run this tool's `fetch`, `cite` and `check`
commands (Claude Code by an allow-list, Codex by its workspace sandbox with
network access for paper downloads). `run` never commits, pushes or opens a
pull request: it prints the Git commands for you to run. Add `--model NAME` to
choose the agent's model, or `--agent-command 'tool {prompt}'` for another
agent CLI.

## Choose your own pair

To propose a connection that is not in a prepared pack, pick any two papers in
the collection. The earlier paper must come from an earlier year.

```sh
python paper_evolve.py find "words from the title"
python paper_evolve.py propose --earlier "Earlier paper title, URL or ID" \
  --later "Later paper title, URL or ID"
python paper_evolve.py run --earlier "..." --later "..." --name "Your name"
```

`propose` writes a one-task pack to `community/tasks/proposal-….json`, built only
from the public corpus record and abstracts. It has no prepared passages, so a
positive connection needs excerpts you register from both full papers with
`fetch` and `cite`. Commit that pack together with your submission; the `pr` and
`run` commands stage both. Validation rebuilds the pack from the corpus and
rejects it if any title, year, abstract or source URL was changed.

To pick particular pairs from a prepared pack instead, list them and name the
ones you want:

```sh
python paper_evolve.py list --pack PACK_ID
python paper_evolve.py start --pack PACK_ID --task TASK_ID --name "Your name" \
  --tool "Actual agent / model version"
```

## Validate and prepare your pull request

```sh
python paper_evolve.py check --workspace work/contributions/PACK_ID
python paper_evolve.py pr --workspace work/contributions/PACK_ID
```

The `pr` command exports one validated JSON file into `community/submissions/`
and writes `GIT_STEPS.md` and `PULL_REQUEST.md` inside the ignored workspace.
It prints an exact branch name and commands that stage only that submission.
It does not switch branches, commit, push, contact GitHub, or open a pull request.
Run the generated Git steps when you are ready, then open a pull request from
your fork to Paper Evolve using the prepared description.

Only commit the submission JSON, plus the `proposal-…` pack when you proposed
the pair yourself. `work/`, `.env` and API ledgers remain local.
Each task has a fixed identity and initial evidence fingerprint. Additional
research excerpts attach separately with document/page provenance; see
[RESEARCH.md](RESEARCH.md). After updating your
clone, the CLI reads committed submissions and approvals so an older catalog
cannot offer tasks that have already been submitted. Unmerged work is not a
live reservation; check current pull requests before choosing a pack.

## What happens on GitHub

Pull-request CI validates the submission, exact quotes, identities and duplicate
task versions. A maintainer checks the interpretation and separately records
acceptance. A submission merge alone does not accept its edges. Once an
acceptance is merged, the Pages workflow rebuilds the static graph and updates
the public contribution catalog. No browser upload endpoint or always-on
backend is required. You can also export a submission and upload that JSON
through GitHub in your fork before opening a pull request.

## Publishing this project's links

The Pages workflow supplies its repository identity at build time. Custom
hosting can set `community/project.json` to `{"repository":"OWNER/REPO"}` or
set `PAPER_EVOLVE_REPOSITORY=OWNER/REPO` for the build. Never put credentials
there. Repository links are not inferred from an inherited Git remote.
