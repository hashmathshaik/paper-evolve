# Legacy: the original Paper Atlas

These files built the first version of this project, a single-page map of the
paper collection. They are kept for reference and reproducibility; the live
site (`index.html`, `contribute.html`, `evolve/`) does not use them.

- `build_*.py`, `nav.py`: generators for the old map, table, analytics and blog pages.
- `*.html`: their generated output. `atlas.html` still holds the 2D map coordinates.
- `noise_baseline.py`, `vocab_coherence.py`, `cross_venue_analysis.py`,
  `report_cell_sizes.py`, `embed_specter2.py`, `spike_map.py`: clustering experiments.
- `future_work.md`: notes from that stage.

The scripts expect the ignored `data/` directory and import `paper_atlas` from
the repository root, so run them from the root with `PYTHONPATH=.`, for example
`PYTHONPATH=. uv run python legacy/build_frontend.py`.
