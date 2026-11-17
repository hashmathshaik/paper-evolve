# 015: A budgeted seed pool and portable community evidence reviews

Date: 2026-11-14
Status: implemented; seed inference is resumable

## Context

The corpus contains 70,861 papers. Reviewing every candidate pair with the
existing prompt exceeds the remaining project allowance. The user chose a $30
edge-generation ceiling and asked to grow coverage through open-source review.
The latest provider instruction is Qwen only. Similarity must remain separate
from the five contribution labels.

## Decision

Use Singapore Qwen3.7-Flash proposals and blind Qwen3.7-Plus review of positives.
Reuse cached Jev rankings without new screening requests. Prioritize known
citations, available source documents and citing paragraphs; interleave later
papers so popular hubs do not consume the entire seed budget. These ranking
features are heuristics, not evidence of a relationship or scientific importance.
Fetch source packets before inference. Publish a new positive only if both Qwen
models agree on the type and the reviewer supplies explicit contribution evidence
from the earlier paper and a later citing passage. Abstain on missing sources.
The first source audit found shared-problem and hypothetical-combination errors,
so unverified positive proposals are excluded from public shards.

The $30 edge ceiling is cumulative, counting earlier edge costs/reservations.
It is persisted in SQLite and enforced across connections in addition to the
existing $50 whole-project ceiling, historical preparation and contingency.
The bounded pilot has a further $0.05 allowance. Ambiguous paid outcomes keep a
reservation and are not automatically resent. Provider/account errors stop the
worker. Isolated invalid outputs are quarantined; three consecutive invalid
outputs stop admission. Finishing below the ceiling is acceptable when evidence runs out.

Community contributors receive frozen task packs with paper identities, sources,
abstracts, available passages and content fingerprints. They can use their own
assistant account, local model or manual reading. Standard-library Python
validation checks chronology, identities, duplicates, exact quotes, type names
and evidence coverage without an API or private corpus. A maintainer separately
accepts a review, recording the original submission, source snapshot, contributor,
tool and reviewer. Assistant review never becomes a human-verification badge.
The eventual repository must require maintainer approval; a JSON reviewer field
is an audit record, not a cryptographic assertion of identity or expertise.

Accepted reviews form a static overlay, overriding the corresponding paid
prediction, including withdrawing it after an accepted abstention. This keeps
GitHub Pages builds independent of private SQLite caches and makes removing an
approval reversible without deleting the original model result. Normal task
exports skip already issued pairs; explicit pair export supports corrections.

## Alternatives and limits

Labeling all pairs cheaply would maximize counts but retain the errors observed
in the pilot. A second model is used only for positive proposals to concentrate
cost on the proposed seed. Model agreement can share errors and is not a quality
benchmark. The priority order does not guarantee domain balance or complete
recall. Papers with unavailable sources and unsupported links remain open tasks;
not every paper should have a forced evolution edge.

## Revisit when

Use an independently labeled, held-out evaluation set to measure precision and
abstention by relation type. Revisit retrieval coverage and ranking as citation
contexts improve, and add more public task packs as contributors finish them.
Only change the provider or spending ceilings when the user requests it.

## Parallel execution, 2026-11-15

The initial seed worker serialized API calls and waited for ordered batches of
PDF retrieval. Its observed pace was roughly 150–170 source candidates per hour.
The user requested faster completion. The pipeline now admits up to 32 model
jobs while a separate pool retrieves sources. Ready packets are consumed as
they finish. Each model thread has its own ledger connection, with immediate
transactions preserving the global cap and exclusive pair claims. Queue sizes
are bounded. Admission stops on user pause, budget exhaustion or provider errors;
already admitted calls are drained and accounted for. A coordinator handles
progress and static publication. Models, prompts and the evidence/type-agreement
gate are unchanged. Tests cover overlapping full two-model reviews, duplicate
claims, a slow first source, shared-budget exhaustion with unknown outcomes, and
draining on pause. Actual service throughput remains subject to provider limits.
