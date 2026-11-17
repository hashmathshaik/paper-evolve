# 016: Topic packs shared by API and agent contributors

Date: 2026-11-16
Status: implemented locally; public repository publication remains separate

## Context

The paid seed contains 3,733 relationships. The user wants a sustainable system
where people contribute using either their own API allowance or their existing
Claude Code/Codex agents. The user deleted the maintainer's local Qwen keys and
paused the seed jobs. Building the contribution workflow must not restart them.

## Decision

Use frozen topic packs as the common input and the existing evidence-reviewed
submission schema as the common output. A standard-library CLI prepares a local
workspace with pack fingerprints, selected tasks, prompt, agent instructions,
schema and submission template. It validates and exports files for pull requests;
it never accepts or publishes a contribution. Claude Code and Codex read the
same workspace prompt. No vendor SDK, agent automation service or credentials
are needed for this route.

The separate opt-in API command supports the OpenAI-compatible chat-completions
protocol. Contributors provide their own endpoint, model, current token rates,
key environment variable and cumulative workspace budget. A local SQLite ledger
reserves conservative input-byte/output-token allowances before requests, records
reported usage including invalid outputs, and retains uncertain holds. Uncertain
and rejected requests are not automatically resent. A workspace fixes its model,
endpoint, rates, prompt and evidence version. The project seed ledger and keys are
never loaded. Input/output prices are contributor supplied; actual provider
billing remains authoritative. API predictions still require separate acceptance.

The initial release adds 46 topic packs with 10 source-ready tasks each. New
citation passages were prepared only from cached PDFs; no model requests or
network source downloads were needed. Tasks are assigned by the later paper's
topic, preserving cross-topic contribution links. The legacy starter pack stays
available through the CLI, while the browser highlights the organized topic packs.
Source readiness means prepared citation evidence exists, not that a true edge
has been established. Agents and APIs may abstain.

The static catalog tracks available task versions using committed submissions
and acceptance records. It is a build-time snapshot, not a live claim service.
Distinct evidence revisions can coexist, but duplicate snapshots fail validation.
Maintainers reconcile duplicate accepted pairs explicitly. Public ZIP kits are
deterministic, contain only a whitelist of portable code/instructions and one
pack, and are regenerated during Pages builds without private caches or keys.

## Alternatives and limits

A shared MCP server would require deployment, authentication and live coordination.
The file/CLI interface works with either agent immediately and keeps Pages static.
A later MCP adapter can wrap the same task and submission operations. The API
runner currently targets the compatible chat-completions protocol; provider-native
protocols are separate adapters. Real paid API integration was not exercised
because the user removed credentials; tests use injected provider responses.

Concurrent contributors can choose the same public pack. The site makes the
snapshot explicit; contributors coordinate through pull requests and CI rejects
duplicate submissions of a task version. A live claim queue can be added when a
backend exists. Format/quote checks do not determine scientific correctness or
authenticate a reviewer. Maintainer merge approval and repository branch
protection remain necessary on the eventual public repository.

## Validation

Exercise agent workspace creation, fingerprint tampering, fabricated quotes,
separate acceptance, portable exported submissions and an extracted ZIP operating
without the repository/caches. Test API reservations, cumulative resume behavior,
uncertain holds, missing usage, rejected requests, truncated output, source gating,
configuration changes and crash recovery. Check desktop/mobile topic selection,
both route controls, contextual navigation and kit downloads in the local app.
