# qobuz-dl capability scenarios - 2026-06-20

## Shared evaluation conditions

- Evaluation method: pass/fail for each scenario.
- Scenario granularity: 10 scenarios total, 1 implementation PR per scenario.
- Scope for this PR: S03 only; S01 and S02 evidence is retained from merged PRs.
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
| S02 | Direct source routing | Album/track/artist/label/playlist URLs route correctly, invalid URLs do not crash, collection pages are all consumed. | Pass |
| S03 | Text-file source ingestion | Local URL files ignore blank/comment lines, dispatch remaining URLs, and bad files fail gracefully. | Pass |
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

## S02 evidence

### Automated coverage

S02 is covered in `tests/test_core_regressions.py`.

| Behavior | Evidence |
| --- | --- |
| Album and track URLs route directly | `test_handle_url_routes_direct_album_and_track_downloads` parametrizes album and track URLs and verifies `handle_url` dispatches the parsed ID to `download_from_id` with the correct album/track flag and no alternate collection path. |
| Artist, label, and playlist URLs route through collection metadata | `test_handle_url_downloads_collection_items_from_every_page` parametrizes artist, label, and playlist URLs against a fake client and verifies the correct client metadata method is used. |
| Collection pages are all consumed | The same collection-routing test returns two fake metadata pages and verifies all three items across both pages are queued, rather than only the first page. |
| Playlist M3U generation is controlled by the existing no-m3u flag | The collection-routing test parametrizes `no_m3u_for_playlists` and verifies playlist URLs call `make_m3u` only when the flag is false; artist and label URLs never call `make_m3u`. |
| Invalid URLs do not crash | `test_handle_url_logs_invalid_url_without_crashing` calls `handle_url` with a non-Qobuz URL and verifies an invalid-url log record is emitted instead of an exception. |
| URL parsing covers supported direct source forms | `TestGetUrlInfo` parametrizes album, track, artist, label, playlist, and www/open/play/bare-path URL forms, and verifies invalid inputs raise `ValueError`. |

### Commands and outcomes

| Command | Outcome |
| --- | --- |
| `git status --short` | Clean before changes. |
| `uv run pytest tests/test_core_regressions.py` | Pass: 24 tests passed. |
| `just ci` | Pass: ruff format check, ruff lint, 86 pytest tests, local CLI help smoke checks, and `uv build` all succeeded. |
| `uv run python /Users/assistant/.agents/skills/autoreview/scripts/autoreview --mode local` | Pass: no accepted/actionable findings reported. |

## S02 status

Pass. S02 behavior is covered by local automated tests using fake clients, monkeypatched M3U generation, captured logs, and pytest temporary directories. No live Qobuz credentials, Qobuz API calls, Last.fm pages, or media downloads are required.

## S03 evidence

### Automated coverage

S03 is covered in `tests/test_core_regressions.py`.

| Behavior | Evidence |
| --- | --- |
| Local URL files ignore blank and comment lines | `test_download_list_of_urls_ingests_text_file_sources_in_order` writes a temporary URL file containing blank lines, whitespace-only lines, whole-line comments, and indented comments, then verifies only non-comment URL lines are dispatched. |
| Remaining URLs dispatch through the normal URL handling path in order | The same test invokes `download_list_of_urls([str(url_file)])`, fakes the normal Qobuz and Last.fm handlers, and verifies the surviving URLs are dispatched in file order. |
| Repeated valid URLs are preserved | The same test includes the same track URL twice and verifies both occurrences are dispatched. |
| Bad and missing files fail gracefully | `test_download_from_txt_file_logs_bad_files_without_dispatching` covers a missing temporary path and an invalid UTF-8 text file, verifies an `Invalid text file` log entry, and fails the test if any URL dispatch happens. |
| Unreadable files fail gracefully | `test_download_from_txt_file_logs_unreadable_file_without_dispatching` simulates `PermissionError`, verifies an `Invalid text file` log entry, and fails the test if any URL dispatch happens. |
| Bad-file paths avoid live Qobuz/API/download behavior | The bad-file and unreadable-file tests construct `QobuzDL` without initializing a client, patch dispatch to fail if touched, and verify no `client` attribute is created. |

### Commands and outcomes

| Command | Outcome |
| --- | --- |
| `git status --short` | Clean before changes. |
| `uv run pytest tests/test_core_regressions.py -k "text_file or txt_file"` | Pass: 4 tests passed, 24 deselected. |
| `just ci` | Pass: ruff format check, ruff lint, 90 pytest tests, local CLI help smoke checks, and `uv build` all succeeded. |
| `uv run python /Users/assistant/.agents/skills/autoreview/scripts/autoreview --mode local` | Pass: no accepted/actionable findings reported. |

## S03 status

Pass. S03 behavior is covered by local automated tests using temporary URL files, fake URL handlers, monkeypatched file errors, and captured logs. No live Qobuz credentials, Qobuz API calls, Last.fm pages, or media downloads are required.
