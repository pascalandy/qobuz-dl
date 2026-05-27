# Implementation Plan: Dependency Hardening Phase 3

## Overview

Implement Phase 3 of dependency hardening: remove the low-risk utility dependencies whose used behavior is small enough for this project to own directly.

Phase 3 targets:

- `colorama` — terminal color constants and reset behavior
- `pathvalidate` — filename and filepath sanitization
- `tqdm` — download progress display

This phase should not change the downloader's core behavior. It should replace each dependency with small project-owned code, keep the Phase 2 characterization tests passing, update dependency metadata, and refresh docs and lockfiles.

## Source Inputs

- `docs/sdlc/2026-05-26-dependency-hardening/vision-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/architecture-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/impl-plan-phase-2-dependency-hardening.md`
- `docs/dependencies.md`
- Phase 2 characterization tests under `tests/`
- Current implementation in `qobuz_dl/color.py`, `qobuz_dl/core.py`, and `qobuz_dl/downloader.py`
- Current dependency declarations in `pyproject.toml`, `requirements.txt`, and `uv.lock`

## Non-Goals

- Do not remove or replace `requests` in this phase.
- Do not remove or replace `beautifulsoup4` in this phase.
- Do not remove, optionalize, or replace `pick` in this phase.
- Do not remove, fork, or vendor `mutagen`.
- Do not redesign the downloader, HTTP behavior, Last.fm parsing, metadata tagging, or interactive flows.
- Do not introduce a broad terminal framework, generic progress framework, or vendored sanitizer library.
- Do not add live-network, credentialed, subscription, Last.fm-live, or real media download tests.

## Architecture / Contract Notes

- Phase 2 characterization tests are the safety net. If they are missing or failing, stop and finish Phase 2 before dependency removal.
- Prefer small internal modules over broad abstractions:
  - terminal constants can stay centralized in `qobuz_dl/color.py` or move to a tiny project-owned helper only if that improves clarity;
  - sanitizer behavior should live behind a project-owned helper such as `qobuz_dl/sanitize.py` if a helper is needed;
  - progress behavior should be narrow and tied to current download needs.
- Preserve current user-visible behavior where Phase 2 tests define it. If a behavior changes intentionally, update tests and docs in the same slice and call it out.
- Keep each dependency removal independently reviewable. Remove one dependency at a time, run targeted tests, then continue.
- Treat the current working tree as intentional baseline. Do not clean, revert, reformat, or fix unrelated existing changes.

## Task List

### Task 1: Verify Phase 2 safety net before removal

**Description:** Confirm the characterization tests needed for Phase 3 exist and pass before removing utility dependencies.

**Acceptance Criteria:**

- [ ] Sanitization characterization tests exist and pass.
- [ ] Terminal/color characterization tests exist and pass.
- [ ] Download/progress characterization tests exist and pass.
- [ ] Tests are offline and do not require credentials, subscriptions, live Qobuz, live Last.fm, or real media downloads.
- [ ] Any missing Phase 2 coverage is recorded as a blocker before dependency removal begins.

**Verification:**

- [ ] Run the Phase 2 targeted test files for sanitization, terminal/color, and downloader/progress behavior.
- [ ] Run `just test`.
- [ ] Inspect failures before making production changes.

**Dependencies:** Completed Phase 2 tests.

**Likely Touch Surface:**

- `tests/`
- No production files unless fixing a Phase 2 test issue inside the existing boundary

**Estimated Scope:** XS

**Why:** One readiness check, no intended behavior change, prevents removing dependencies without the promised safety net.

### Task 2: Remove `colorama` with a project-owned color policy

**Description:** Replace `colorama` usage with small project-owned terminal color constants while preserving the public constants used by the rest of the code.

**Acceptance Criteria:**

- [ ] `qobuz_dl/color.py` no longer imports `colorama`.
- [ ] The existing exported names remain available: `DF`, `BG`, `RESET`, `OFF`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `CYAN`, and `MAGENTA`.
- [ ] Color/reset behavior remains acceptable under the Phase 2 terminal/color characterization tests.
- [ ] Any difference from `colorama.init(autoreset=True)` is either avoided or explicitly handled so log output does not leak color unexpectedly.
- [ ] `colorama` is ready to remove from dependency metadata in Task 5 after all Phase 3 targeted code changes pass.

**Verification:**

- [ ] Run the terminal/color characterization tests.
- [ ] Run `uv run qobuz-dl --help`.
- [ ] Run `rg "colorama" qobuz_dl tests pyproject.toml requirements.txt docs/dependencies.md` and confirm only intentional historical/doc references remain.
- [ ] Run `just test` before moving to the next dependency.

**Dependencies:** Task 1.

**Likely Touch Surface:**

- `qobuz_dl/color.py`
- `pyproject.toml`
- `requirements.txt`
- `uv.lock` after lock refresh task
- `docs/dependencies.md` after docs sync task

**Estimated Scope:** S

**Why:** One centralized import site and a stable exported constant contract, with one important risk: preserving reset/autoreset behavior.

### Task 3: Replace `pathvalidate` with project-owned sanitization

**Description:** Replace `pathvalidate.sanitize_filename` and `pathvalidate.sanitize_filepath` with project-owned sanitization helpers that match the behavior characterized in Phase 2 closely enough for generated Qobuz paths.

**Acceptance Criteria:**

- [ ] No production code imports `pathvalidate`.
- [ ] Generated album, artist, playlist, folder, and track names pass the Phase 2 sanitization characterization tests.
- [ ] The sanitizer handles invalid path characters, reserved/problematic names, empty or whitespace-heavy results, and length/path behavior covered by tests.
- [ ] Sanitizer behavior is conservative and project-specific; it does not attempt to become a full clone of `pathvalidate` beyond this CLI's needs.
- [ ] `pathvalidate` is ready to remove from dependency metadata in Task 5 after all Phase 3 targeted code changes pass.

**Verification:**

- [ ] Run sanitization characterization tests.
- [ ] Run Last.fm characterization tests if playlist directory sanitization is covered there.
- [ ] Run `rg "pathvalidate|sanitize_filename|sanitize_filepath" qobuz_dl tests -n` and confirm imports/call sites use the project-owned helper.
- [ ] Run `just test` before moving to the next dependency.

**Dependencies:** Task 1.

**Likely Touch Surface:**

- `qobuz_dl/core.py`
- `qobuz_dl/downloader.py`
- `qobuz_dl/sanitize.py` or equivalent new helper if needed
- `tests/` only if tests need explicit intentional-change updates
- `pyproject.toml`
- `requirements.txt`
- `uv.lock` after lock refresh task
- `docs/dependencies.md` after docs sync task

**Estimated Scope:** M

**Why:** Multiple call sites and filesystem safety make this broader than `colorama`, but the behavior remains bounded by generated names and Phase 2 tests.

### Task 4: Replace or internalize `tqdm` download progress behavior

**Description:** Remove `tqdm` from the streamed download path by adding a narrow project-owned progress display or no-frills progress reporter that preserves useful download feedback without a generic progress framework.

**Acceptance Criteria:**

- [ ] `qobuz_dl/downloader.py` no longer imports `tqdm`.
- [ ] `tqdm_download` or its replacement still streams response chunks to disk.
- [ ] Successful downloads still write all bytes from the fake streamed response used in tests.
- [ ] Interrupted downloads still raise `ConnectionError` when declared content length and bytes written differ.
- [ ] Download progress remains understandable in normal CLI output, but tests do not depend on terminal rendering.
- [ ] `tqdm` is ready to remove from dependency metadata in Task 5 after all Phase 3 targeted code changes pass.

**Verification:**

- [ ] Run downloader/progress characterization tests.
- [ ] Run `uv run qobuz-dl --help` to confirm import/startup still works.
- [ ] Run `rg "tqdm" qobuz_dl tests pyproject.toml requirements.txt docs/dependencies.md` and confirm only intentional historical/doc references remain.
- [ ] Run `just test` before lock/docs cleanup.

**Dependencies:** Task 1.

**Likely Touch Surface:**

- `qobuz_dl/downloader.py`
- `tests/` only if progress tests need intentional updates for project-owned display behavior
- `pyproject.toml`
- `requirements.txt`
- `uv.lock` after lock refresh task
- `docs/dependencies.md` after docs sync task

**Estimated Scope:** M

**Why:** The download path is user-visible and error-sensitive. Keep the change narrow: streaming and interruption checks matter more than recreating a polished progress bar.

### Task 5: Refresh dependency metadata and lockfile

**Description:** Remove the low-risk utility dependencies from project metadata and regenerate the lockfile after code changes pass targeted tests.

**Acceptance Criteria:**

- [ ] `colorama`, `pathvalidate`, and `tqdm` are removed from `pyproject.toml` runtime dependencies.
- [ ] `colorama`, `pathvalidate`, and `tqdm` are removed from `requirements.txt` while that file remains in use.
- [ ] `uv.lock` is refreshed with `uv lock` or `uv sync --dev`.
- [ ] Remaining runtime dependencies still include the dependencies not targeted in Phase 3: `beautifulsoup4`, `mutagen`, `pick==1.6.0`, and `requests`.
- [ ] No unrelated dependency policy changes are bundled into this task.

**Verification:**

- [ ] Run `uv sync --dev`.
- [ ] Run `uv tree --no-dev` and confirm the removed direct dependencies are gone unless still present transitively.
- [ ] Run `rg '"colorama"|"pathvalidate"|"tqdm"|^colorama$|^pathvalidate$|^tqdm$' pyproject.toml requirements.txt uv.lock` and inspect any remaining hits.
- [ ] Run `just test`.

**Dependencies:** Tasks 2–4.

**Likely Touch Surface:**

- `pyproject.toml`
- `requirements.txt`
- `uv.lock`

**Estimated Scope:** S

**Why:** One metadata/lockfile cleanup after behavior has already been migrated and tested.

### Task 6: Update dependency docs for Phase 3 removals

**Description:** Update the canonical dependency documentation to reflect that `colorama`, `pathvalidate`, and `tqdm` have been removed or replaced internally.

**Acceptance Criteria:**

- [ ] `docs/dependencies.md` no longer lists removed dependencies as active runtime dependencies.
- [ ] The doc records their replacement path briefly enough for future maintainers to understand what happened.
- [ ] Remaining active dependencies and import sites are accurate.
- [ ] The policy still states that `requests` needs an HTTP boundary before removal and that `mutagen` remains pinned/audited.
- [ ] If docs index descriptions do not change materially, `docs/INDEX.md` is left untouched.

**Verification:**

- [ ] Run `rg "colorama|pathvalidate|tqdm" docs/dependencies.md` and confirm any mentions are historical/replacement notes, not active inventory entries.
- [ ] Run `rg "beautifulsoup4|mutagen|pick|requests" docs/dependencies.md` and confirm retained dependencies remain documented.
- [ ] Follow the docs link from `docs/INDEX.md` if it was touched.

**Dependencies:** Tasks 2–5.

**Likely Touch Surface:**

- `docs/dependencies.md`
- `docs/INDEX.md` only if the doc title or role changes materially

**Estimated Scope:** S

**Why:** One canonical docs update tied to actual dependency removal; no new lifecycle artifact is needed beyond this plan.

### Task 7: Run full proof gate and review Phase 3 diff

**Description:** Run the full local proof gate and inspect the diff to ensure Phase 3 removed only the intended utility dependencies.

**Acceptance Criteria:**

- [ ] Targeted characterization tests for color, sanitization, and download/progress pass.
- [ ] `just ci` succeeds.
- [ ] `uv tree --no-dev` confirms the intended direct dependency reduction.
- [ ] `git diff --stat` shows changes limited to Phase 3 code, tests if needed, dependency metadata, lockfile, and dependency docs.
- [ ] No `requests`, `beautifulsoup4`, `pick`, or `mutagen` replacement work is included.

**Verification:**

- [ ] Run targeted tests for Tasks 2–4.
- [ ] Run `just ci`.
- [ ] Run `uv tree --no-dev`.
- [ ] Run `git diff --stat`.
- [ ] Run `rg "from colorama|from pathvalidate|from tqdm|import tqdm" qobuz_dl tests -n` and confirm no active imports remain.

**Dependencies:** Tasks 1–6.

**Likely Touch Surface:**

- No new files unless verification reveals a missed Phase 3 touchpoint

**Estimated Scope:** S

**Why:** One final proof gate and scope check after dependency removal.

## Checkpoints

- [ ] After Task 1: Stop if Phase 2 characterization tests are missing or failing.
- [ ] After Task 2: Check terminal reset/autoreset behavior before removing `colorama` from metadata.
- [ ] After Task 3: Review sanitizer behavior carefully before removing `pathvalidate`; filesystem safety is the highest-risk part of this phase.
- [ ] After Task 4: Review streamed download behavior before removing `tqdm`; interrupted-download behavior must remain loud.
- [ ] After Task 7: Run `pa-code-review` because this phase removes runtime dependencies and changes filesystem/download-adjacent behavior.

## Risks and Mitigations

- **Risk:** Removing `colorama` changes reset/autoreset behavior and leaks terminal colors across log lines.
  - **Impact:** Medium
  - **Mitigation:** Preserve reset behavior explicitly or update output sites narrowly; verify with characterization tests and manual CLI help/startup checks.

- **Risk:** A project-owned sanitizer is too permissive or too aggressive.
  - **Impact:** High
  - **Mitigation:** Use Phase 2 tests as the contract, keep the sanitizer conservative, and avoid pretending to clone all of `pathvalidate`.

- **Risk:** Progress replacement breaks streamed download correctness while focusing on display.
  - **Impact:** High
  - **Mitigation:** Treat bytes written and interruption detection as the core behavior. Keep terminal progress display simple.

- **Risk:** Metadata and lockfile cleanup accidentally removes non-Phase-3 dependencies.
  - **Impact:** Medium
  - **Mitigation:** Inspect `pyproject.toml`, `requirements.txt`, `uv.lock`, and `uv tree --no-dev`; retain `beautifulsoup4`, `mutagen`, `pick==1.6.0`, and `requests`.

- **Risk:** This phase drifts into Phase 4 or Phase 5 work.
  - **Impact:** Medium
  - **Mitigation:** Do not touch `pick`, Last.fm parser replacement, `beautifulsoup4`, `requests`, or HTTP boundaries except where tests prove unaffected imports/startup.

- **Risk:** Dirty working tree makes it hard to see Phase 3 changes.
  - **Impact:** Medium
  - **Mitigation:** Treat existing changes as baseline, inspect `git diff --stat`, and keep a tight list of Phase 3 files touched.

## Open Questions

- None blocking if Phase 2 characterization tests exist and pass.
- If Phase 2 tests are incomplete, the blocker is not a Phase 3 design question; finish the missing tests first.

## Recommended Next Phase

`pa-tdd` for Task 1 first. Continue one dependency at a time: `colorama`, then `pathvalidate`, then `tqdm`. After Phase 3 passes `just ci` and `pa-code-review`, create a new `pa-plan-slicer` plan for Phase 4: secondary feature simplification around `pick` and `beautifulsoup4`.
