# 014: Paper Evolve static contribution graph

Context: extend the existing atlas into a source-linked history of contributions, with an explicit user request for a full UI redesign and automatic connections.

Options: replace the map and ML pipeline; add a new framework/backend; retain the shipped static corpus and add a dependency-free workspace.

Chosen: preserve the original map as atlas.html and browse/table tools; introduce a static JSON research slice with separate paper/contribution/relationship records. Use native SVG plus HTML controls. No new runtime dependencies. This follows the upstream two-layer storage and identity rationale without changing embedding/clustering methodology.

Connections: curated, source-backed evolution edges are separate from computed lexical similarity (TF-IDF/cosine). The latter is a local reproducible baseline, not a claim of influence or a neural semantic model. Ship seven sourced papers instead of invented quota-filling relationships. No fixture records. Explicit/inferred statuses remain visible.

Revisit: larger collections warrant neural embeddings and reviewed candidate edges, dynamic graph layout, canonical version reconciliation, and alphaXiv retrieval. Keep paid credentials optional. The user's autonomous implementation request supersedes upstream teaching-only discussion gates for this adaptation.
