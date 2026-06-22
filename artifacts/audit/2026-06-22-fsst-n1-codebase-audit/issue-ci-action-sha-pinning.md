# Vision: CI Action SHA Pinning

Mode: `pa-vision` / AlignmentDraft
Severity: Low
Status: weak

## Request Or Decision

Decide whether the normal CI workflow should match the release workflow's stronger action-pinning standard.

## Current State

The release workflow pins third-party actions to full commit SHAs for checkout, setup-uv, upload-artifact, and download-artifact (`.github/workflows/release.yml:24-28`, `.github/workflows/release.yml:53-71`). The normal CI workflow uses moving major-version tags: `actions/checkout@v4`, `astral-sh/setup-uv@v5`, and `actions/upload-artifact@v4` (`.github/workflows/ci.yml:28-32`, `.github/workflows/ci.yml:67-69`).

The CI workflow does set `permissions: contents: read` (`.github/workflows/ci.yml:10-11`), which reduces token blast radius. GitHub's secure-use docs say full-length SHA pinning is the only immutable way to use an action reference. GitHub's token docs recommend least-required permissions; this repo already follows that for CI.

## Observed Constraints

- SHA pins increase maintenance overhead because updates require changing hashes.
- CI does not publish releases and uses read-only contents permissions.
- Release workflow is already stronger because it writes releases.

## Desired End State

Either normal CI uses full-length SHA pins like release, or the project documents that CI intentionally accepts tag-pinning risk because CI has read-only permissions and no deployment authority.

## Proposed Interaction Or Behavior

- Pin CI actions to full SHAs.
- Keep read-only permissions.
- Add a lightweight update process for action SHAs.

## Design Decisions

- Treat release workflow as the hard standard.
- Treat CI tag pinning as a hardening gap, not an immediate release blocker.
- Keep GitHub token permissions minimal regardless of pinning choice.

## Patterns To Follow

- Pin third-party actions to immutable SHAs for sensitive workflows.
- Keep permissions explicit.
- Prefer consistency between CI and release where maintenance cost is low.

## Patterns To Avoid

- Do not broaden token permissions while changing pins.
- Do not assume major-version tags are immutable.
- Do not block audit completion on this low-severity hardening task.

## Success Signals

- CI and release workflows both use full-length commit SHA pins, or the risk is documented.
- `just ci` and GitHub CI still run the same quality gates.
- Action updates remain traceable.

## Open Questions And Risks

- The repository may prefer Dependabot/Renovate action updates by tag. If so, pinning policy needs a maintenance plan.

## What Needs Human Review

The maintainer should decide whether CI should match release hardening or remain tag-pinned for easier updates.

## Recommended Next Phase

`pa-tdd` for a small workflow hardening change if accepted.
