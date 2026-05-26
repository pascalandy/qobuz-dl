# Implementation Plan: Dependency Hardening Phases 4-6

## Overview

Implement the remaining dependency-hardening phases after Phase 3 removes the low-risk utility dependencies.

Remaining phases:

- **Phase 4:** simplify or optionalize secondary features that currently depend on `pick` and `beautifulsoup4`.
- **Phase 5:** replace `requests` and its transitive dependency graph through a narrow internal HTTP boundary.
- **Phase 6:** keep `mutagen` as an intentional pinned/audited dependency and document the governance policy.

This plan is sequential. Phase 4 removes secondary-feature dependency risk first. Phase 5 then tackles the broad HTTP surface. Phase 6 closes the cycle by making the retained metadata dependency visible and governed.

## Source Inputs

- `docs/sdlc/2026-05-26-dependency-hardening/vision-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/architecture-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/impl-plan-phase-2-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/impl-plan-phase-3-dependency-hardening.md`
- `docs/dependencies.md`
- Phase 2 characterization tests, especially Last.fm, interactive, Qobuz API, bundle, and streamed-download tests
- Current implementation in `qobuz_dl/core.py`, `qobuz_dl/qopy.py`, `qobuz_dl/bundle.py`, `qobuz_dl/downloader.py`, `qobuz_dl/metadata.py`, and `qobuz_dl/utils.py`
- Current dependency declarations in `pyproject.toml`, `requirements.txt`, and `uv.lock`

## Non-Goals

- Do not replace or fork `mutagen`.
- Do not add live Qobuz, Last.fm, credentialed, subscription, or real media download tests to the default suite.
- Do not vendor third-party code unless a separate architecture review explicitly approves it.
- Do not redesign unrelated CLI commands, metadata tagging, database behavior, or download folder semantics.
- Do not hide user-facing behavior changes as dependency cleanup.
- Do not attempt all remaining phases in one coding session.

## Architecture / Contract Notes

- Phase 2 and Phase 3 tests are prerequisites. If relevant characterization tests are missing or failing, stop and finish those first.
- Phase 4 has human-choice points: simpler built-in behavior versus optional extras for interactive selection and Last.fm parsing.
- Phase 5 must introduce an internal HTTP boundary before removing `requests`; replacing `requests` call sites ad hoc is not acceptable.
- Phase 6 is governance, not replacement. `mutagen` remains because MP3/FLAC metadata writing is high-consequence.
- Keep default tests offline. Use fake responses, fake sessions, fixtures, and temporary files.
- Treat the current working tree as intentional baseline; avoid unrelated cleanup.

## Task List

### Task 1: Confirm readiness for Phase 4

**Description:** Verify that Phase 4 can start safely by checking that Phase 2 interactive and Last.fm tests exist, Phase 3 dependency removals are complete, and current dependency docs reflect the latest runtime state.

**Acceptance Criteria:**

- [ ] Phase 2 interactive characterization tests exist or an explicit deferral note exists.
- [ ] Phase 2 Last.fm fixture tests exist and pass.
- [ ] Phase 3 has removed `colorama`, `pathvalidate`, and `tqdm`, or those removals are explicitly marked incomplete before proceeding.
- [ ] `docs/dependencies.md` correctly shows `pick` and `beautifulsoup4` as the Phase 4 targets.
- [ ] No Phase 5 HTTP replacement work begins in this task.

**Verification:**

- [ ] Run relevant Phase 2 tests for Last.fm and interactive behavior.
- [ ] Run `uv tree --no-dev` and inspect current direct runtime dependencies.
- [ ] Run `just test`.

**Dependencies:** Completed or explicitly checkpointed Phases 2-3.

**Likely Touch Surface:**

- `tests/`
- `docs/dependencies.md` only if current-state docs are stale

**Estimated Scope:** XS

**Why:** One readiness check before user-facing convenience-flow changes.

### Task 2: Decide and implement the `pick` strategy

**Description:** Remove or optionalize `pick` by choosing the smallest acceptable interactive strategy, then update `QobuzDL.interactive` without breaking scripted flows.

**Acceptance Criteria:**

- [ ] A decision is recorded in the implementation notes or docs: simple built-in numbered prompts, or optional rich interactive extra.
- [ ] Core non-interactive commands do not depend on `pick`.
- [ ] If simple prompts are chosen, users can still choose search type, select one or more results, decide whether to continue searching, and choose quality.
- [ ] If optional rich UI is chosen, package metadata cleanly separates the optional dependency from the default install.
- [ ] Existing interactive characterization tests are updated to match the chosen behavior.
- [ ] `pick` is removed from default runtime dependencies if the default install no longer needs it.

**Verification:**

- [ ] Run interactive characterization tests.
- [ ] Run CLI smoke checks: `uv run qobuz-dl --help`, `uv run qobuz-dl fun --help`.
- [ ] Run `rg "from pick|import pick|pick==" qobuz_dl tests pyproject.toml requirements.txt docs/dependencies.md` and inspect remaining hits.
- [ ] Run `just test`.

**Dependencies:** Task 1.

**Likely Touch Surface:**

- `qobuz_dl/core.py`
- `tests/`
- `pyproject.toml`
- `requirements.txt`
- `uv.lock`
- `docs/dependencies.md`
- `docs/cli.md` or `docs/examples.md` if interactive behavior changes materially

**Estimated Scope:** M

**Why:** This is a user-facing CLI behavior slice with one human-choice point. Keep it isolated from Last.fm and HTTP work.

### Task 3: Replace or optionalize `beautifulsoup4` for Last.fm parsing

**Description:** Remove the default `beautifulsoup4` dependency by either implementing a small `html.parser`-based Last.fm extractor for the supported fixture shape or moving Last.fm support behind an optional dependency/feature.

**Acceptance Criteria:**

- [ ] A decision is recorded: built-in small parser, optional Last.fm extra, or explicit best-effort support.
- [ ] Default install no longer requires `beautifulsoup4` if a small parser or optional feature is chosen.
- [ ] Last.fm fixture tests pass for supported page shapes.
- [ ] Unsupported page shapes fail clearly and do not trigger misleading downloads.
- [ ] Core Qobuz search/download flows remain unaffected.
- [ ] Docs are updated if Last.fm support becomes optional or its failure behavior changes.

**Verification:**

- [ ] Run Last.fm fixture tests.
- [ ] Run CLI smoke checks.
- [ ] Run `rg "BeautifulSoup|bs4|beautifulsoup4" qobuz_dl tests pyproject.toml requirements.txt docs/dependencies.md docs/examples.md` and inspect remaining hits.
- [ ] Run `just test`.

**Dependencies:** Task 1. Can run after Task 2, but should stay a separate reviewable change.

**Likely Touch Surface:**

- `qobuz_dl/core.py`
- `tests/fixtures/`
- `tests/`
- `pyproject.toml`
- `requirements.txt`
- `uv.lock`
- `docs/dependencies.md`
- `docs/examples.md` if Last.fm docs change

**Estimated Scope:** M

**Why:** This is a secondary feature with parser brittleness risk. Fixture coverage should govern the replacement.

### Task 4: Refresh metadata and docs after Phase 4

**Description:** Update dependency metadata, lockfile, and docs after `pick` and/or `beautifulsoup4` have been removed from the default runtime path.

**Acceptance Criteria:**

- [ ] `pyproject.toml`, `requirements.txt`, and `uv.lock` reflect the chosen Phase 4 dependency state.
- [ ] `docs/dependencies.md` accurately lists remaining active dependencies and any optional extras.
- [ ] User docs are updated only where behavior changed: likely `docs/examples.md`, `docs/cli.md`, or `docs/installation.md` if optional extras are introduced.
- [ ] `uv tree --no-dev` shows the expected runtime dependency reduction.
- [ ] No `requests` or `mutagen` governance changes are mixed into this task.

**Verification:**

- [ ] Run `uv sync --dev`.
- [ ] Run `uv tree --no-dev`.
- [ ] Run `just ci`.
- [ ] Run `git diff --stat` and confirm the changes are Phase 4 only.

**Dependencies:** Tasks 2-3.

**Likely Touch Surface:**

- `pyproject.toml`
- `requirements.txt`
- `uv.lock`
- `docs/dependencies.md`
- `docs/cli.md`, `docs/examples.md`, or `docs/installation.md` only if behavior/installation changes

**Estimated Scope:** S

**Why:** One cleanup/proof gate after secondary-feature dependency decisions.

### Task 5: Design and add the internal HTTP boundary

**Description:** Introduce a narrow project-owned HTTP boundary before removing `requests`. The boundary should represent exactly what the project needs: GET-based JSON API calls, text fetches, streamed downloads, headers, query params, redirects, timeouts, TLS verification, status handling, JSON parsing, and error mapping.

**Acceptance Criteria:**

- [ ] A small module such as `qobuz_dl/http.py` or equivalent exists.
- [ ] The boundary exposes focused helpers for JSON GET requests, text GET fetches, and streamed downloads, or similarly narrow operations.
- [ ] Project-owned exceptions or error wrappers are defined where callers need to stop depending on `requests.exceptions`.
- [ ] Timeout and TLS/certificate behavior is explicit enough that removing `requests` does not silently weaken network safety.
- [ ] The boundary is tested with fake responses and does not perform live network calls.
- [ ] No caller migration happens until the boundary tests pass, except tiny setup needed to make the boundary importable.

**Verification:**

- [ ] Run new HTTP-boundary tests directly.
- [ ] Run `just test`.
- [ ] Inspect the boundary to confirm it is not a generic HTTP framework.

**Dependencies:** Completed Phase 4 and Phase 2 HTTP characterization tests.

**Likely Touch Surface:**

- `qobuz_dl/http.py` or equivalent
- `tests/test_http*.py` or equivalent
- `qobuz_dl/exceptions.py` if project-owned HTTP exceptions belong there

**Estimated Scope:** M

**Why:** This is the structural seam that makes safe `requests` removal possible. It should be built and tested before call sites migrate.

### Task 6: Migrate Qobuz API client through the HTTP boundary

**Description:** Move `qobuz_dl/qopy.py` from direct `requests.Session` usage to the internal HTTP boundary while preserving login, headers, params, signatures, status handling, JSON parsing, and exception behavior.

**Acceptance Criteria:**

- [ ] `qopy.Client` no longer imports or directly instantiates `requests.Session`.
- [ ] Login behavior still maps invalid credentials and invalid app IDs to existing project exceptions.
- [ ] `track/getFileUrl` and favorite calls still map invalid app secret behavior correctly.
- [ ] Invalid quality handling remains local and does not require network access.
- [ ] Existing qopy characterization tests pass, updated only for the new boundary where appropriate.

**Verification:**

- [ ] Run qopy/API client tests.
- [ ] Run HTTP-boundary tests.
- [ ] Run `just test`.

**Dependencies:** Task 5.

**Likely Touch Surface:**

- `qobuz_dl/qopy.py`
- `qobuz_dl/http.py` or equivalent
- `tests/`

**Estimated Scope:** M

**Why:** API authentication and request signing are high-risk but contained in one main module.

### Task 7: Migrate bundle and Last.fm text fetches through the HTTP boundary

**Description:** Move direct `requests` usage for bundle scraping and Last.fm page fetches to the internal HTTP boundary while preserving status/error handling and fixture-tested parsing behavior.

**Acceptance Criteria:**

- [ ] `qobuz_dl/bundle.py` no longer imports `requests.Session` directly.
- [ ] `qobuz_dl/core.py` no longer imports or catches `requests.exceptions` for Last.fm fetches.
- [ ] Bundle fixture tests pass.
- [ ] Last.fm fixture tests pass.
- [ ] No live network calls are introduced in default tests.

**Verification:**

- [ ] Run bundle characterization tests.
- [ ] Run Last.fm tests.
- [ ] Run `rg "import requests|from requests|requests\." qobuz_dl/bundle.py qobuz_dl/core.py tests -n` and inspect remaining hits.
- [ ] Run `just test`.

**Dependencies:** Tasks 5-6.

**Likely Touch Surface:**

- `qobuz_dl/bundle.py`
- `qobuz_dl/core.py`
- `qobuz_dl/http.py` or equivalent
- `tests/`

**Estimated Scope:** M

**Why:** Two text-fetch surfaces share the same HTTP boundary behavior and can be reviewed without touching streamed media downloads.

### Task 8: Migrate streamed downloads through the HTTP boundary

**Description:** Move media and extra-file streamed downloads in `qobuz_dl/downloader.py` to the internal HTTP boundary while preserving chunked writes and interrupted-download detection.

**Acceptance Criteria:**

- [ ] `qobuz_dl/downloader.py` no longer imports `requests` for streamed downloads or HTTP errors.
- [ ] Streamed-download tests pass.
- [ ] Successful fake streamed responses write all expected bytes.
- [ ] Interrupted-download behavior remains loud when content length and bytes written differ.
- [ ] Missing or unusual content-length behavior is either preserved from characterization tests or intentionally changed with tests and notes.
- [ ] No live network calls or real media downloads are introduced in default tests.

**Verification:**

- [ ] Run downloader/streaming tests.
- [ ] Run HTTP-boundary tests.
- [ ] Run `rg "import requests|from requests|requests\." qobuz_dl/downloader.py tests -n` and inspect remaining hits.
- [ ] Run `just test`.

**Dependencies:** Tasks 5-6. Can follow Task 7, but should stay a separate reviewable change.

**Likely Touch Surface:**

- `qobuz_dl/downloader.py`
- `qobuz_dl/http.py` or equivalent
- `tests/`

**Estimated Scope:** M

**Why:** Streamed downloads are high-consequence and should not be hidden inside the same task as bundle and Last.fm migration.

### Task 9: Remove `requests` and refresh dependency metadata

**Description:** Remove `requests` from the default runtime dependencies after all production call sites use the internal HTTP boundary.

**Acceptance Criteria:**

- [ ] No production code imports `requests`.
- [ ] `requests` is removed from `pyproject.toml` and `requirements.txt`.
- [ ] `uv.lock` is refreshed.
- [ ] `uv tree --no-dev` no longer includes `requests` or its transitive dependencies unless another retained dependency pulls them in.
- [ ] `docs/dependencies.md` records the project-owned HTTP boundary and no longer lists `requests` as active runtime dependency.

**Verification:**

- [ ] Run `rg "requests|urllib3|certifi|charset-normalizer|idna" qobuz_dl pyproject.toml requirements.txt docs/dependencies.md uv.lock -n` and inspect remaining hits.
- [ ] Run `uv sync --dev`.
- [ ] Run `uv tree --no-dev`.
- [ ] Run `just ci`.

**Dependencies:** Tasks 5-8.

**Likely Touch Surface:**

- `pyproject.toml`
- `requirements.txt`
- `uv.lock`
- `docs/dependencies.md`

**Estimated Scope:** S

**Why:** Metadata cleanup after behavior migration and tests pass.

### Task 10: Pin and document retained `mutagen` governance

**Description:** Complete Phase 6 by making `mutagen` retention explicit in dependency metadata and docs, including audit expectations and future replacement guardrails.

**Acceptance Criteria:**

- [ ] `mutagen` remains in runtime dependencies.
- [ ] `mutagen` has an explicit version policy, preferably a pin or bounded range chosen deliberately.
- [ ] `docs/dependencies.md` states why `mutagen` is retained and what would be required before replacement or vendoring.
- [ ] Audit expectations are documented in `docs/dependencies.md` or `docs/testing.md` if a test/audit command is introduced.
- [ ] No binary metadata writer replacement work is included.

**Verification:**

- [ ] Run metadata formatting tests.
- [ ] Run `uv tree --no-dev` and confirm `mutagen` remains visible.
- [ ] Run `rg "mutagen" pyproject.toml requirements.txt docs/dependencies.md qobuz_dl tests -n` and confirm references match retained-governance policy.
- [ ] Run `just ci`.

**Dependencies:** Task 9 is recommended first so `mutagen` is the only retained third-party runtime dependency if all other removals succeeded.

**Likely Touch Surface:**

- `pyproject.toml`
- `requirements.txt`
- `uv.lock`
- `docs/dependencies.md`
- `docs/testing.md` only if an audit command is added

**Estimated Scope:** S

**Why:** Governance and metadata cleanup; no behavior change.

### Task 11: Final dependency-hardening proof gate

**Description:** Validate the final runtime dependency state, docs, tests, and packaging after Phases 4-6.

**Acceptance Criteria:**

- [ ] `just ci` succeeds.
- [ ] `uv tree --no-dev` shows the expected final runtime dependency graph.
- [ ] Default tests remain offline and do not require credentials, subscriptions, live Qobuz, live Last.fm, or real downloads.
- [ ] `docs/dependencies.md` is accurate and does not list removed dependencies as active runtime dependencies.
- [ ] Remaining open follow-ups are explicit, especially any deferred Last.fm, interactive, HTTP, or metadata questions.

**Verification:**

- [ ] Run `just ci`.
- [ ] Run `uv tree --no-dev`.
- [ ] Run `rg "beautifulsoup4|bs4|pick|requests|colorama|pathvalidate|tqdm|mutagen" pyproject.toml requirements.txt docs/dependencies.md qobuz_dl tests -n` and inspect all remaining hits.
- [ ] Run `git diff --stat` and review for out-of-scope changes.

**Dependencies:** Tasks 1-10.

**Likely Touch Surface:**

- No new files unless validation finds stale references

**Estimated Scope:** S

**Why:** One final integration/proof step for the remaining phases.

## Checkpoints

- [ ] Before Task 2: Human approval of `pick` strategy if preserving rich multiselect is important.
- [ ] Before Task 3: Human approval of Last.fm strategy if support might become optional or best-effort.
- [ ] After Task 5: Review the HTTP boundary before migrating callers.
- [ ] After Task 8: Review network/download behavior before removing `requests` from metadata.
- [ ] Before Task 10: Confirm the chosen `mutagen` pin/range and audit command policy.
- [ ] After Task 11: Run `pa-code-review`, then `pa-qa` or targeted smoke checks if user-facing CLI behavior changed.

## Risks and Mitigations

- **Risk:** Phase 4 silently downgrades interactive UX.
  - **Impact:** Medium
  - **Mitigation:** Make the `pick` strategy explicit before implementation and keep behavior covered by tests or documented as changed.

- **Risk:** Last.fm parser replacement becomes brittle.
  - **Impact:** Medium
  - **Mitigation:** Use fixtures, clear unsupported-page failure behavior, and optionalize rather than overfitting a complex parser.

- **Risk:** HTTP boundary becomes a generic framework.
  - **Impact:** Medium
  - **Mitigation:** Keep helpers tied to current needs: JSON GET call, text GET fetch, streamed download, status/error mapping.

- **Risk:** `requests` removal changes error behavior relied on by callers.
  - **Impact:** High
  - **Mitigation:** Preserve project-level exception behavior and update catch sites deliberately.

- **Risk:** Standard-library HTTP streaming handles redirects, headers, timeouts, TLS certificates, or missing content length differently than `requests`.
  - **Impact:** High
  - **Mitigation:** Test redirects/status handling where used, make timeout and TLS behavior explicit, and validate streamed downloads with fake responses.

- **Risk:** `mutagen` version policy is too rigid or too loose.
  - **Impact:** Medium
  - **Mitigation:** Choose the version policy deliberately and document update/audit expectations.

- **Risk:** Dependency cleanup absorbs unrelated refactors in a dirty working tree.
  - **Impact:** Medium
  - **Mitigation:** Treat current changes as baseline, inspect `git diff --stat`, and keep each phase's touched files narrow.

## Open Questions

- `pick` strategy: simple built-in prompts versus optional rich interactive extra. This needs human approval before Task 2 if UX parity matters.
- Last.fm strategy: built-in small parser versus optional support. This needs human approval before Task 3 if Last.fm is considered core.
- HTTP backend shape: whether stdlib-only is sufficient or the boundary should allow a future optional backend. Review after Task 5.
- `mutagen` version policy: exact pin versus bounded range. Decide before Task 10.

## Recommended Next Phase

After Phase 3 is complete and reviewed, run `pa-tdd` for Task 1 of this plan. Continue checkpoint-by-checkpoint: Phase 4 decisions first, then HTTP boundary review before Phase 5 migration, then `mutagen` governance for Phase 6.
