# Dependency Hardening Phase 2 — Completion Audit

## Deliverable

Implemented Phase 2 characterization tests around dependency-owned behavior without removing, replacing, optionalizing, or vendoring runtime dependencies.

## Files added/updated in Phase 2

- `tests/test_sanitization_characterization.py`
- `tests/test_lastfm_characterization.py`
- `tests/test_qopy_characterization.py`
- `tests/test_bundle_downloader_characterization.py`
- `tests/test_terminal_interactive_characterization.py`
- `tests/test_metadata_characterization.py`
- `tests/fixtures/lastfm_playlist.html`
- `tests/fixtures/lastfm_empty_playlist.html`
- `docs/testing.md`
- `artifacts/sdlc/2026-05-26-dependency-hardening-phase-2/*`

Existing broader working-tree changes were treated as intentional baseline.

## AC evidence

- AC-1 Sanitization: covered by `tests/test_sanitization_characterization.py`, including helper behavior, empty/illegal names, `QobuzDL.handle_url()`, and a production-path `Download.download_track()` test with fake downloader/tagger functions.
- AC-2 Last.fm parsing: covered by static fixtures in `tests/fixtures/` and mocked `qobuz_dl.core.requests.get`, search, download, and M3U boundaries.
- AC-3 Qobuz API client HTTP: covered by fake session/response tests in `tests/test_qopy_characterization.py`, including endpoint params, login status mapping, invalid secret handling, invalid quality pre-HTTP rejection, headers, and deterministic `track/getFileUrl` signing params.
- AC-4 Bundle/download HTTP-adjacent: covered by fake `qobuz_dl.bundle.Session`, compact fake bundle JS, fake streamed `requests.get`, no-op `tqdm`, successful writes, and short-stream `ConnectionError`.
- AC-5 Interactive/terminal boundary: covered by color constant string assertions and fake `pick`/`input` interactive flow returning selected URLs without downloading.
- AC-6 Metadata formatting: covered by pure helper tests for titles, versions/classical work names, genre normalization, and copyright marker behavior.
- AC-7 Proof/docs: `docs/testing.md` documents durable fixture/mock conventions; final checks pass.

## Validation

Final commands run by parent:

```text
uv run pytest tests/test_sanitization_characterization.py tests/test_qopy_characterization.py
10 passed

just test
27 passed

just ci
passed: ruff format check, ruff lint, pytest 27 passed, top-level CLI smoke, uv build

rg "requests.get|Session\(|last.fm|qobuz.com" tests -n
24 hits inspected: all are monkeypatched/faked/static example URLs, not live network calls.

rg "\.mp3|\.flac|cover.jpg" tests -n
6 hits inspected: temp filenames or static fake URLs only; no binary fixtures or real media operations.
```

## Review and repairs

- Initial implementation delegate completed all Phase 2 tests and docs.
- Independent DD found no blockers and two P2 strengthening fixes.
- Repair delegate added production-path downloader sanitization coverage and deterministic Qobuz signing assertions.
- Post-repair reviewers found the P2 issues resolved; one formatting/import-sort blocker was fixed by parent with `uv run ruff check ... --fix`.

## Remaining risks / deferrals

- Real curses/terminal behavior remains intentionally out of scope.
- Full binary MP3/FLAC metadata writing remains intentionally out of scope.
- Last.fm behavior when parsing succeeds but Qobuz search returns no results remains a documented optional follow-up, not an AC blocker.
- `docs/testing.md`/`justfile` smoke wording mismatch was noted by DD as advisory; not part of Phase 2 characterization scope.
