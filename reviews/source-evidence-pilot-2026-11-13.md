# Source-evidence pilot — 2026-11-13

This is a development regression check, not held-out validation or independent expert review.

Eight previously audited difficult pairs were selected. Official PDFs were retrieved and checked against corpus titles. Two pairs produced packets with both papers and candidate citation paragraphs. Five pairs had a blocked OpenReview source, and one earlier paper had a different PDF title from the corpus. The title mismatch was left pending rather than automatically accepted as the same version. No challenge page was bypassed.

Haiku reviewed the two ready packets using exact-source quotation constraints and the existing shared $5 ledger:

- **SparseMAP → LP-SparseMAP (R06):** Extends accepted. I inspected the returned source quotations. The later paper explicitly introduces a relaxation of SparseMAP's exact-oracle requirement; the predicted inheritance/change is supported.
- **Oko et al. → Beyond Density Lower Bound Assumptions (R30):** withheld. Haiku proposed Challenges at 0.8, below the publication threshold. The retrieved evidence supports a generalization rather than a demonstrated invalidity of the earlier theorem. This remains a model error/missed relationship and is queued for a stronger review; it was not force-accepted.

The two calls cost approximately $0.0016 combined at actual reported usage. Remaining retrieval failures are explicit `needs_context` cases. This tiny, selected pilot cannot measure model accuracy or predict whole-corpus source coverage. Prompt wording was clarified after the R30 failure; that clarification has not been evaluated on new held-out cases.

Publication/UI changes:

- Passage-supported predictions are the default filter for computed neighborhoods.
- Older abstract-only predictions are retained under All predictions and explicitly labeled.
- Quote provenance includes the PDF URL, page number, and document SHA-256.
- Invalid quotes, missing source packets, stale abstract fingerprints, blocked sources, and missing Jev gates do not pass the source-backed review queue.
- Similarity remains a separate discovery layer. A source quotation's existence is not proof that its relationship label is correct.

The retrieval heuristic produces candidate passages, not guaranteed method sections. It uses resolved numeric citations, available Semantic Scholar citing sentences, and exact named methods. A reviewer still needs to check whether each selected passage identifies the particular earlier contribution. Broader deployment needs verified alternate sources for blocked papers and a fresh held-out evaluation set.
