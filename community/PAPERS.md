# Add papers and venues

The collection grows through pull requests, the same way connections do. You
can add single papers, a batch, or a whole new conference. An agent such as
Claude Code or Codex can gather the records for you.

## What a paper record needs

Write a JSON list, one object per paper:

```json
[
  {
    "title": "Exact published title",
    "year": 2025,
    "venue": "cvpr",
    "url": "https://openaccess.thecvf.com/content/CVPR2025/html/Example_CVPR_2025_paper.html",
    "abstract": "The full abstract, copied from the official page.",
    "topic": "3D Scene Reconstruction and Representation with Neural Methods"
  }
]
```

- `url` is the paper's public page on the venue's official host.
- `abstract` is the published abstract in full, not a summary.
- `topic` is optional. `python paper_evolve.py topics` lists the choices; leave
  it out and the paper is filed as uncategorized.
- `abstract_source_url` and `retrieved_at` are optional. They default to `url`
  and the current time.

## Add them

```sh
python paper_evolve.py add-papers --file my-papers.json --name "Your name" \
  --tool "Actual agent / model version"
```

The command checks every record, refuses papers already in the collection, and
writes one file under `community/papers/`. It prints the Git commands for a
branch and commit. It never pushes.

## Add a new venue first

If the conference or journal is new to the collection, register it once:

```sh
python paper_evolve.py add-venue --id cvpr --name CVPR --host openaccess.thecvf.com
```

`--host` is the official site that serves its paper pages; repeat it when there
are several. The venue is added to `community/venues.json`, the single place
venues are declared. Commit that file together with your papers.

## Ask an agent to do it

Give Claude Code or Codex a prompt like this from your clone:

> Read AGENTS.md and community/PAPERS.md. Collect the accepted papers of
> VENUE YEAR from its official proceedings site: exact title, year, public paper
> page URL and the full published abstract. Register the venue if it is missing.
> Choose a topic for each paper from `python paper_evolve.py topics` when one
> clearly fits. Write them to a JSON list and run add-papers with my name and
> your actual model version. Use only official pages, copy abstracts exactly,
> and do not push or open a pull request without my instruction.

## What happens next

Pull-request CI validates the file. A maintainer reviews it and runs
`python scripts/contribution_papers.py apply`, which appends the papers to the
published collection and moves your file to `community/papers/applied/` as the
record of who added them. After the next site build the papers appear in
Browse, Landscape and search. They start without connections, so they are open
for anyone to connect with `propose` or `run --earlier … --later …`.
