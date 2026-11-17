# 017: Repository clones as a first-class contribution path

Date: 2026-11-16
Status: implemented locally

## Context

The user wants contributors to clone the repository, use their existing agent
or API route, and submit work through GitHub while the app remains on Pages.
The local Git remote still points to the upstream starter project; deriving
public contribution destinations from that remote would direct users wrongly.

## Decision

Expose repository/fork links and clone instructions alongside downloadable
kits. Public repository identity comes from explicit `community/project.json`
configuration or the Pages build's GitHub repository environment, never a Git
remote. A browser fallback can identify ordinary github.io project/user sites.
Local previews with no configured repository show a publication placeholder.

Root AGENTS.md/CLAUDE.md guide cloned-repository agents into frozen workspaces.
The standard-library `pr` command validates and exports a single submission,
generates a safe branch name and narrowly scoped Git commands, and writes a
PR description. It never executes Git operations or contacts GitHub. Contributors
choose when to push and create the pull request. The Pages workflow supplies
its own repository identity automatically.

A cloned CLI checks committed submissions/acceptances before listing or
offering tasks, even when the committed catalog predates the latest PR. Live
claims remain outside scope; contributors coordinate unmerged work through PRs.
The existing acceptance gate remains separate: a submission merge updates
availability, while a merged acceptance publishes graph changes.

## Validation

Test the workflow in a fresh local Git clone with no private corpus or API key;
prepare a task, validate/export it and inspect the generated PR/Git plan. Check
stale catalog handling, safe output paths/quoting, configured and CI repository
links, github.io fallback and local previews with no repository. Run the static
build and existing contribution/API tests. No remote push or paid request is
needed to verify this path.
