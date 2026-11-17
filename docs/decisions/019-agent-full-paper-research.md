# 019: Let contributor agents research full papers and attach new evidence

Date: 2026-11-16
Status: implemented; supersedes the prepared-excerpts-only agent restriction

## Context

After the fresh-agent trial, the user clarified that contributors should actively
download/read papers and investigate references rather than remain limited to
prepared excerpts. The old prompt required abstention or a maintainer-refreshed
task when evidence lay outside the snapshot. That prevented useful source work.

## Decision

Keep original task identities and initial fingerprints fixed, but allow additive
`source_material` on a submitted task decision. The `fetch` command retrieves
official public PDFs, verifies title matches, fingerprints the bytes and extracts
page-marked text into the ignored workspace. It also accepts an official alternate
URL or an explicitly imported PDF with its public source URL. Cached files are
checked before reuse. Extraction uses reading order rather than layout mode to
reduce two-column text interleaving; figures/equations still require PDF inspection.

The `cite` command re-extracts the downloaded PDF and verifies an exact excerpt
on the selected physical PDF page before attaching it. New source IDs are separate
from prepared IDs, so the original evidence cannot be silently overwritten.
Attachments include paper identity, URL, page, PDF hash, excerpt hash and retrieval/
extraction metadata. Full PDFs and full text stay local; compact excerpts travel
with the JSON contribution. Existing submission files remain compatible.

Both agent and API routes validate the augmented source state. API requests include
new source IDs and fix the research snapshots in their workspace ledger; completed
results recover their attachments after interruption. Altering evidence after a
paid attempt requires a new API workspace. No model API or project credentials are
needed for PDF research. Public-source downloads are permitted on the agent route.

## Trust and limits

Official-host HTTPS URLs and redirects are checked before retrieval, credentials
and private destinations are rejected, and access-control failures are reported
without bypasses. Alternate-source title matching is useful but does not fully
verify authors, paper versions or scientific interpretation.

CI remains offline and standard-library-only. It validates attachment structure,
fingerprints, source identity and quotations against submitted source snapshots;
it cannot prove a contributor-supplied excerpt was actually in a published PDF.
Maintainers must verify the public URL/page/document before acceptance. Evidence
is explicitly labeled contributor-retrieved, and assistant checks are not marked
human verified. Full-paper reading still does not justify a forced relationship.

## Validation

Test additive positive submissions, unchanged task fingerprints, fabricated/wrong-
page quotes, tampered documents, unsupported redirects, incorrect paper identities,
incomplete source coverage, and researched API input/recovery. Exercise real PDF
downloads/extraction and inspect rendered pages. A research-enabled follow-up agent
reads the complete downloaded pair and registers new diagnostic page excerpts.
