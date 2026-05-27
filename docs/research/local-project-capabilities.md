# qobuz-dl local project capabilities

Read-only exploration of `/Users/andy16/Documents/github_local/qobuz-dl` on 2026-05-26. Source files were not modified; this file is the requested research artifact.

## Project shape and entry points

- Python CLI/package. `pyproject.toml` declares `qobuz-dl` version `0.9.9.10`, Python `>=3.10`, runtime dependency `mutagen>=1.47,<2`, and console scripts `qobuz-dl` plus `qdl` pointing to `qobuz_dl:main` (`pyproject.toml:5-28`).
- Package exports `main` and `Client` only (`qobuz_dl/__init__.py:1-4`). The documented module API is `QobuzDL` from `qobuz_dl.core` (`docs/module-usage.md:1-17`).
- Local development must use `uv run ...`, not any globally installed `/Users/andy16/.local/bin/qobuz-dl` (`AGENTS.md`, `docs/development.md:1-31`).

## CLI features

- Global usage: `qobuz-dl [-h] [--version] [-r] [-p] [-sc] {fun,dl,lucky} ...` (`docs/cli.md:5-10`, `qobuz_dl/commands.py:154-190`).
- Global flags:
  - `--version` from installed package metadata (`qobuz_dl/commands.py:9-13`, `qobuz_dl/commands.py:166-171`).
  - `-r/--reset` creates/resets config (`qobuz_dl/commands.py:173-175`, `qobuz_dl/cli.py:52-94`).
  - `-p/--purge` deletes local downloaded-ID DB (`qobuz_dl/commands.py:176-183`, `qobuz_dl/cli.py:205-211`).
  - `-sc/--show-config` prints config and DB paths with sensitive values redacted (`qobuz_dl/commands.py:184-188`, `qobuz_dl/cli.py:28-49`, `qobuz_dl/cli.py:199-203`).
- Subcommands:
  - `dl SOURCE...`: downloads Qobuz album/track/artist/label/playlist URLs, Last.fm playlist URLs, or local text files of URLs (`qobuz_dl/commands.py:79-105`, `qobuz_dl/core.py:268-294`).
  - `fun`: interactive search, multi-select queue, quality choice, then download (`qobuz_dl/commands.py:15-38`, `qobuz_dl/core.py:371-443`).
  - `lucky QUERY...`: search and download first N results for selected type (`qobuz_dl/commands.py:40-76`, `qobuz_dl/core.py:296-311`).
- Common download flags for all subcommands: directory, quality, albums-only, no-m3u, no-fallback, embed-art, og-cover, no-cover, no-db, folder-format, track-format, smart-discography (`qobuz_dl/commands.py:108-154`). Qualities are exactly `5, 6, 7, 27` (`qobuz_dl/commands.py:3-5`). Lucky types are `artist, album, track, playlist` (`qobuz_dl/commands.py:6`, `qobuz_dl/commands.py:60-67`).

## Config, auth, and session behavior

- Config lives under OS config dir: macOS/Linux `~/.config/qobuz-dl/config.ini`; DB at `~/.config/qobuz-dl/qobuz_dl.db` (`qobuz_dl/cli.py:18-26`).
- First non-help run creates config interactively: email, MD5-hashed password, default folder, default quality, limit, booleans, app ID, secrets, and filename formats (`qobuz_dl/cli.py:52-94`). Help/version bypass config creation (`qobuz_dl/cli.py:130-137`).
- App ID and app secrets are scraped from Qobuz web bundle: fetch `https://play.qobuz.com/login`, parse bundle JS URL, fetch bundle, extract production app ID and timezone-specific secrets (`qobuz_dl/bundle.py:17-77`).
- Client auth uses Qobuz endpoint `user/login` with email, MD5 password, and app ID; free accounts without credential parameters are rejected (`qobuz_dl/qopy.py:43-49`, `qobuz_dl/qopy.py:124-131`).
- After login, `X-User-Auth-Token` is added to the HTTP session headers (`qobuz_dl/qopy.py:124-131`). Initial headers include `User-Agent`, `X-App-Id`, and JSON content type (`qobuz_dl/qopy.py:22-37`).
- Secret validation calls `track/getFileUrl` on hard-coded track ID `5966783` at format 5 until a secret works (`qobuz_dl/qopy.py:194-208`).

## Qobuz API/client endpoints used

Production HTTP boundary is `qobuz_dl/http.py`; it wraps stdlib `urllib` for GET params/headers, JSON/text helpers, and streaming downloads (`qobuz_dl/http.py:1-123`). `qopy.Client` base URL is `https://www.qobuz.com/api.json/0.2/` (`qobuz_dl/qopy.py:38`).

Endpoints wired in `qobuz_dl/qopy.py`:

| Capability | Endpoint | Evidence |
|---|---|---|
| Login | `user/login` | `qobuz_dl/qopy.py:43-49`, `qobuz_dl/qopy.py:124-131` |
| Track metadata | `track/get` | `qobuz_dl/qopy.py:50-51`, `qobuz_dl/qopy.py:152-153` |
| Album metadata | `album/get` | `qobuz_dl/qopy.py:52-53`, `qobuz_dl/qopy.py:149-150` |
| Playlist metadata with tracks | `playlist/get`, `extra=tracks`, paged 500 | `qobuz_dl/qopy.py:54-60`, `qobuz_dl/qopy.py:161-162` |
| Artist metadata with albums | `artist/get`, `extra=albums`, paged 500 | `qobuz_dl/qopy.py:61-68`, `qobuz_dl/qopy.py:158-159` |
| Label metadata with albums | `label/get`, `extra=albums`, paged 500 | `qobuz_dl/qopy.py:69-75`, `qobuz_dl/qopy.py:164-165` |
| File URL | `track/getFileUrl` with signed `request_sig` and `intent=stream` | `qobuz_dl/qopy.py:88-106`, `qobuz_dl/qopy.py:155-156` |
| Search albums/artists/playlists/tracks | `album/search`, `artist/search`, `playlist/search`, `track/search` | `qobuz_dl/qopy.py:167-177`, used by `qobuz_dl/core.py:313-368` |
| Favorites | `favorite/getUserFavorites` | wrappers exist at `qobuz_dl/qopy.py:179-189`, but see caveat below |
| User playlists | `playlist/getUserPlaylists` | wrapper exists at `qobuz_dl/qopy.py:191-192`, not used by CLI |

Caveat: `favorite/getUserFavorites` wrapper appears not currently usable as written: the special `api_call` branch requires `kwargs["sec"]` and hard-codes `type: "albums"`, while `get_favorite_*` wrappers do not pass `sec` (`qobuz_dl/qopy.py:76-87`, `qobuz_dl/qopy.py:179-189`). No CLI path calls these wrappers.

## Download behavior

- URL routing supports Qobuz `album`, `track`, `artist`, `label`, and `playlist`; regex accepts `www`, `open`, or `play.qobuz.com` and optional locale prefix (`qobuz_dl/utils.py:150-164`).
- Album/track URLs call `download_from_id` directly; artist/label/playlist URLs first fetch a collection and iterate contained albums/tracks (`qobuz_dl/core.py:209-266`).
- Local text files are read line-by-line; comment lines starting with `#` are ignored (`qobuz_dl/core.py:284-294`). Blank lines are not filtered by current code.
- Last.fm playlist URLs are fetched as HTML via `http.get_text`, parsed with `html.parser`, searched as Qobuz tracks, downloaded into a sanitized playlist directory, and optionally converted to `.m3u` (`qobuz_dl/core.py:12-65`, `qobuz_dl/core.py:445-481`).
- Duplicate tracking uses SQLite table `downloads(id TEXT UNIQUE NOT NULL)`; existing IDs are skipped unless DB is disabled (`qobuz_dl/db.py:1-31`, `qobuz_dl/core.py:182-207`). CLI `--no-db` disables DB for one run (`qobuz_dl/cli.py:234`).
- Album download flow: get album metadata, require `streamable`, optionally skip singles/EPs/Various Artists, inspect requested quality, create formatted sanitized folder, download cover/booklet, iterate tracks, get each file URL, stream audio, tag files (`qobuz_dl/downloader.py:63-131`).
- Track download flow: get file URL, get track metadata, create formatted sanitized folder, download cover, stream audio, tag file (`qobuz_dl/downloader.py:133-182`).
- Quality fallback behavior is inverted through naming: `QobuzDL.quality_fallback=True` becomes `Download.downgrade_quality=True`; when fallback is disabled and Qobuz restrictions report `FormatRestrictedByFormatAvailability`, the item is skipped (`qobuz_dl/cli.py:97-98`, `qobuz_dl/downloader.py:274-304`).
- File streaming goes through `http.stream_download`; it writes chunks to a temp file and raises `ConnectionError` if `content-length` does not match bytes written (`qobuz_dl/http.py:100-123`). Temp leftovers matching `**/.*.tmp` are removed after command handling (`qobuz_dl/cli.py:100-105`, `qobuz_dl/cli.py:107-127`).
- Tags are written with `mutagen`: FLAC Vorbis comments/pictures and MP3 ID3v2.3 (`qobuz_dl/metadata.py:1-220`). `.m3u` generation reads local MP3/FLAC metadata (`qobuz_dl/utils.py:17-55`).

## Search behavior

- `search_by_type(query, item_type, limit, lucky=False)` rejects queries shorter than 3 characters (`qobuz_dl/core.py:313-317`).
- Supported search types map to Qobuz endpoints: album, artist, track, playlist (`qobuz_dl/core.py:319-347`). Returned URLs are normalized as `https://play.qobuz.com/{type}/{id}` (`qobuz_dl/core.py:350-367`).
- Album/track search display includes duration and HI-RES/LOSSLESS based on `hires_streamable`; artist/playlist display uses counts (`qobuz_dl/core.py:319-367`).
- `lucky` mode uses search results as direct URLs and then calls normal URL download routing (`qobuz_dl/core.py:296-311`).
- `fun` mode uses built-in terminal prompts: numbered type selection, comma/range multiselect, yes/no queue loop, and final quality selection (`qobuz_dl/core.py:67-104`, `qobuz_dl/core.py:371-443`).

## Tests and docs constraints

- Main proof gate is `just ci`, which runs ruff format check, ruff lint, pytest, CLI smoke help checks, and `uv build` (`justfile:15-40`).
- Default tests must not require Qobuz credentials, an active subscription, live Qobuz API calls, live Last.fm pages, or real media downloads; network behavior should be mocked (`docs/testing.md:87-100`).
- Current tests cover CLI parsing/help/config redaction (`tests/test_commands.py`), DB behavior (`tests/test_db.py`), HTTP boundary (`tests/test_http.py`), bundle parsing/download stream characterization (`tests/test_bundle_downloader_characterization.py`), Last.fm fixtures (`tests/test_lastfm_characterization.py`), qopy API call/signature behavior (`tests/test_qopy_characterization.py`), terminal prompts (`tests/test_terminal_interactive_characterization.py`), sanitization/path generation (`tests/test_sanitization_characterization.py`), metadata helpers (`tests/test_metadata_characterization.py`), and imports (`tests/test_imports.py`).
- Dependency docs explicitly require characterization tests before later dependency removals and keep `mutagen` as retained/pinned/audited (`docs/dependencies.md:7-20`, `docs/dependencies.md:22-60`).
- Packaging metadata belongs in `pyproject.toml`; `setup.py` is intentionally minimal and should not regain duplicate metadata (`docs/packaging.md:1-35`).
- Documentation map expects user docs in `README.md` and detailed docs under `docs/` (`docs/INDEX.md:1-13`). Behavior/tooling/package changes should update docs per repository instructions.

## Likely integration points for adding/removing functionality

- **New CLI flag or command:** `qobuz_dl/commands.py` for parser shape/help, `qobuz_dl/cli.py` for config/default wiring and dispatch, tests in `tests/test_commands.py`, docs in `docs/cli.md` and examples/README as user-visible.
- **New Qobuz endpoint:** add wrapper in `qobuz_dl/qopy.py` while keeping network through `qobuz_dl/http.py`; add mocked tests in `tests/test_qopy_characterization.py` or a new focused test. Avoid bypassing `qobuz_dl/http.py` (`docs/dependencies.md:90-97`).
- **New URL/source type:** `qobuz_dl/utils.py:get_url_info` and/or `QobuzDL.download_list_of_urls`/`handle_url` in `qobuz_dl/core.py`; add fixture/mocked tests for routing and docs under `docs/cli.md`/`docs/examples.md`.
- **Download organization/quality/tagging:** `qobuz_dl/downloader.py` owns album/track download flow, quality checks, cover/booklet downloads, filename formats, temp files; `qobuz_dl/metadata.py` owns audio tags; `qobuz_dl/sanitize.py` owns generated name sanitization.
- **Duplicate tracking changes:** `qobuz_dl/db.py` and `QobuzDL.download_from_id`; validate with `tests/test_db.py` and command tests around `--no-db`/`--purge`.
- **Search UX changes:** `QobuzDL.search_by_type`, `lucky_mode`, and `interactive`; tests should mock `search_by_type`/client responses and avoid real terminal/network.
- **Dependency removal/addition:** follow `docs/dependencies.md`; add characterization tests first, update `pyproject.toml`, `requirements.txt`, `uv.lock`, and docs; run `just ci`.
