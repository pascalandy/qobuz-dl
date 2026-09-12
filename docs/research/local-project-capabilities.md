# qobuz-dl local project capabilities

> Historical snapshot, 26 May 2026. This report records the project as first explored on that date. Authentication evidence received updates on 11 and 12 September 2026. Code and test line anchors were refreshed against final issue #47 revision `5ed26ae03479d25f1c338d0ab9a65807cf7803c0` on 12 September 2026. Documentation anchors reflect this truth sweep. Use the linked current documentation and [issue #20](https://github.com/pascalandy/qobuz-dl/issues/20) for active work.

## Dated corrections

- On 12 June 2026, commit [`8b5b55f`](https://github.com/pascalandy/qobuz-dl/commit/8b5b55f) changed the package version from `0.9.9.10` to `1.0.0`. `pyproject.toml` now declares version `1.0.0`, Python `>=3.10`, `mutagen>=1.47,<2`, and both console scripts (`pyproject.toml:7-45`)
- On 12 June 2026, commit [`30fb21b`](https://github.com/pascalandy/qobuz-dl/commit/30fb21b) made text-file ingestion skip blank and comment lines. The current list comprehension preserves only nonempty, non-comment values (`qobuz_dl/core.py:437-451`)
- The same commit fixed Favorites request parameters and secret fallback. The current request keeps `type`, `offset`, and `limit`, uses the configured secret unless a caller overrides it, and sends the user token in both the query and the session header (`qobuz_dl/qopy.py:164-176`, `qobuz_dl/qopy.py:243-245`, `qobuz_dl/qopy.py:292-305`)

## Project shape and entry points

- At the 26 May snapshot, `pyproject.toml` declared `qobuz-dl` version `0.9.9.10`, Python `>=3.10`, runtime dependency `mutagen>=1.47,<2`, and console scripts `qobuz-dl` plus `qdl` pointing to `qobuz_dl:main`. See the correction above for the current version.
- Package exports `main` and `Client` only (`qobuz_dl/__init__.py:1-4`). The documented module API is `QobuzDL` from `qobuz_dl.core` (`docs/module-usage.md:1-17`).
- Local development uses `uv run ...`, not a globally installed `$HOME/.local/bin/qobuz-dl` (`AGENTS.md`, `docs/development.md:1-38`).

## CLI features

- Global usage: `qobuz-dl [-h] [--version] [-r] [-p] [-sc] {fun,dl,lucky} ...` (`docs/cli.md:5-10`, `qobuz_dl/commands.py:196-256`).
- Global flags:
  - `--version` from installed package metadata (`qobuz_dl/commands.py:12-17`, `qobuz_dl/commands.py:217-222`).
  - `-r/--reset` creates/resets config (`qobuz_dl/commands.py:223-225`, `qobuz_dl/cli.py:238-278`).
  - `-p/--purge` deletes local downloaded-ID DB (`qobuz_dl/commands.py:226-234`, `qobuz_dl/cli.py:358-369`).
  - `-sc/--show-config` prints config and DB paths with sensitive values redacted (`qobuz_dl/commands.py:235-240`, `qobuz_dl/cli.py:24-31`, `qobuz_dl/cli.py:218-236`, `qobuz_dl/cli.py:353-356`).
- Subcommands:
  - `dl SOURCE...`: downloads Qobuz album/track/artist/label/playlist URLs, Last.fm playlist URLs, or local text files of URLs (`qobuz_dl/commands.py:85-113`, `qobuz_dl/core.py:420-451`).
  - `fun`: interactive search, multi-select queue, quality choice, then download (`qobuz_dl/commands.py:19-45`, `qobuz_dl/core.py:530-603`).
  - `lucky QUERY...`: search and download first N results for selected type (`qobuz_dl/commands.py:48-82`, `qobuz_dl/core.py:453-469`).
- Common download flags for all subcommands: directory, quality, albums-only, no-m3u, no-fallback, embed-art, og-cover, no-cover, no-db, folder-format, track-format, smart-discography (`qobuz_dl/commands.py:116-193`). Qualities are exactly `5, 6, 7, 27` (`qobuz_dl/commands.py:4-5`). Lucky types are `artist, album, track, playlist` (`qobuz_dl/commands.py:6`, `qobuz_dl/commands.py:65-71`).

## Config, auth, and session behavior

- Config lives under OS config dir: macOS/Linux `~/.config/qobuz-dl/config.ini`; DB at `~/.config/qobuz-dl/qobuz_dl.db` (`qobuz_dl/cli.py:73-85`).
- First non-help run creates config interactively. The CLI reads hidden plaintext password input, computes one lowercase MD5 hexadecimal digest over its UTF-8 bytes, and stores the digest under the historical `password` key. It also stores the email, defaults, app ID, secrets, and filename formats (`qobuz_dl/cli.py:238-278`). Help and version bypass config creation (`qobuz_dl/cli.py:304-351`).
- App ID and app secrets are scraped from Qobuz web bundle: fetch `https://play.qobuz.com/login`, parse bundle JS URL, fetch bundle, extract production app ID and timezone-specific secrets (`qobuz_dl/bundle.py:39-119`).
- CLI startup passes the stored digest to `QobuzDL.initialize_client` unchanged. Library callers must also supply the digest expected by the current flow and must not hash an existing digest again. `initialize_client` forwards its `pwd` argument unchanged (`qobuz_dl/cli.py:406-412`, `qobuz_dl/core.py:229-231`; `tests/test_auth_contract.py:114-183`).
- Client auth currently uses GET for `user/login`, with email, the password digest, and app ID in the query. This is current local behavior, not a claim about required or live-verified server transport. Before changing session state, the client validates the response structure, eligible membership parameters, a string membership label, and a non-empty string user token. Free accounts without membership parameters are rejected, while malformed success responses raise the fixed `Invalid login response.` error (`qobuz_dl/qopy.py:84-103`, `qobuz_dl/qopy.py:105-131`, `qobuz_dl/qopy.py:208-246`; `tests/test_auth_contract.py:80-98`; `tests/test_qopy_characterization.py:266-345`).
- After validation, the user token is stored and added to the session as `X-User-Auth-Token`, then authentication prints the fixed `Logged: OK` message. The server-provided membership label is retained internally but not logged (`qobuz_dl/qopy.py:243-246`; `tests/test_qopy_characterization.py:348-378`). Initial headers include `User-Agent`, `X-App-Id`, and JSON content type (`qobuz_dl/qopy.py:65-76`).
- The password digest is credential-equivalent, not encryption. The current login flow can use the digest without the plaintext password. [Authentication credential and transport evidence](authentication-transport.md) records the dated public-client evidence and the unverified server inferences.
- Secret validation calls `track/getFileUrl` on hard-coded track ID `5966783` at format 5 until a secret works (`qobuz_dl/qopy.py:310-328`).

## Qobuz API/client endpoints used

Production HTTP boundary is `qobuz_dl/http.py`; it wraps stdlib `urllib` for GET params/headers, JSON/text helpers, bounded rate-limit retries, and streaming downloads (`qobuz_dl/http.py:1-365`). `qopy.Client` base URL is `https://www.qobuz.com/api.json/0.2/` (`qobuz_dl/qopy.py:76`).

Endpoints wired in `qobuz_dl/qopy.py`:

| Capability | Endpoint | Evidence |
|---|---|---|
| Login | `user/login` | `qobuz_dl/qopy.py:105-131`, `qobuz_dl/qopy.py:208-246` |
| Track metadata | `track/get` | `qobuz_dl/qopy.py:108-109`, `qobuz_dl/qopy.py:133-134`, `qobuz_dl/qopy.py:265-266` |
| Album metadata | `album/get` | `qobuz_dl/qopy.py:110-111`, `qobuz_dl/qopy.py:136-137`, `qobuz_dl/qopy.py:262-263` |
| Playlist metadata with tracks | `playlist/get`, `extra=tracks`, paged 500 | `qobuz_dl/qopy.py:112-113`, `qobuz_dl/qopy.py:139-145`, `qobuz_dl/qopy.py:248-260`, `qobuz_dl/qopy.py:274-275` |
| Artist metadata with albums | `artist/get`, `extra=albums`, paged 500 | `qobuz_dl/qopy.py:114-115`, `qobuz_dl/qopy.py:147-154`, `qobuz_dl/qopy.py:248-260`, `qobuz_dl/qopy.py:271-272` |
| Label metadata with albums | `label/get`, `extra=albums`, paged 500 | `qobuz_dl/qopy.py:116-117`, `qobuz_dl/qopy.py:156-162`, `qobuz_dl/qopy.py:248-260`, `qobuz_dl/qopy.py:277-278` |
| File URL | `track/getFileUrl` with signed `request_sig` and `intent=stream` | `qobuz_dl/qopy.py:120-121`, `qobuz_dl/qopy.py:178-194`, `qobuz_dl/qopy.py:268-269` |
| Search albums/artists/playlists/tracks | `album/search`, `artist/search`, `playlist/search`, `track/search` | `qobuz_dl/qopy.py:280-290`, used by `qobuz_dl/core.py:471-524` |
| Favorites | `favorite/getUserFavorites` | wrappers exist at `qobuz_dl/qopy.py:292-305`; request behavior is documented below |
| User playlists | `playlist/getUserPlaylists` | wrapper exists at `qobuz_dl/qopy.py:307-308`, not used by CLI |

`favorite/getUserFavorites` requests use GET and the configured app secret by default. The current request puts the user token in both the query and the session header. This is current local behavior, not proof that the server accepts header-only authentication or requires both placements. The wrappers preserve type, offset, and limit, and direct API calls can override the secret (`qobuz_dl/qopy.py:105-124`, `qobuz_dl/qopy.py:164-176`, `qobuz_dl/qopy.py:243-245`, `qobuz_dl/qopy.py:292-305`; `tests/test_auth_contract.py:100-111`; `tests/test_qopy_characterization.py:417-482`). No CLI path calls these wrappers.

## Download behavior

- URL routing supports Qobuz `album`, `track`, `artist`, `label`, and `playlist`; regex accepts `www`, `open`, or `play.qobuz.com` and optional locale prefix (`qobuz_dl/utils.py:170-189`).
- Album/track URLs call `download_from_id` directly; artist/label/playlist URLs first fetch a collection and iterate contained albums/tracks (`qobuz_dl/core.py:240-261`, `qobuz_dl/core.py:278-371`).
- At the 26 May snapshot, local text files ignored comment lines but did not filter blank lines. The correction above records the current behavior.
- Last.fm playlist URLs are fetched as HTML via `http.get_text`, parsed with `html.parser`, searched as Qobuz tracks, downloaded into a sanitized playlist directory, and optionally converted to `.m3u` (`qobuz_dl/core.py:65-132`, `qobuz_dl/core.py:604-643`).
- Duplicate tracking uses SQLite table `downloads(id TEXT UNIQUE NOT NULL)`. `download_from_id` skips existing IDs and records only a finalized top-level album or track; ignored, failed, and partial attempts remain retryable (`qobuz_dl/db.py:10-50`, `qobuz_dl/core.py:240-261`). CLI `--no-db` disables DB for one run (`qobuz_dl/commands.py:162-166`, `qobuz_dl/cli.py:397-399`).
- Album download flow: get album metadata, require `streamable`, optionally skip singles/EPs/Various Artists, inspect requested quality, create a formatted sanitized folder, download cover/booklet, iterate tracks, get each file URL, stream audio, tag files, and aggregate the child results (`qobuz_dl/downloader.py:144-232`).
- Track download flow: get the file URL and metadata, create a formatted sanitized folder, download the cover, stream audio, tag the file, and return its result (`qobuz_dl/downloader.py:234-291`, `qobuz_dl/downloader.py:351-423`).
- Quality fallback behavior is inverted through naming: `QobuzDL.quality_fallback=True` becomes `Download.downgrade_quality=True`; when fallback is disabled and Qobuz restrictions report `FormatRestrictedByFormatAvailability`, the item is skipped (`qobuz_dl/cli.py:391-394`, `qobuz_dl/downloader.py:324-330`, `qobuz_dl/downloader.py:483-504`).
- File streaming goes through `http.stream_download`; it writes chunks to a temporary file and raises `ConnectionError` if `content-length` does not match bytes written (`qobuz_dl/http.py:306-365`). Each media operation creates a unique hidden `.qdl-<UUID>.tmp` beside its final file and cleans only that exact path when streaming or tagging fails or an interruption occurs. A completed final file remains after the tagger renames it, and unrelated temporary files remain untouched (`qobuz_dl/downloader.py:351-423`, `tests/test_commands.py:1137-1170`, `tests/test_download_execution_characterization.py:425-588`, `tests/test_download_execution_characterization.py:627-663`).
- Tags are written with `mutagen`: FLAC Vorbis comments/pictures and MP3 ID3v2.3 (`qobuz_dl/metadata.py:1-253`). `.m3u` generation reads local MP3/FLAC metadata (`qobuz_dl/utils.py:35-74`).

## Search behavior

- `search_by_type(query, item_type, limit, lucky=False)` rejects queries shorter than 3 characters (`qobuz_dl/core.py:471-475`).
- Supported search types map to Qobuz endpoints: album, artist, track, playlist. Returned URLs are normalized as `https://play.qobuz.com/{type}/{id}` (`qobuz_dl/core.py:477-525`).
- Album and track search display includes duration and HI-RES or LOSSLESS based on `hires_streamable`; artist and playlist display uses counts (`qobuz_dl/core.py:477-525`).
- `lucky` mode uses search results as direct URLs and then calls normal URL download routing (`qobuz_dl/core.py:453-469`).
- `fun` mode uses built-in terminal prompts: numbered type selection, comma/range multiselect, yes/no queue loop, and final quality selection (`qobuz_dl/core.py:135-190`, `qobuz_dl/core.py:530-603`).

## Tests and docs constraints

- Main proof gate is `just ci`, which runs ruff format check, ruff lint, pytest, CLI smoke help checks, and the package build and installation proof (`justfile:48-52`, `scripts/check.py:16-26`, `scripts/check.py:189-224`).
- Default tests must not require Qobuz credentials, an active subscription, live Qobuz API calls, live Last.fm pages, or real media downloads; network behavior should be mocked (`docs/testing.md:225-233`).
- Current tests cover CLI parsing/help/config redaction (`tests/test_commands.py`), offline credential forwarding and request placement (`tests/test_auth_contract.py`), DB behavior (`tests/test_db.py`), HTTP boundary (`tests/test_http.py`), bundle parsing/download stream characterization (`tests/test_bundle_downloader_characterization.py`), Last.fm fixtures (`tests/test_lastfm_characterization.py`), qopy API call/signature behavior (`tests/test_qopy_characterization.py`), terminal prompts (`tests/test_terminal_interactive_characterization.py`), sanitization/path generation (`tests/test_sanitization_characterization.py`), metadata helpers (`tests/test_metadata_characterization.py`), and imports (`tests/test_imports.py`).
- Dependency docs explicitly require characterization tests before later dependency removals and keep `mutagen` as retained/pinned/audited (`docs/dependencies.md:7-20`, `docs/dependencies.md:22-60`).
- Packaging metadata belongs in `pyproject.toml`; `setup.py` is intentionally minimal and should not regain duplicate metadata (`docs/packaging.md:1-35`).
- Documentation map expects user docs in `README.md` and detailed docs under `docs/` (`docs/INDEX.md:1-13`). Behavior/tooling/package changes should update docs per repository instructions.

## Live verifier status

- Open PR #77 proposes the disabled `just live-qobuz` verifier. This stacked revision contains that proposal, but `master` does not contain it until the PR merges (`qobuz_dl/live_verification.py:903-910`, `tests/test_live_qobuz_verification.py:421-445`, `docs/testing.md:164-174`).
- The verifier reads credential values literally from a private UTF-8 config and hashes the supplied password once as UTF-8 MD5 (`qobuz_dl/live_verification.py:181-192`, `qobuz_dl/live_verification.py:259-264`; `tests/test_live_qobuz_verification.py:713-824`, `tests/test_live_qobuz_verification.py:827-845`).
- The verifier structurally checks FLAC without decoding it, then fetches authoritative metadata for the same authorized track and compares title, artist, album, and track number with the finalized MP3 or FLAC (`qobuz_dl/live_verification.py:351-516`, `qobuz_dl/live_verification.py:533-657`, `qobuz_dl/live_verification.py:818-824`; `tests/test_live_qobuz_verification.py:847-1103`, `tests/test_live_qobuz_verification.py:1375-1897`).
- The offline verifier tests block sockets, protect credentials and private values, and prove the disabled gate. They do not claim that issue #48 ran or that Qobuz accepted an account (`tests/test_live_qobuz_verification.py:47-52`, `tests/test_live_qobuz_verification.py:421-525`, `docs/testing.md:228-240`).

## Likely integration points for adding/removing functionality

- **New CLI flag or command:** `qobuz_dl/commands.py` for parser shape/help, `qobuz_dl/cli.py` for config/default wiring and dispatch, tests in `tests/test_commands.py`, docs in `docs/cli.md` and examples/README as user-visible.
- **New Qobuz endpoint:** add wrapper in `qobuz_dl/qopy.py` while keeping network through `qobuz_dl/http.py`; add mocked tests in `tests/test_qopy_characterization.py` or a new focused test. Avoid bypassing `qobuz_dl/http.py` (`docs/dependencies.md:99-101`).
- **New URL/source type:** `qobuz_dl/utils.py:get_url_info` and/or `QobuzDL.download_list_of_urls`/`handle_url` in `qobuz_dl/core.py`; add fixture/mocked tests for routing and docs under `docs/cli.md`/`docs/examples.md`.
- **Download organization/quality/tagging:** `qobuz_dl/downloader.py` owns album/track download flow, quality checks, cover/booklet downloads, filename formats, temp files; `qobuz_dl/metadata.py` owns audio tags; `qobuz_dl/sanitize.py` owns generated name sanitization.
- **Duplicate tracking changes:** `qobuz_dl/db.py` and `QobuzDL.download_from_id`; validate with `tests/test_db.py` and command tests around `--no-db`/`--purge`.
- **Search UX changes:** `QobuzDL.search_by_type`, `lucky_mode`, and `interactive`; tests should mock `search_by_type`/client responses and avoid real terminal/network.
- **Dependency removal/addition:** follow `docs/dependencies.md`; add characterization tests first, update `pyproject.toml`, `requirements.txt`, `uv.lock`, and docs; run `just ci`.
