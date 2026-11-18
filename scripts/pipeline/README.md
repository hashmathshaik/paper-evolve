# Maintainer pipeline

These jobs prepared the published collection. They need the private `work/`
caches, and some need API keys or extra packages, so contributors never run
them. Everything the contributor tool and the site build import lives one level
up in `scripts/`; nothing there imports from this folder.

Run them from the repository root, for example
`python scripts/pipeline/audit_corpus.py`.

| Stage | Scripts |
|---|---|
| Abstracts | `fetch_abstracts`, `download_collection`, `recover_openalex`, `recover_s2`, `recover_mirrors`, `recover_more`, `recover_acl_pdf`, `audit_corpus` |
| Embeddings and neighbours | `embed_downloaded`, `embedding_queue`, `edges_knn`, `run_pipeline` |
| Citation data | `citations_s2`, `citations_openalex`, `contexts_s2` |
| Model-reviewed connections | `seed_edges`, `qwen_relations`, `qwen_batches`, `qwen_grouped_edges`, `free_quota_edges`, `prepare_evidence_queue`, `edge_pipeline`, `sample_relation_review` |
| Budget and ledgers | `project_budget`, `migrate_relation_ledger` |
| Publishing | `export_edges`, `edge_publication` |
