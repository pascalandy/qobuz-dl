# Vision: Stale Local Capability Research Doc

Mode: `pa-vision` / AlignmentDraft
Severity: Low
Status: proved

## Request Or Decision

Decide whether to refresh or clearly archive the existing local capability research artifact so it does not mislead future planning.

## Current State

`docs/research/local-project-capabilities.md` says it was a read-only exploration on 2026-05-26 (`docs/research/local-project-capabilities.md:3`). It now contains stale facts. It says `pyproject.toml` declares version `0.9.9.10` (`docs/research/local-project-capabilities.md:7`), but current `pyproject.toml` declares version `1.0.0` (`pyproject.toml:7-12`). It also says blank lines are not filtered from local text files (`docs/research/local-project-capabilities.md:59`), while current `download_from_txt_file()` filters blank lines and comment lines (`qobuz_dl/core.py:341-345`).

This is not a production-code issue. It is a planning/docs quality issue: a future agent or maintainer could use stale research as current-state truth.

## Observed Constraints

- The file is under `docs/research/`, so it may intentionally capture a point-in-time exploration.
- Updating it could blur historical context unless the artifact is marked as refreshed.
- The user asked not to code anything yet, so this audit logs the issue rather than editing the doc.

## Desired End State

The research artifact should either be refreshed to current code or clearly marked as historical/stale with links to the current audit.

## Proposed Interaction Or Behavior

- Add a note at the top that the artifact is historical and superseded by this audit, or refresh it with current version and behavior.
- If refreshed, keep the date and current evidence exact.
- Link from the audit to any future updated research doc.

## Design Decisions

- Do not silently treat historical research as canonical.
- Keep docs updates separate from audit artifact creation.
- Use `pa-doc-update` if this doc is changed later.

## Patterns To Follow

- Date and scope research artifacts clearly.
- Avoid stale line references in reusable docs.
- Prefer a short supersession notice over a broad rewrite if the artifact is historical.

## Patterns To Avoid

- Do not delete historical research without confirming whether it is intentionally archived.
- Do not update docs opportunistically during a no-code audit unless the user approves.
- Do not use stale research as evidence for current behavior.

## Success Signals

- Future readers can tell whether the research file is historical or current.
- Version and text-file ingestion statements match current code if the doc remains current.
- The docs index points to the right canonical current-state source.

## Open Questions And Risks

- The maintainer may prefer preserving dated research unchanged. If so, a supersession banner is safer than editing contents.

## What Needs Human Review

Decide whether `docs/research/local-project-capabilities.md` should be refreshed, archived, or superseded by this audit directory.

## Recommended Next Phase

`pa-doc-update` only if the maintainer wants the existing docs changed.
