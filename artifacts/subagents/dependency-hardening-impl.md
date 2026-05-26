# Dependency hardening phases 3-6 implementation handoff

## Files changed by this implementation slice

Production/code:
- `qobuz_dl/color.py`
- `qobuz_dl/core.py`
- `qobuz_dl/downloader.py`
- `qobuz_dl/bundle.py`
- `qobuz_dl/qopy.py`
- `qobuz_dl/http.py` (new stdlib urllib boundary)
- `qobuz_dl/sanitize.py` (new project-owned sanitizer)

Tests:
- `tests/test_sanitization_characterization.py`
- `tests/test_bundle_downloader_characterization.py`
- `tests/test_lastfm_characterization.py`
- `tests/test_qopy_characterization.py`
- `tests/test_terminal_interactive_characterization.py`

Runtime metadata/docs:
- `pyproject.toml`
- `requirements.txt`
- `uv.lock`
- `docs/dependencies.md`
- `docs/packaging.md`
- `docs/examples.md`
- `docs/cli.md`

Existing unrelated working tree changes were treated as baseline and not reverted.

## AC coverage

- AC-1: Covered. No production imports of `colorama`, `pathvalidate`, `tqdm`, `pick`, `bs4`/`BeautifulSoup`, or `requests` remain.
- AC-2: Covered. `qobuz_dl/color.py` exports `DF`, `BG`, `RESET`, `OFF`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `CYAN`, `MAGENTA` as strings.
- AC-3: Covered by sanitizer tests; project-owned `qobuz_dl/sanitize.py` preserves characterized generated path/name behavior.
- AC-4: Covered. `tqdm_download` now delegates to project HTTP streaming and keeps content-length mismatch `ConnectionError` behavior; tests do not rely on terminal rendering.
- AC-5: Covered. Interactive mode uses built-in prompts with numbered choices, comma/range multiselect, yes/no continuation, quality choice, and clean `KeyboardInterrupt` cancel.
- AC-6: Covered. Last.fm parsing uses `html.parser` with fixtures for populated and empty playlists.
- AC-7: Covered. HTTP calls go through `qobuz_dl/http.py` for JSON API responses, text fetches, and streamed downloads, with project-owned HTTP errors.
- AC-8: Covered by offline fake tests for qopy mapping/signatures/headers/auth token, invalid quality, bundle extraction, Last.fm fetch/parsing, and downloader streaming.
- AC-9: Covered. Runtime metadata removes the targeted dependencies; `mutagen>=1.47,<2` remains. `uv.lock` refreshed.
- AC-10: Covered. `docs/dependencies.md` and `docs/packaging.md` updated; `docs/examples.md`/`docs/cli.md` updated for material interactive prompt changes.
- AC-11: Covered. Default tests remain offline with fakes/fixtures only.
- AC-12: Covered. Final `just ci` passed.

## Commands run and exit codes

- `git status --short && find docs/sdlc/2026-05-26-dependency-hardening -maxdepth 1 -type f -print | sort` — exit 0
- `just test` baseline before edits — exit 0, 28 passed
- `just test` after implementation — exit 0, 30 passed
- `just lint` — exit 0
- `uv lock` — exit 0
- `uv tree --no-dev` — exit 0; output showed only `qobuz-dl -> mutagen v1.47.0`
- `just ci` first run — exit 1; formatting check reported 3 files needing reformat
- `just fmt` — exit 0; reformatted 3 files
- `just ci` final — exit 0; format check, lint, pytest, CLI smoke help, and build all passed
- Targeted greps for forbidden production imports — exit 1/no matches (expected): no active production imports of removed dependencies

## Validation evidence

- Final `just ci` passed with:
  - Ruff format check: 23 files already formatted
  - Ruff lint: all checks passed
  - Pytest: 30 passed
  - CLI smoke: `qobuz-dl --help`, `dl --help`, `fun --help`, `lucky --help`
  - `uv build`: completed successfully
- `uv tree --no-dev` resolved runtime tree to:
  - `qobuz-dl v0.9.9.10`
  - `mutagen v1.47.0`
- Production forbidden-import grep returned no matches.

## Known remaining risks

- `qobuz_dl/http.py` intentionally preserves narrow current behavior, including raising on content-length mismatch. Missing content-length behavior remains strict, matching the old characterized path.
- The Last.fm parser is deliberately small and fixture-driven; unsupported Last.fm HTML shapes may fail by producing no tracks rather than attempting broad scraping.
- Built-in interactive prompts are less visually rich than `pick`, but preserve approved behavior without adding optional UI dependencies.
- `uv.lock` still includes `colorama` as a Windows-only transitive dev dependency of `pytest`; it is not a runtime dependency and is absent from `uv tree --no-dev`.

## Decisions needing parent/user approval

None. Approved decisions were followed: stdlib replacements, built-in prompts, built-in Last.fm parser, stdlib urllib HTTP boundary, and retained bounded `mutagen>=1.47,<2`.
