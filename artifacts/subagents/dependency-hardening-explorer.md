Read-only findings for dependency hardening phases 3–6 in `/Users/andy16/Documents/github_local/qobuz-dl`.

Note: I did **not** write `/artifacts/subagents/dependency-hardening-explorer.md` because the task also said “Do not edit files”; read-only/no-edit wins.

## Current dependency usage/imports

Active runtime deps in `pyproject.toml` / `requirements.txt`:

- `beautifulsoup4`
  - `qobuz_dl/core.py`: `BeautifulSoup as bso`
  - Used only by `download_lastfm_pl()` for Last.fm playlist HTML parsing.
- `colorama`
  - `qobuz_dl/color.py`: `Fore`, `Style`, `init(autoreset=True)`
  - Centralized constants: `DF`, `BG`, `RESET`, `OFF`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `CYAN`, `MAGENTA`.
- `mutagen`
  - `qobuz_dl/metadata.py`: FLAC/ID3 write/tag/embed behavior.
  - `qobuz_dl/utils.py`: reads MP3/FLAC metadata for `.m3u` generation.
- `pathvalidate`
  - `qobuz_dl/core.py`: `sanitize_filename()` for playlist/artist/label directories.
  - `qobuz_dl/downloader.py`: `sanitize_filename()`, `sanitize_filepath()` for album folders, track folders, final filenames, album/artist attrs.
- `pick==1.6.0`
  - `qobuz_dl/core.py`: imported inside `QobuzDL.interactive()`.
  - Search type selection, multiselect results, continue prompt, quality prompt.
- `requests`
  - `qobuz_dl/qopy.py`: `requests.Session()` for Qobuz API.
  - `qobuz_dl/bundle.py`: `Session` for Qobuz web bundle scraping.
  - `qobuz_dl/core.py`: Last.fm fetch and `RequestException` handling.
  - `qobuz_dl/downloader.py`: media/extra download and `HTTPError` catch in `_get_format()`.
- `tqdm`
  - `qobuz_dl/downloader.py`: progress bar in `tqdm_download()`.

## Characterization tests present

- `tests/test_sanitization_characterization.py`
  - Captures current `pathvalidate` behavior for illegal filename/path chars, empty/whitespace names, album/track folder attrs, final file paths, playlist/artist handle URL directories.
- `tests/test_bundle_downloader_characterization.py`
  - Fake Qobuz bundle HTML/JS for app ID + compact secret extraction.
  - Fake streamed download for `tqdm_download()`: successful write and short-stream `ConnectionError`.
- `tests/test_lastfm_characterization.py`
  - Static fixtures under `tests/fixtures/`.
  - Mocks `requests.get`, verifies Last.fm title sanitization, search queries, track downloads, no-track behavior.
- `tests/test_qopy_characterization.py`
  - Fake sessions/responses for `Client.api_call()`.
  - Covers endpoint params, login error mapping, invalid app secret, invalid quality pre-network rejection, init header updates.
- `tests/test_terminal_interactive_characterization.py`
  - Verifies exported color constants are strings.
  - Mocks `pick` + `input` for one interactive selected-result path without download.
- `tests/test_metadata_characterization.py`
  - Pure metadata formatting only: title/version/work, genres, copyright symbols, download description.
- Existing baseline tests:
  - `tests/test_commands.py`, `tests/test_db.py`, `tests/test_imports.py`.

## Likely blockers before Phase 3

- Phase 2 safety net exists, but some tests directly import/monkeypatch dependencies targeted for removal:
  - `test_sanitization_characterization.py` imports `pathvalidate` directly.
  - downloader tests monkeypatch `qobuz_dl.downloader.tqdm`.
  - after replacement, tests must be updated to assert project-owned behavior while preserving characterized outputs.
- `colorama.init(autoreset=True)` behavior is implicit; replacing constants with raw ANSI may leak colors unless output sites continue to include resets or policy is explicit.
- Sanitizer replacement must carefully match current visible behavior:
  - illegal chars are removed, not replaced;
  - whitespace-only and all-invalid names become `""`;
  - final file path truncation remains in `_download_and_tag()` via `[:250] + extension`.
- `tqdm_download()` currently has both progress and correctness responsibilities; preserve streamed writes and short-download `ConnectionError` before changing display.
- Do not start Phase 4 decisions silently:
  - `pick`: simple prompts vs optional rich UI needs approval.
  - Last.fm: small parser vs optional `beautifulsoup4` also needs approval.
- Phase 5 is not ready until an HTTP boundary design is approved; current tests still patch `requests`-shaped seams.

## Recommended acceptance criteria / proof commands

Phase 3 readiness/proof:

```bash
uv run pytest tests/test_sanitization_characterization.py
uv run pytest tests/test_terminal_interactive_characterization.py
uv run pytest tests/test_bundle_downloader_characterization.py
just test
```

After each Phase 3 dependency removal:

```bash
uv run qobuz-dl --help
rg "from colorama|import colorama|from pathvalidate|import pathvalidate|from tqdm|import tqdm" qobuz_dl tests -n
just test
```

After metadata/lock/docs cleanup:

```bash
uv sync --dev
uv tree --no-dev
rg '"colorama"|"pathvalidate"|"tqdm"|^colorama$|^pathvalidate$|^tqdm$' pyproject.toml requirements.txt uv.lock
just ci
```

Phase 4–6 later proof should add:

```bash
rg "BeautifulSoup|bs4|beautifulsoup4|from pick|import pick|pick==" qobuz_dl tests pyproject.toml requirements.txt docs -n
rg "import requests|from requests|requests\\." qobuz_dl tests -n
rg "mutagen" pyproject.toml requirements.txt docs/dependencies.md qobuz_dl tests -n
just ci
```