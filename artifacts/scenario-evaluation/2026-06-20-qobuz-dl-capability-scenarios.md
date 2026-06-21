# qobuz-dl capability scenarios - 2026-06-20

## Shared evaluation conditions

- Evaluation method: pass/fail for each scenario.
- Scenario granularity: 10 scenarios total, 1 implementation PR per scenario.
- Scope for this PR: S07 only; S01-S06 evidence is retained from merged PRs.
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
| S04 | Lucky search mode | Query validation, type/limit mapping, result URLs, and download dispatch are correct. | Pass |
| S05 | Interactive queue mode | Type selection, search loop, multi-select ranges/dedupe, default quality, no-download test mode, and Ctrl-C behavior are correct. | Pass |
| S06 | Last.fm playlist ingestion | Fixture HTML parsing, sanitization, missing Qobuz match skip, M3U optional behavior, and HTTP errors are safe. | Pass |
| S07 | Download execution | Album/track download paths, quality fallback/no-fallback, cover/booklet/no-cover, multi-disc folders, existing file skip, and interrupted streams are handled. | Pass |
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

## S04 evidence

### Automated coverage

S04 is covered in `tests/test_core_regressions.py`.

| Behavior | Evidence |
| --- | --- |
| Short and invalid lucky queries are rejected before search/download | `test_lucky_mode_rejects_short_or_invalid_queries_without_search_or_download` parametrizes empty, too-short, whitespace-only, and non-string queries, patches `search_by_type` and `download_list_of_urls` to fail if touched, and verifies the invalid-query log path returns without dispatch. |
| Short and invalid search-boundary queries avoid live client access | `test_search_by_type_rejects_short_or_invalid_queries_without_client` covers the same invalid query shapes directly against `search_by_type`, verifies no `client` attribute is required, and therefore proves no live Qobuz search boundary is touched. |
| Valid lucky queries use the configured type and limit | `test_lucky_mode_uses_configured_search_boundary_and_download_flag` configures `lucky_type="track"` and `lucky_limit=2`, then verifies `lucky_mode` calls `search_by_type` with the normalized query, configured type, configured limit, and `lucky=True`. |
| Download dispatch is controlled by the existing `download` flag | The same lucky-mode test verifies `download=True` dispatches the returned URL list through `download_list_of_urls`, while `download=False` returns the same URL list without dispatch. |
| Lucky result URLs are built for album, track, artist, and playlist search types | `test_search_by_type_lucky_builds_urls_for_supported_types` parametrizes all supported lucky types with fake client methods and verifies URLs are normalized as `https://play.qobuz.com/{type}/{id}` with the requested limit. |

### Commands and outcomes

| Command | Outcome |
| --- | --- |
| `git status --short` | Clean before changes. |
| `uv run pytest tests/test_core_regressions.py -k "lucky or search_by_type"` | Pass: 13 tests passed, 28 deselected. |
| `just ci` | Pass: ruff format check, ruff lint, 103 pytest tests, local CLI help smoke checks, and `uv build` all succeeded. |
| `uv run python /Users/assistant/.agents/skills/autoreview/scripts/autoreview --mode local` | Pass: no accepted/actionable findings reported. |

## S04 status

Pass. S04 behavior is covered by local automated tests using fake client search methods, monkeypatched search/download dispatch boundaries, captured logs, and pytest temporary directories. No live Qobuz credentials, Qobuz API calls, Last.fm pages, or media downloads are required.

## S05 evidence

### Automated coverage

S05 is covered in `tests/test_terminal_interactive_characterization.py`.

| Behavior | Evidence |
| --- | --- |
| Type selection is deterministic under fake input | `test_interactive_builtin_prompts_return_selected_urls_without_download` selects Tracks with monkeypatched `input`, fakes `search_by_type`, and verifies the returned track URL and prompts without constructing a live client. |
| Search loop retries default empty result selection | `test_interactive_search_loop_retries_empty_selection_and_dedupes_in_order` sends an empty selection for the first fake search result list, verifies the loop asks for a second query, and asserts both fake search calls were made in order with type `track` and the configured limit. |
| Multi-select parsing supports comma-separated values and ranges | `test_interactive_multiselect_accepts_commas_and_ranges` selects `1,3-4` against fake search results and verifies the corresponding URLs are returned in selection order. |
| Multi-select dedupes repeated selections while preserving first-seen order | `test_interactive_search_loop_retries_empty_selection_and_dedupes_in_order` selects `3,1-2,2,3` and verifies the final queue is `3,1,2`. |
| Default quality behavior is covered | `test_interactive_quality_prompt_defaults_to_current_quality` accepts an empty quality prompt and verifies the current quality remains selected; the retry-loop test also accepts the default quality after queueing. |
| No-download/test-mode behavior avoids dispatch | `test_interactive_builtin_prompts_return_selected_urls_without_download` and `test_interactive_search_loop_retries_empty_selection_and_dedupes_in_order` call `interactive(download=False)` and verify `download_list_of_urls` is not dispatched. |
| Ctrl-C exits safely | `test_interactive_keyboard_interrupt_cancels_cleanly` raises `KeyboardInterrupt` from monkeypatched `input`, verifies `interactive(download=False)` returns `None`, and fails the test if search or download dispatch happens after the interrupt. |

### Commands and outcomes

| Command | Outcome |
| --- | --- |
| `git status --short` | Clean before changes. |
| `uv run pytest tests/test_terminal_interactive_characterization.py` | Pass: 7 tests passed. |
| `just ci` | Pass: ruff format check, ruff lint, 104 pytest tests, local CLI help smoke checks, and `uv build` all succeeded. |
| `uv run python /Users/assistant/.agents/skills/autoreview/scripts/autoreview --mode local` | Pass: no accepted/actionable findings reported. |

## S05 status

Pass. S05 behavior is covered by local automated tests using monkeypatched input, fake search results, monkeypatched download dispatch boundaries, captured prompts, and pytest temporary directories. No live Qobuz credentials, Qobuz API calls, Last.fm pages, or media downloads are required.

## S06 evidence

### Automated coverage

S06 is covered in `tests/test_lastfm_characterization.py` and `tests/test_core_regressions.py`.

| Behavior | Evidence |
| --- | --- |
| Fixture HTML parsing extracts playlist title, artists, and tracks | `test_lastfm_playlist_parser_extracts_fixture_title_artists_and_tracks` feeds `tests/fixtures/lastfm_playlist.html` to `LastFmPlaylistParser` and verifies the raw playlist title, artists, and track titles. |
| Output directory names are sanitized | `test_lastfm_playlist_parsing_sanitizes_title_downloads_found_tracks_and_obeys_m3u_flag` verifies the fixture title `My: Last/fm Playlist?*` is used as the sanitized download directory `My Lastfm Playlist`. |
| Parsed artist/title pairs drive fake Qobuz track searches | The same test verifies the generated fake search queries are `Alpha Artist First Song` and `Beta: Artist Second/Track`, with item type `track`, limit `1`, and `lucky=True`. |
| Found Qobuz matches dispatch fake track downloads only | The same test fakes Qobuz search results and verifies `download_from_id` receives the parsed track IDs with `album=False` and the sanitized playlist directory as `alt_path`. |
| Missing Qobuz matches are skipped safely | `test_lastfm_playlist_skips_tracks_without_qobuz_matches` returns no fake search result for the first parsed track and verifies only the matched second track is downloaded. |
| Playlist M3U generation obeys the existing no-m3u flag | `test_lastfm_playlist_parsing_sanitizes_title_downloads_found_tracks_and_obeys_m3u_flag` parametrizes `no_m3u_for_playlists` and verifies `make_m3u` is called only when the flag is false. |
| Empty or unusable playlist pages do not search, download, or create M3U files | `test_lastfm_playlist_with_no_usable_track_list_does_not_search_or_download` uses `tests/fixtures/lastfm_empty_playlist.html` and verifies fake search, download, and M3U boundaries are untouched. |
| Last.fm HTTP errors fail gracefully | `test_lastfm_playlist_http_errors_do_not_escape` parametrizes fake `HttpRequestError` and `HttpStatusError`, verifies no exception escapes, and asserts search, download, and M3U boundaries are untouched. |

### Commands and outcomes

| Command | Outcome |
| --- | --- |
| `git status --short` | Clean before changes. |
| `uv run pytest tests/test_lastfm_characterization.py tests/test_core_regressions.py::test_lastfm_playlist_skips_tracks_without_qobuz_matches` | Pass: 7 tests passed. |
| `just ci` | Pass: ruff format check, ruff lint, 107 pytest tests, local CLI help smoke checks, and `uv build` all succeeded. |
| `uv run python /Users/assistant/.agents/skills/autoreview/scripts/autoreview --mode local` | Pass: no accepted/actionable findings reported. |

## S06 status

Pass. S06 behavior is covered by local automated tests using fixture HTML, fake HTTP responses, fake Qobuz search/download methods, monkeypatched M3U generation, captured logs, and pytest temporary directories. No live Qobuz credentials, Qobuz API calls, Last.fm pages, or media downloads are required.

## S07 evidence

### Automated coverage

S07 is covered in `tests/test_download_execution_characterization.py` and `tests/test_bundle_downloader_characterization.py`.

| Behavior | Evidence |
| --- | --- |
| Album download paths are correct | `test_album_download_places_multidisc_tracks_cover_and_booklet` fakes album metadata, track URLs, streamed downloads, and tagging, then verifies the generated album directory, temporary media paths, and final FLAC file paths. |
| Track download paths are correct | `test_track_download_uses_fallback_quality_and_can_skip_cover` fakes a direct track download and verifies the generated track album directory, temporary media path, and final FLAC path. |
| Requested quality fallback behavior is covered | `test_track_download_uses_fallback_quality_and_can_skip_cover` returns a fake Qobuz restriction with `FormatRestrictedByFormatAvailability`, enables fallback, and verifies the media stream and tag boundary are still reached. |
| Requested quality no-fallback behavior is covered | `test_album_download_skips_restricted_quality_when_fallback_disabled` returns the same fake restriction with fallback disabled, verifies the release is skipped before any download/tag boundary, and checks the quality log path. |
| Cover and booklet behavior respects existing options | `test_album_download_places_multidisc_tracks_cover_and_booklet` verifies cover download uses the original-quality URL when requested and booklet download occurs from fake goodies metadata; `test_track_download_uses_fallback_quality_and_can_skip_cover` verifies `no_cover=True` skips cover download while still downloading media. |
| Multi-disc folder placement is correct | `test_album_download_places_multidisc_tracks_cover_and_booklet` verifies tracks with different fake `media_number` values are placed under `Disc 1` and `Disc 2`. |
| Existing files are skipped safely | `test_existing_track_file_is_skipped_without_streaming_or_tagging` pre-creates the expected final FLAC in a pytest temp dir and verifies neither streaming nor tagging is called. |
| Interrupted or failed media streams clean up partial output and surface/log safe failure | `test_failed_media_stream_removes_partial_file_and_logs_safe_failure` fakes a stream that writes a partial `.tmp` file and raises `ConnectionError`, then verifies the partial file is removed and the existing `QobuzDL.download_from_id` error log path is used; `test_download_with_progress_raises_connection_error_when_stream_is_short` verifies the shared streaming wrapper removes partial output before re-raising. |

### Commands and outcomes

| Command | Outcome |
| --- | --- |
| `git status --short` | Clean before changes. |
| `uv run pytest tests/test_download_execution_characterization.py tests/test_bundle_downloader_characterization.py::test_download_with_progress_raises_connection_error_when_stream_is_short` | Pass: 6 tests passed. |
| `just ci` | Pass: ruff format check, ruff lint, 112 pytest tests, local CLI help smoke checks, and `uv build` all succeeded. |
| `uv run python /Users/assistant/.agents/skills/autoreview/scripts/autoreview --mode local` | Pass: no accepted/actionable findings reported. |

## S07 status

Pass. S07 behavior is covered by local automated tests using fake Qobuz/API metadata, fake HTTP/download streams, monkeypatched tag/download boundaries, captured logs, and pytest temporary directories. No live Qobuz credentials, Qobuz API calls, Last.fm pages, or real media downloads are required.
