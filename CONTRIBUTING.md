# Contributing to Paper Evolve

There are three ways to help. Each starts from a fork of this repository and
ends in a pull request.

| I want to… | Start here |
|---|---|
| Connect two papers | [Add a connection](#add-a-connection) |
| Add papers or a conference | [Add papers](#add-papers-or-a-venue) |
| Change the site or the tools | [Improve the code](#improve-the-code) |

You need Python 3.10+ and nothing else installed. No API key is required unless
you choose the API route.

## Add a connection

```sh
git clone YOUR_FORK_URL paper-evolve
cd paper-evolve
python paper_evolve.py list
python paper_evolve.py run --pack PACK_ID --name "Your name" --agent claude
```

`run` prepares a workspace, has Claude Code or Codex read both papers of each
pair, validates every quote, and prints the Git commands for your pull request.
It never commits or pushes. Use `--agent codex` for Codex.

To connect two papers of your own choice:

```sh
python paper_evolve.py find "words from a title"
python paper_evolve.py run --earlier "Earlier paper" --later "Later paper" --name "Your name"
```

Other routes use the same packs and produce the same submission:

| Route | Commands | Guide |
|---|---|---|
| Your own API key | `start --method api`, then `api` | [API guide](community/API.md) |
| Step by step, or reading yourself | `start`, fill in `submission.json`, `check`, `pr` | [Clone guide](community/CLONE.md) |
| Without cloning | Download a kit from the [contribution page](https://hashmathshaik.github.io/paper-evolve/contribute.html) | Kit `README.md` |

### What a connection needs

- One or more of **Extends, Challenges, Combines, Transfers, Revives**.
- What the later paper **inherited** and what it **changed**.
- Exact quotes from **both** papers, including the passage where the later one
  cites the earlier one. Your agent can download the papers and register
  quotes with `fetch` and `cite`; see [the research guide](community/RESEARCH.md).
- If the papers turn out to be unrelated, say so with a reason. That is a
  useful contribution too.

Commit only your exported submission (plus its `proposal-…` pack if you chose
the pair yourself). A maintainer reads the sources before accepting, and
accepted connections appear on the site with your name.

## Add papers or a venue

```sh
python paper_evolve.py add-venue --id cvpr --name CVPR --host openaccess.thecvf.com
python paper_evolve.py add-papers --file my-papers.json --name "Your name" --tool "Your agent / model"
```

The record format and a ready prompt for your agent are in
[the papers guide](community/PAPERS.md).

## Improve the code

```sh
python -m unittest discover -s tests       # all tests
python scripts/community_edges.py check    # what pull-request CI validates
python build_evolve.py                     # build the site into dist/
python -m http.server 8765 --directory dist
```

- The repository map at the end of the [README](README.md) says what lives where.
- Site scripts in `evolve/` are formatted with Prettier:
  `npx prettier@3 --write "evolve/*.js"`, then `python build_evolve.py` to refresh
  the asset version stamps.
- The contributor tool in `scripts/` uses the Python standard library only. Keep
  it that way so a fresh clone works without installing anything.
- Non-trivial choices are recorded in [`docs/decisions/`](docs/decisions/). Read
  the relevant one before changing that area, and add an entry when you make
  such a choice yourself.

### A good pull request

- Does one thing. If you spot something else broken, mention it instead of
  fixing it in the same change.
- Passes the tests and the `check` command.
- Includes before and after numbers when it changes a method, not only the UI
  or tooling.

## Maintainers

Accepting connections, applying added papers, issuing new task packs and the
preparation pipeline are covered in [docs/MAINTAINING.md](docs/MAINTAINING.md).
