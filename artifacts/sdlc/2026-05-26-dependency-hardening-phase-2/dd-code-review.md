# Dependency Hardening Phase 2 — Independent Code Review

## Scope reviewed

Read-only review of the current repository state after Phase 2 implementation. Reviewed:

- `AGENTS.md`
- `docs/sdlc/2026-05-26-dependency-hardening/impl-plan-phase-2-dependency-hardening.md`
- `artifacts/sdlc/2026-05-26-dependency-hardening-phase-2/acceptance-criteria.md`
- `artifacts/sdlc/2026-05-26-dependency-hardening-phase-2/implementation-delegate.md`
- `artifacts/sdlc/2026-05-26-dependency-hardening-phase-2/scope-explorer.md`
- New Phase 2 tests and fixtures under `tests/`
- `docs/testing.md` and related changed docs relevant to testing/dependency hardening

## Checks run

- `git status --short` — repo remains dirty with intentional baseline changes plus Phase 2 additions.
- `uv run pytest tests/test_sanitization_characterization.py tests/test_lastfm_characterization.py tests/test_qopy_characterization.py tests/test_bundle_downloader_characterization.py tests/test_terminal_interactive_characterization.py tests/test_metadata_characterization.py` — passed, `19 passed`.
- `just ci` — passed: Ruff format, Ruff lint, pytest `26 passed`, CLI smoke, and `uv build`.
- `rg "requests.get|Session\(|last.fm|qobuz.com" tests -n` — inspected hits; network-looking references are mocked/faked/static examples.

## Verdict

Ready with fixes worth doing now. No blocker found that invalidates Phase 2, and the new tests are deterministic/offline. The main risk is that a couple of tests are weaker than the dependency-hardening intent: they characterize helper/dependency calls but would miss some production-path regressions.

## Blockers

None.

## Fixes worth doing now

### P2 — Sanitization tests can miss production-path removal of sanitization

**Files:**

- `tests/test_sanitization_characterization.py`
- production paths being characterized: `qobuz_dl/downloader.py:97-103`, `qobuz_dl/downloader.py:146-154`, `qobuz_dl/downloader.py:217-218`

**Issue:** The downloader sanitization tests assert private helper output plus direct `pathvalidate.sanitize_filename` / `sanitize_filepath` calls in the test. That documents current dependency behavior, but it does not fully prove that the downloader production paths still apply sanitization when creating album/track folders or final track filenames.

A future change could remove `sanitize_filepath(...)` from `download_album` / `download_track`, or remove `sanitize_filename(...)` from `_download_and_tag`, while these tests would still pass because the test itself applies `pathvalidate`.

**Recommended fix:** Add one compact temp-dir/monkeypatch test that exercises actual `Download.download_track()` or `_download_and_tag()` enough to observe the created directory/final file path, with `tqdm_download` and taggers faked. This would better satisfy AC-1’s “where generated names become filesystem paths” intent without requiring real downloads/media.

### P2 — Qobuz `track/getFileUrl` request-signature behavior is under-characterized

**Files:**

- `tests/test_qopy_characterization.py`
- production path: `qobuz_dl/qopy.py:79-99`

**Issue:** The invalid-app-secret test verifies endpoint, `track_id`, `format_id`, and `intent`, but not that `request_ts` and `request_sig` are included or computed from the current algorithm. A future HTTP-boundary change could omit signing parameters and this test could still pass as long as the fake response returns status `400`.

**Recommended fix:** In `test_track_file_url_invalid_app_secret_mapping`, freeze or monkeypatch `time.time()` and assert `request_ts` plus either exact `request_sig` or at least deterministic signature presence/shape. Exact signature is acceptable here because the signature algorithm is current dependency/API boundary behavior that Phase 5 must preserve or intentionally replace.

## Optional deferrals

### P3 — Last.fm “Qobuz search returns no result” behavior remains undocumented

**Files:**

- `tests/test_lastfm_characterization.py`
- production path: `qobuz_dl/core.py:388-393`

The tests cover the no-usable-track-list path when the fixture lacks matching artist/title pairs. They do not cover the current behavior when Last.fm parsing succeeds but `search_by_type(..., lucky=True)` returns an empty list. Current code indexes `[0]`, so the behavior appears to be an `IndexError` rather than a graceful skip. This is not clearly required by official AC-2, but documenting it before parser/HTTP changes would reduce ambiguity.

### P3 — Terminal/color characterization is intentionally shallow

**Files:**

- `tests/test_terminal_interactive_characterization.py`
- `qobuz_dl/color.py`

The color test only verifies exported constants are strings. This matches AC-5’s lightweight boundary, but it will not catch accidental semantic swaps of specific constants. Deferring is reasonable unless Phase 4 plans to replace `colorama` directly.

## Positive findings

- Tests are offline by construction: Qobuz, Last.fm, streamed media, `pick`, and `tqdm` are all faked/mocked in the new characterization tests.
- No runtime dependency was removed/replaced/optionalized in Phase 2.
- The Last.fm fixtures are small and readable.
- Bundle/download tests avoid terminal progress rendering assertions and verify the important streamed-write/short-stream behavior.
- Metadata tests avoid binary media fixtures and stay limited to pure formatting helpers.
- `docs/testing.md` now documents durable fixture/mock conventions consistent with the added tests.
