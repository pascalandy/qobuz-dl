# FSST N1 Audit Criteria

Date: 2026-06-22

## Scope

Audit `qobuz-dl` from actual repository code, tests, packaging, workflows, and current primary sources. Do not implement application fixes. Produce audit artifacts only.

## Same Run Conditions

- Repository: `/Users/assistant/Documents/github_local/qobuz-dl`
- Branch at start: `master`
- Immutable audited app/base revision after final rebase: `95fa412108e59272a66c017fbe9b9dcf4d791a05`
- Final comparison base: `git merge-base master HEAD` = `95fa412108e59272a66c017fbe9b9dcf4d791a05`
- Worktree at start: clean (`git status --short --branch`)
- Python/project command policy: use `uv` and `just`
- Live Qobuz behavior: not exercised because default tests must not require Qobuz credentials, active subscriptions, live Qobuz API calls, live Last.fm pages, or real media downloads
- External research: primary sources first, read-only
- Evaluation method: pass/fail acceptance checks plus area status labels

## Area Status Labels

- `proved`: concrete evidence supports the finding or issue
- `no issue`: inspected and no material issue found under this audit scope
- `weak`: material weakness exists, but not an immediate failing bug
- `N/A`: the area does not exist in this app
- `blocked`: evidence could not be verified after a reasonable direct check

## Severity Labels

- `Critical`: immediate exploit, data loss, or release-blocking failure
- `High`: likely user, legal, credential, or operational harm
- `Medium`: meaningful compatibility, reliability, or maintainability risk
- `Low`: cleanup or hardening issue with limited blast radius
- `N/A`: no issue for the area

## Success Criteria

| ID | Criterion | Result | Evidence |
|---|---|---:|---|
| C1 | Audit is based on actual code/config, not framework assumptions. | PASS | Inspected `qobuz_dl/*.py`, `pyproject.toml`, `requirements.txt`, `uv.lock`, `justfile`, `.github/workflows/*.yml`, `docs/*`, and tests. |
| C2 | Each requested and discovered area is logged with status, severity, and evidence. | PASS | See `area-evidence-table.md`. |
| C3 | Each material issue has a separate `pa-vision` style file under this one directory. | PASS | See `issue-*.md` files in this directory. |
| C4 | External/current limits are checked from primary sources where possible and numbers are calculated. | PASS WITH BLOCKED ITEMS | Python lifecycle, Qobuz audio-size/bitrate, Qobuz API Terms, GitHub Actions security guidance, and PyPI Mutagen were checked. Current Qobuz numeric API rate limits remain blocked because no accessible primary source exposed them. |
| C5 | Anything unverified is listed, checked again, and either resolved or marked blocked. | PASS | See `verification-log.md`. |
| C6 | No production code is changed. | PASS | Only audit artifacts under `artifacts/audit/2026-06-22-fsst-n1-codebase-audit/` were added. |
| C7 | Local proof gate runs before finalizing artifact changes. | PASS | `just ci` passed: ruff format check, ruff lint, 157 pytest tests, CLI smoke checks, and package build. |
| C8 | Client-safe language: no guessed claims are presented as fact. | PASS | Blocked and uncertain areas are explicitly labeled. |

## Issues Logged

| Issue File | Severity | Short Name |
|---|---:|---|
| `issue-qobuz-api-compliance-boundary.md` | High | Qobuz API credential and certification boundary |
| `issue-login-credential-query-exposure.md` | High | Credential-equivalent values in GET query parameters |
| `issue-local-secret-file-permissions.md` | High | Sensitive config/database file permissions not enforced |
| `issue-windows-reserved-filename-gap.md` | Medium | Windows reserved names with extensions can survive sanitization |
| `issue-windows-appdata-startup-risk.md` | Medium | Windows startup can fail when `%APPDATA%` is missing |
| `issue-bulk-api-limit-throttling.md` | Medium | Bulk API/media transfers have no cap, throttle, or verified numeric Qobuz limit |
| `issue-ci-action-sha-pinning.md` | Low | CI workflow uses tag-pinned actions |
| `issue-stale-research-doc.md` | Low | Existing local capability research doc is stale |
