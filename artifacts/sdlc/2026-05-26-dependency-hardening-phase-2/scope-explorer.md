# Dependency Hardening Phase 2 — Scope Explorer

Read-only scope pass. Current working tree changes are treated as the intentional baseline; this note does not recommend unrelated cleanup.

## Likely test files and fixtures

- `tests/test_sanitization_characterization.py`
  - Cover `qobuz_dl.downloader.Download._get_album_attr`, `_get_track_attr`, `_get_filename_attr`, `_clean_format_str`, and `_download_and_tag` with monkeypatched `tqdm_download`/metadata taggers where needed.
  - Also cover `qobuz_dl.core.QobuzDL.handle_url` path creation for playlist/artist/label content names, with fake client metadata and monkeypatched `download_from_id`/`make_m3u`.
- `tests/test_lastfm_characterization.py`
  - Use `tests/fixtures/lastfm_playlist.html` and optionally `tests/fixtures/lastfm_playlist_empty.html`.
  - Mock `qobuz_dl.core.requests.get`; stub `search_by_type`, `download_from_id`, and `make_m3u`.
- `tests/test_qopy_characterization.py`
  - Avoid `Client.__init__`; instantiate via `qopy.Client.__new__` and attach fake `id`, `base`, `sec`, `uat`, and fake `session`.
  - Fake response object should support `status_code`, `json()`, and `raise_for_status()`.
- `tests/test_bundle_characterization.py`
  - Fake `qobuz_dl.bundle.Session` before constructing `Bundle`.
  - Fixtures can be inline strings unless JS readability argues for `tests/fixtures/qobuz_login.html` and `tests/fixtures/qobuz_bundle.js`.
- `tests/test_downloader_characterization.py`
  - Focus `tqdm_download` with fake `requests.get`, fake response headers, `iter_content`, and temp files.
  - Monkeypatch `qobuz_dl.downloader.tqdm` to a no-op context manager to avoid terminal/progress assertions.
- `tests/test_terminal_characterization.py` / `tests/test_interactive_characterization.py`
  - Color constants from `qobuz_dl.color` are simple string assertions.
  - Interactive flow requires injecting a fake `pick` module in `sys.modules` plus monkeypatched `input`, `search_by_type`, and `download_list_of_urls`.
- `tests/test_metadata_characterization.py`
  - Directly test private pure helpers in `qobuz_dl.metadata`: `_get_title`, `_format_genres`, `_format_copyright`.
  - No binary MP3/FLAC fixtures in this phase.

Existing tests are minimal (`tests/test_commands.py`, `tests/test_db.py`, `tests/test_imports.py`), so Phase 2 can add focused characterization files without restructuring the test suite.

## Dependency-owned behavior seams

- `pathvalidate`
  - `qobuz_dl.downloader`: `sanitize_filepath(folder_format.format(...))`, `sanitize_filename(track_format.format(...))`, album/track attr helpers sanitize artist/album values.
  - `qobuz_dl.core`: `sanitize_filename(content_name)` in `handle_url`; Last.fm `h1` playlist title sanitization.
  - Best seam: pure helper calls first; temp-dir path checks second; monkeypatch download/tag side effects.
- `beautifulsoup4`
  - `QobuzDL.download_lastfm_pl` uses selectors `td.chartlist-artist > a`, `td.chartlist-name > a`, and `h1`.
  - Best seam: fixture HTML through mocked `requests.get(...).content` and observe generated search queries/download IDs.
- `requests`
  - `qopy.Client.api_call`: endpoint params, login status mapping, invalid secret status mapping, `raise_for_status`, JSON return.
  - `core.download_lastfm_pl`: `requests.get(url, timeout=10)` error path and content parsing.
  - `downloader.tqdm_download`: `requests.get(..., allow_redirects=True, stream=True)`, headers, chunks, interrupted size check.
  - `bundle.Bundle`: `Session().get(login)`, bundle URL extraction, bundle fetch.
- `tqdm`
  - Only observable Phase 2 behavior should be that streamed bytes are written and short writes raise `ConnectionError`; progress rendering itself should be faked.
- `pick`
  - `QobuzDL.interactive` imports `pick` inside the method, then calls it for type, multiselect queue, keep-searching, and quality.
  - Best seam: fake module + deterministic pick responses; avoid curses/terminal simulation.
- `colorama`
  - Centralized in `qobuz_dl.color`; downstream modules consume constants. Characterize exported constants as strings, not exact ANSI policy unless later removal needs stricter behavior.
- `mutagen`
  - Full tag writing is high-risk/out of scope. Pure formatting seams in `metadata.py` are safe and meaningful.

## Risks: live network, terminal, media

- Live network risk is highest in `qopy.Client.__init__`, `Bundle.__init__`, `download_lastfm_pl`, and `tqdm_download`. Tests should fake before construction/call and should not instantiate authenticated clients normally.
- Terminal flake risk is isolated to `interactive`; inject fake `pick` and `input`. Do not test Windows missing-curses behavior unless a clean platform-independent import-failure seam is obvious.
- Media/file risk is in `_download_and_tag`, `tag_flac`, `tag_mp3`, and `make_m3u`. Phase 2 should avoid real media files and monkeypatch taggers/downloaders when filename behavior needs coverage.
- Bundle secret extraction may be brittle because `get_secrets` depends on regex shape, base64 fragments, and timezone ordering. Cover app ID confidently; only cover secrets with a compact readable fixture, otherwise document follow-up before Phase 5.
- Last.fm “nothing found” path must avoid indexing `search_by_type(...)[0]`; use mismatched/missing artist/title fixture to reach early return.

## Validation commands

```sh
uv run pytest tests/test_sanitization_characterization.py
uv run pytest tests/test_lastfm_characterization.py
uv run pytest tests/test_qopy_characterization.py
uv run pytest tests/test_bundle_characterization.py tests/test_downloader_characterization.py
uv run pytest tests/test_terminal_characterization.py tests/test_interactive_characterization.py tests/test_metadata_characterization.py
just test
just ci
rg "requests.get|Session\(|last.fm|qobuz.com" tests -n
rg "\.mp3|\.flac|cover.jpg" tests -n
```

Inspect `rg` hits to confirm all HTTP/media references are mocked, faked, or static strings. Use `git diff --stat` after implementation to confirm edits stay within Phase 2 tests/fixtures plus optional `docs/testing.md` conventions.
