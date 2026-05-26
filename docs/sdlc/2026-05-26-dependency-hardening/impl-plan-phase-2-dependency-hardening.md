# Implementation Plan: Dependency Hardening Phase 2

## Overview

Implement Phase 2 of dependency hardening: add characterization tests around dependency-owned behavior before removing or replacing dependencies. This phase should make current behavior observable and reproducible without changing runtime dependency choices yet.

The goal is not broad coverage. The goal is a focused test net that makes later dependency removals safer: sanitization, Last.fm parsing, HTTP behavior, streamed downloads/progress, interactive selection boundaries, and lightweight metadata formatting.

## Source Inputs

- `docs/sdlc/2026-05-26-dependency-hardening/vision-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/architecture-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/impl-plan-phase-1-dependency-hardening.md`
- `docs/dependencies.md`
- Existing tests under `tests/`
- Current implementation in `qobuz_dl/core.py`, `qobuz_dl/downloader.py`, `qobuz_dl/qopy.py`, `qobuz_dl/bundle.py`, `qobuz_dl/color.py`, `qobuz_dl/metadata.py`, and `qobuz_dl/utils.py`

## Non-Goals

- Do not remove, replace, optionalize, or vendor dependencies in this phase.
- Do not rewrite HTTP behavior or introduce the final internal HTTP boundary yet.
- Do not replace `pick` interaction behavior yet.
- Do not replace `beautifulsoup4` parsing yet.
- Do not replace or fork `mutagen`.
- Do not add tests that require Qobuz credentials, live Qobuz API calls, live Last.fm pages, active subscriptions, or real media downloads.
- Do not add large binary media fixtures unless a later metadata-specific plan approves them.

## Architecture / Contract Notes

- Default tests must use mocks, fakes, fixtures, and temporary directories.
- Tests should target current user-visible behavior or current dependency boundaries, not implementation trivia.
- Where current code lacks a clean seam, use monkeypatching rather than refactoring in this phase.
- Tiny production-code seams are acceptable only when monkeypatching becomes brittle or unreadable, runtime behavior stays unchanged, and no dependency replacement sneaks in.
- If a behavior is too awkward to test without redesign, document that as a Phase 3/4/5 blocker rather than hiding it.
- `just ci` remains the full local proof command.

## Execution Guidance

- Treat the current working tree as intentional baseline. Do not clean, revert, reformat, or fix unrelated existing changes while executing this phase.
- Execute Task 1 first, then checkpoint before continuing. Do not attempt Tasks 1–7 in one large pass unless explicitly approved later.
- For Task 1, keep network mocking local; a global offline test guard is not required yet.
- Consider a global/offline network guard around Tasks 3–4 only if repeated HTTP-adjacent tests make it useful and it does not create noisy failures in existing tests.
- For interactive multiselect and bundle secret extraction, try a reasonable compact test first. If it becomes brittle or contorted, defer explicitly rather than forcing fragile tests.
- Update `docs/testing.md` in the same pass only when a durable convention is introduced, such as `tests/fixtures/` layout or a reusable HTTP/mock pattern. One-off local helpers do not need docs yet.

## Task List

### Task 1: Characterize filename and path sanitization behavior

**Description:** Add tests that lock the current filename/path behavior delegated to `pathvalidate` at the places where generated names become filesystem paths.

**Acceptance Criteria:**

- [ ] Tests cover illegal filename characters relevant to generated album, artist, playlist, and track names.
- [ ] Tests cover empty or whitespace-heavy generated names where current behavior is important.
- [ ] Tests cover path formatting through downloader helpers enough to protect folder and track filename outputs.
- [ ] Tests avoid real downloads and use temporary directories or pure helper calls only.
- [ ] Tests make clear which expectations are current behavior, not necessarily ideal future behavior.

**Verification:**

- [ ] Run `uv run pytest tests/test_*sanitize*.py` or the actual new test file path.
- [ ] Run `just test`.
- [ ] Confirm no network calls are made.

**Dependencies:** None

**Likely Touch Surface:**

- `tests/`
- `qobuz_dl/downloader.py` only if a tiny test seam is unavoidable; avoid production changes if possible
- `qobuz_dl/core.py` only if a tiny test seam is unavoidable; avoid production changes if possible

**Estimated Scope:** M

**Why:** One high-value behavior surface, several edge cases, clear regression value for the future `pathvalidate` removal, no product behavior change.

### Task 2: Characterize Last.fm playlist parsing with static fixtures

**Description:** Add fixture-based tests for `download_lastfm_pl` so the current BeautifulSoup-backed extraction of playlist title, artists, and track names is protected without live Last.fm access.

**Acceptance Criteria:**

- [ ] A static Last.fm-like HTML fixture exists under `tests/fixtures/` or equivalent.
- [ ] Tests mock `requests.get` and do not fetch Last.fm live.
- [ ] Tests verify that playlist title sanitization and artist/title pairing produce the expected search queries or download calls.
- [ ] Tests cover the “nothing found” path when artists and titles do not produce a usable track list.
- [ ] Tests avoid real Qobuz search/download behavior by stubbing `search_by_type` and `download_from_id`.

**Verification:**

- [ ] Run the new Last.fm parsing tests directly.
- [ ] Run `just test`.
- [ ] Confirm the fixture is small and readable enough to update if Last.fm page assumptions change.

**Dependencies:** Task 1 is helpful if the test asserts sanitized playlist directory names, but not strictly required.

**Likely Touch Surface:**

- `tests/fixtures/`
- `tests/test_lastfm_characterization.py` or similar
- `qobuz_dl/core.py` only if a tiny test seam is unavoidable; avoid production changes if possible

**Estimated Scope:** M

**Why:** One secondary feature, mocked network, protects the future `beautifulsoup4` replacement or optionalization path.

### Task 3: Characterize Qobuz API client HTTP behavior with fake responses

**Description:** Add tests around `qobuz_dl.qopy.Client.api_call` behavior using fake sessions/responses so future HTTP boundary work can preserve status handling, JSON handling, headers, request signatures, and exception mapping.

**Acceptance Criteria:**

- [ ] Tests avoid constructing a real authenticated client unless authentication calls are fully faked.
- [ ] Tests cover at least one successful JSON API call with expected endpoint and params.
- [ ] Tests cover login-specific status handling for invalid credentials or invalid app ID.
- [ ] Tests cover invalid app secret handling for `track/getFileUrl` or secret testing behavior.
- [ ] Tests cover invalid quality handling without network access.
- [ ] Tests assert that no live `requests.Session` call is needed.

**Verification:**

- [ ] Run the new qopy/API client tests directly.
- [ ] Run `just test`.
- [ ] Inspect tests to confirm credentials, subscription, and live Qobuz are not required.

**Dependencies:** None

**Likely Touch Surface:**

- `tests/test_qopy_characterization.py` or similar
- `qobuz_dl/qopy.py` only if a tiny seam is unavoidable; avoid production changes if possible

**Estimated Scope:** M

**Why:** HTTP behavior is high risk for Phase 5. This creates early proof without designing the final HTTP abstraction yet.

### Task 4: Characterize bundle scraping and streamed download behavior

**Description:** Add tests for the remaining HTTP-adjacent behavior: Qobuz bundle extraction in `Bundle` and streamed file download behavior in `tqdm_download`.

**Acceptance Criteria:**

- [ ] Bundle tests use fake HTML and fake bundle JavaScript; no live `play.qobuz.com` request occurs.
- [ ] Bundle tests verify app ID extraction from fake login HTML and fake bundle JavaScript.
- [ ] Bundle tests verify secret extraction only if a compact representative fixture can be made readable; otherwise they document secret extraction as a targeted follow-up before Phase 5.
- [ ] Download tests fake `requests.get`, response headers, and `iter_content`.
- [ ] Download tests verify successful streamed writes to a temporary file.
- [ ] Download tests verify interrupted download behavior raises `ConnectionError` when content length and bytes written differ.
- [ ] Download tests avoid relying on actual terminal progress rendering.

**Verification:**

- [ ] Run the new bundle/download characterization tests directly.
- [ ] Run `just test`.
- [ ] Confirm no live HTTP calls and no real media downloads occur.

**Dependencies:** None

**Likely Touch Surface:**

- `tests/test_bundle_characterization.py` or similar
- `tests/test_downloader_characterization.py` or similar
- `qobuz_dl/bundle.py` only if a tiny seam is unavoidable; avoid production changes if possible
- `qobuz_dl/downloader.py` only if a tiny seam is unavoidable; avoid production changes if possible

**Estimated Scope:** M

**Why:** This covers both bundle scraping and the download/progress path that later `requests` and `tqdm` changes can easily break.

### Task 5: Characterize interactive and terminal output boundaries lightly

**Description:** Add lightweight tests for current terminal color constants and the `pick`-based interactive boundary where feasible, without trying to fully automate terminal UI behavior.

**Acceptance Criteria:**

- [ ] Tests cover that `qobuz_dl.color` exposes the constants used by the rest of the application as strings.
- [ ] Interactive tests mock `pick`, `input`, and search results where feasible to verify a simple selected-item flow returns expected URLs when `download=False`.
- [ ] Tests cover the Windows missing-`pick` message only if it can be done without platform-fragile hacks; otherwise document that it is deferred.
- [ ] Tests do not require curses, a real terminal, or manual input.
- [ ] Any untested interactive behavior is explicitly listed as a later Phase 4 review point.

**Verification:**

- [ ] Run the new color/interactive tests directly.
- [ ] Run `just test`.
- [ ] Confirm tests are not flaky in non-interactive CI.

**Dependencies:** None

**Likely Touch Surface:**

- `tests/test_terminal_characterization.py` or similar
- `tests/test_interactive_characterization.py` or similar
- `qobuz_dl/core.py` only if a tiny seam is unavoidable; avoid production changes if possible

**Estimated Scope:** S

**Why:** This creates enough protection for future `colorama` and `pick` decisions without over-investing in terminal UI automation.

### Task 6: Add lightweight metadata formatting characterization

**Description:** Add tests for pure metadata formatting helpers so retained `mutagen` behavior has a small safety net without introducing binary media fixtures.

**Acceptance Criteria:**

- [ ] Tests cover metadata title formatting with versions and classical work names.
- [ ] Tests cover genre normalization from Qobuz genre lists.
- [ ] Tests cover copyright symbol replacement.
- [ ] Tests do not create or mutate real MP3/FLAC media files.
- [ ] Tests document that full binary tag writing remains out of scope for Phase 2.

**Verification:**

- [ ] Run the new metadata formatting tests directly.
- [ ] Run `just test`.
- [ ] Confirm no large binary fixtures were added.

**Dependencies:** None

**Likely Touch Surface:**

- `tests/test_metadata_characterization.py` or similar
- `qobuz_dl/metadata.py` only if helper visibility becomes a lint/test issue; avoid production changes if possible

**Estimated Scope:** S

**Why:** `mutagen` remains retained, but these pure helper tests protect metadata formatting logic without pretending to solve binary tagging coverage.

### Task 7: Run the full Phase 2 proof gate and update test docs if needed

**Description:** Run the full local quality gate after characterization tests are added, then update testing documentation only if new test conventions or fixture locations need to be durable.

**Acceptance Criteria:**

- [ ] `just test` succeeds.
- [ ] `just ci` succeeds.
- [ ] New tests are deterministic and do not depend on network, credentials, active subscriptions, terminal UI, or real downloads.
- [ ] Fixture locations or mocking conventions are documented in `docs/testing.md` only if they are important for future contributors.
- [ ] No runtime dependency is removed or replaced in this phase.

**Verification:**

- [ ] Run `just test`.
- [ ] Run `just ci`.
- [ ] Run `rg "requests.get|Session\(|last.fm|qobuz.com" tests -n` and inspect hits to confirm they are mocked/faked, not live network calls.
- [ ] Run `git diff --stat` and confirm the changed files match Phase 2 boundaries.

**Dependencies:** Tasks 1–6

**Likely Touch Surface:**

- `tests/`
- `tests/fixtures/`
- `docs/testing.md` only if new fixture/mock conventions need durable documentation

**Estimated Scope:** S

**Why:** One final validation and optional docs sync; no new behavior beyond the test net.

## Checkpoints

- [ ] After Task 1: Checkpoint before continuing to Task 2; confirm the new tests are scoped to sanitization and do not touch unrelated baseline changes.
- [ ] After Tasks 1–2: Check that sanitization and Last.fm tests are not over-coupled to implementation internals.
- [ ] After Tasks 3–4: Review HTTP-adjacent tests before Phase 5 planning; these tests must prove behavior, not requests-specific trivia that would block migration.
- [ ] After Task 5: Human review if interactive multiselect behavior cannot be tested cleanly; do not force brittle terminal tests.
- [ ] After Task 7: Run `pa-code-review` because this phase adds the safety net that later dependency-removal work will rely on.

## Risks and Mitigations

- **Risk:** Tests overfit to third-party internals instead of project behavior.
  - **Impact:** High
  - **Mitigation:** Assert generated names, returned URLs, raised project/domain errors, files written, and parsed outputs. Avoid asserting implementation-only call order unless it is the behavior being preserved.

- **Risk:** Mocking accidentally allows live network calls.
  - **Impact:** High
  - **Mitigation:** Use fake sessions/responses and inspect tests for `requests.get`, `Session`, `qobuz.com`, and `last.fm` references. Default tests must stay offline.

- **Risk:** Interactive tests become flaky in CI.
  - **Impact:** Medium
  - **Mitigation:** Keep interactive characterization shallow. Mock `pick` and `input`; defer anything that needs curses or a real terminal.

- **Risk:** Metadata tests imply `mutagen` replacement readiness.
  - **Impact:** Medium
  - **Mitigation:** Limit Phase 2 to pure formatting helpers and explicitly state that binary tag writing fixtures are deferred.

- **Risk:** Test seams become production refactors.
  - **Impact:** Medium
  - **Mitigation:** Prefer monkeypatching. If a seam is necessary, keep it tiny, boring, and behavior-preserving.

- **Risk:** Phase 2 work accidentally absorbs unrelated baseline changes from the already-dirty working tree.
  - **Impact:** Medium
  - **Mitigation:** Treat existing changes as intentional baseline, inspect `git diff --stat`, and keep Phase 2 edits limited to tests, fixtures, tiny seams, and optional testing docs.

## Open Questions

- Whether interactive multiselect behavior can be tested cleanly without brittle terminal simulation. This does not block Phase 2; if it is awkward, document it as a Phase 4 review point.
- Whether bundle secret extraction can be represented with a compact fixture. This does not block Phase 2 if app ID extraction is covered and secret extraction is explicitly marked as a targeted follow-up before Phase 5.

## Recommended Next Phase

`pa-tdd` for Task 1 first, then continue through the characterization surfaces in risk order. After Phase 2 passes `just ci` and review, move to a new `pa-plan-slicer` plan for Phase 3: low-risk utility dependency removals.
