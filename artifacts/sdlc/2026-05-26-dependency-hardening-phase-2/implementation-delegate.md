# Dependency Hardening Phase 2 — Implementation Delegate Handoff

## Changed files

Phase 2 writer changes were limited to characterization tests, small fixtures, and testing docs:

- `tests/test_sanitization_characterization.py`
- `tests/test_lastfm_characterization.py`
- `tests/test_qopy_characterization.py`
- `tests/test_bundle_downloader_characterization.py`
- `tests/test_terminal_interactive_characterization.py`
- `tests/test_metadata_characterization.py`
- `tests/fixtures/lastfm_playlist.html`
- `tests/fixtures/lastfm_empty_playlist.html`
- `docs/testing.md`
- `artifacts/sdlc/2026-05-26-dependency-hardening-phase-2/implementation-delegate.md`

The worktree already had many intentional baseline changes before this task; I did not clean, revert, or reformat unrelated files.

## Acceptance criteria coverage

- **AC-1 Sanitization:** Added tests for current `pathvalidate` behavior for album/artist folder attrs, track folder/filename attrs, playlist/artist URL directory creation, illegal filename characters, and empty/whitespace-heavy generated names. Tests use pure helpers/temp dirs and stub downloads.
- **AC-2 Last.fm parsing:** Added small static Last.fm HTML fixtures and tests that monkeypatch `qobuz_dl.core.requests.get`, `search_by_type`, `download_from_id`, and `make_m3u`. Coverage includes sanitized playlist title, artist/title query formation, download calls, and no-usable-track-list behavior.
- **AC-3 Qobuz API client HTTP:** Added fake session/response tests for `qopy.Client.api_call` success endpoint/params, login status mapping, invalid app secret mapping, invalid quality pre-HTTP rejection, and header setup via faked auth/secret setup.
- **AC-4 Bundle/download HTTP-adjacent:** Added fake Qobuz login HTML and compact bundle JS tests for app ID and readable secret extraction. Added streamed download tests for successful writes and short-stream `ConnectionError`, with `tqdm` replaced by a no-op fake.
- **AC-5 Interactive/terminal boundary:** Added color constant string tests and a shallow interactive selected-item flow using a fake `pick` module plus fake `input`; verifies returned URLs and no download call when `download=False`. Curses/real-terminal behavior remains intentionally out of scope.
- **AC-6 Metadata formatting:** Added pure helper tests for version/classical work title formatting, genre normalization, and current copyright marker replacement behavior. No binary media fixtures added.
- **AC-7 Proof/docs:** Added `docs/testing.md` fixture/mock conventions. No runtime dependencies changed or production code changed.

## Validation commands run

- `uv run pytest tests/test_sanitization_characterization.py tests/test_lastfm_characterization.py tests/test_qopy_characterization.py tests/test_bundle_downloader_characterization.py tests/test_terminal_interactive_characterization.py tests/test_metadata_characterization.py`
  - First run: exit 1; test expectation issues fixed.
  - Final run: exit 0; `19 passed`.
- `just test`
  - Exit 0; `26 passed`.
- `just ci`
  - First run: exit 1; `ruff format --check` wanted formatting in two new test files.
  - Second run: exit 1; Ruff found one unused import in a new test file.
  - Final run: exit 0; format check, lint, pytest, CLI smoke, and `uv build` all passed.
- `rg "requests.get|Session\(|last.fm|qobuz.com" tests -n && git diff --stat`
  - Exit 0. Inspected hits: network-looking references are mocked/faked/static URLs in tests. Existing parser tests contain example Qobuz URLs only. No live network calls are introduced.
- `git status --short`
  - Confirms the repo remains dirty from the intentional baseline plus new Phase 2 files under untracked `tests/`, `docs/testing.md`, and this artifact.

## Failures/unfixed issues

- No remaining test/lint/build failures from the final `just ci` run.
- Interactive real curses/terminal behavior is not tested by design.
- The tests characterize current behavior, including quirks such as private helper usage and current copyright marker mapping, rather than prescribing ideal future behavior.

## Decisions needed

None for Phase 2. The implementation stayed within approved scope and did not require production seams.
