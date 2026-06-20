# qobuz-dl capability scenarios - 2026-06-20

## Shared evaluation conditions

- Evaluation method: pass/fail for each scenario.
- Scenario granularity: 10 scenarios total, 1 implementation PR per scenario.
- Scope for this PR: S01 only.
- No live Qobuz credentials, subscription, API, or media downloads.
- No live Last.fm pages.
- Use mocked network, fake filesystem state, and temporary directories only.
- Record evidence as commands plus observed outcome.
- Run local project commands with `uv`; run the local CLI as `uv run qobuz-dl ...`.
- Before finishing implementation, run `just ci` unless blocked.

## Pass/fail rubric

| Result | Meaning |
| --- | --- |
| Pass | Automated tests or documented commands prove the scenario behavior under the shared conditions, with no live services or real downloads. |
| Fail | A covered behavior is missing, unsafe, or requires live services or real downloads under default tests. |
| Not evaluated | The scenario belongs to a later PR and has no pass/fail claim in this PR. |

## Scenario matrix

| ID | Capability area | Scenario summary | Status in this PR |
| --- | --- | --- | --- |
| S01 | CLI/config safety | Help/version do not initialize config; parser exposes commands/options; show-config redacts sensitive values; reset/purge behavior is safe. | Pass |
| S02 | Direct source routing | Album/track/artist/label/playlist URLs route correctly, invalid URLs do not crash, collection pages are all consumed. | Not evaluated |
| S03 | Text-file source ingestion | Local URL files ignore blank/comment lines, dispatch remaining URLs, and bad files fail gracefully. | Not evaluated |
| S04 | Lucky search mode | Query validation, type/limit mapping, result URLs, and download dispatch are correct. | Not evaluated |
| S05 | Interactive queue mode | Type selection, search loop, multi-select ranges/dedupe, default quality, no-download test mode, and Ctrl-C behavior are correct. | Not evaluated |
| S06 | Last.fm playlist ingestion | Fixture HTML parsing, sanitization, missing Qobuz match skip, M3U optional behavior, and HTTP errors are safe. | Not evaluated |
| S07 | Download execution | Album/track download paths, quality fallback/no-fallback, cover/booklet/no-cover, multi-disc folders, existing file skip, and interrupted streams are handled. | Not evaluated |
| S08 | Duplicate tracking | SQLite DB create/add/skip, --no-db wiring, and purge behavior are correct. | Not evaluated |
| S09 | Metadata/M3U | FLAC/MP3 tagging helpers and M3U generation work from local fake media/metadata without live downloads. | Not evaluated |
| S10 | HTTP/API/bundle/packaging | HTTP headers/params/errors/streaming, qopy endpoint params/signatures, bundle parsing, import/entry-point/build smoke are correct. | Not evaluated |

## S01 evidence

### Automated coverage

S01 is covered in `tests/test_commands.py`.

| Behavior | Evidence |
| --- | --- |
| Help/version avoid config initialization | `test_help_and_version_do_not_initialize_config` parametrizes top-level help, version, and subcommand help while config paths point at missing temp files; `_reset_config` is patched to fail if called. |
| Parser exposes commands/options | Existing parser tests cover top-level reset/purge/show-config, `dl`, `fun`, `lucky`, shared download options, help text, and version output. |
| show-config redacts sensitive values | `test_show_config_redacts_sensitive_values` verifies email, password, app_id, and secrets are replaced with `<redacted>` while non-sensitive defaults remain visible. |
| reset behavior is safe | `test_reset_config_creates_parent_directory`, `test_reset_exits_before_client_initialization`, and `test_first_run_reset_only_resets_once` verify reset can create a missing config directory, calls `_reset_config` once, and exits before constructing the Qobuz client. |
| purge behavior is safe | `test_purge_only_removes_database_and_exits` and `test_first_run_purge_does_not_initialize_config` verify `--purge` removes only the configured duplicate-tracking database when present, tolerates an absent database, skips config initialization on first run, and exits before constructing the Qobuz client. |

### Commands and outcomes

| Command | Outcome |
| --- | --- |
| `git status --short` | Clean before changes. |
| `uv run pytest tests/test_commands.py` | Pass: 21 tests passed. |
| `just ci` | Pass: ruff format check, ruff lint, 79 pytest tests, local CLI help smoke checks, and `uv build` all succeeded. |
| `uv run python /Users/assistant/.agents/skills/autoreview/scripts/autoreview --mode local` | Initial runs found first-run reset/purge safety gaps; accepted findings were fixed and covered. Final rerun passed with no accepted/actionable findings. |

## S01 status

Pass. S01 behavior is covered by local automated tests using temporary config/database paths and monkeypatched boundaries. No live Qobuz credentials, Qobuz API calls, Last.fm pages, or media downloads are required.
