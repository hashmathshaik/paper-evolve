# 018: A fresh-agent trial of the contributor workflow

Date: 2026-11-16
Status: completed; submissions await maintainer acceptance

## Setup

At the user's request, a fresh agent with no conversation history worked in a
local Git clone of a public-only snapshot of the current project. It received
the repository path, a contributor name, the documented workflow and instructions
to assess 20 pairs across two topic packs. The clone had no private `.env`, source
cache or paid inference ledger. No API calls, package installation, source-network
requests, remote push or acceptance operation were needed.

The agent chose the attention/context and graph-neural-network packs, 10 tasks
each. It prepared workspaces, read the frozen sources, validated its decisions,
exported submission JSON and generated local PR descriptions/Git steps. Tracked
files and frozen packs in its clone were unchanged. Its actual model version was
not exposed, which is declared explicitly in the contributor metadata.

## Findings

The first pass returned 20 abstentions. A separate parent-assistant source audit
found that two reasons applied too narrow a meaning of Challenges: they required
refuting a result/theorem rather than allowing a diagnosed method limitation.
The agent re-examined those two packets without changing evidence or validators.

The final submissions contain **2 Challenges proposals and 18 abstentions**:

- DUQ → uncertainty estimation on heterophilic graphs: B explicitly includes A
  among training-time distance-preservation methods and criticizes restrictions
  that prevent post-hoc estimation; B supplies a joint-embedding post-hoc estimator.
- Universal invariant/equivariant GNNs → a loopy WL hierarchy: B cites A while
  diagnosing exponential complexity of the higher-order route and presents a
  scalable alternative. This does not assert that A's universality theorem is
  false or that B preserves the same guarantee.

The DUQ proposal was further checked to include the diagnostic limitation quote,
not merely a generic information-loss statement. Other decisions remained
unchanged. Many abstentions correctly distinguish shared motivation, grouped
background citations, competing algorithms and related theorem families from
specific contribution links.

## Changes

Clarify the shared prompt: Challenges may diagnose and address an A-specific
method limitation without theorem refutation. Generic family-level criticism and
a faster baseline score remain insufficient. The two validated files are saved
in `community/submissions/`; no approvals were added and the published edge count
remains unchanged. First-pass outputs and a machine-readable assistant audit are
retained in the ignored local trial directory for reproducibility.

## Limits

This was an assistant contribution followed by assistant review, not human
verification or a measured accuracy benchmark. The 20 self-selected pairs do not
estimate full-corpus precision or recall. Maintainer source review is still
required before acceptance. An incidental unused workspace came from selecting
a valid global pack outside a filtered listing; that is expected behavior, not
a tooling defect, and it was not submitted.
