# Implementation Plan: Dependency Hardening Phase 1

## Overview

Implement Phase 1 of dependency hardening: create the dependency policy baseline and modernize the project runtime target to Python `>=3.10`. This slice does not remove runtime dependencies yet. It makes the project metadata, CI, lockfile, docs, and maintainer instructions agree before later dependency replacement work begins.

## Source Inputs

- `docs/sdlc/2026-05-26-dependency-hardening/vision-dependency-hardening.md`
- `docs/sdlc/2026-05-26-dependency-hardening/architecture-dependency-hardening.md`
- Current `pyproject.toml`
- Current `.github/workflows/ci.yml`
- Current dependency docs under `docs/`
- Current repository instructions in `AGENTS.md`

## Non-Goals

- Do not remove `colorama`, `pathvalidate`, `tqdm`, `pick`, `beautifulsoup4`, or `requests` in this phase.
- Do not rewrite HTTP behavior.
- Do not vendor dependencies.
- Do not replace or fork `mutagen`.
- Do not add live Qobuz, Last.fm, subscription, credential, or real-download tests.
- Do not broaden packaging modernization beyond what is needed for Python `>=3.10` alignment.

## Architecture / Contract Notes

- `uv` remains the project command runner and lockfile workflow.
- `just ci` remains the main local proof command.
- Python `>=3.10` is the new baseline for this plan.
- `mutagen` is documented as a retained dependency to pin and audit; deeper metadata replacement is explicitly deferred.
- The dependency policy should live in the existing canonical dependency document unless implementation reveals a strong reason to split it.

## Task List

### Task 1: Document the dependency policy baseline

**Description:** Expand the dependency documentation from inventory-only into a policy that explains dependency categories, vendoring rules, audit expectations, and the intentional `mutagen` retention decision.

**Acceptance Criteria:**

- [ ] `docs/dependencies.md` explains the four dependency paths: remove/replace internally, optionalize, pin/audit, or vendor with provenance.
- [ ] The doc states that vendoring transfers maintenance responsibility and is not automatic risk removal.
- [ ] The doc names `mutagen` as intentionally retained for now because audio metadata writing is high-consequence.
- [ ] The doc keeps the current dependency inventory and import-site mapping accurate.
- [ ] The doc explains that later dependency removals require characterization tests first.

**Verification:**

- [ ] Read `docs/dependencies.md` and confirm a maintainer can answer why each dependency exists and what the future path is.
- [ ] Run `rg "mutagen|vendor|optional|audit|characterization" docs/dependencies.md` and confirm the policy topics are findable.

**Dependencies:** None

**Likely Touch Surface:**

- `docs/dependencies.md`
- `docs/INDEX.md` only if the dependency doc title or purpose changes materially

**Estimated Scope:** S

**Why:** One documentation contract, one canonical target, clear proof signal, no code behavior change.

### Task 2: Modernize Python metadata to `>=3.10`

**Description:** Update project metadata and local tooling targets so the package advertises and checks against Python `>=3.10` rather than `>=3.8`.

**Acceptance Criteria:**

- [ ] `pyproject.toml` declares `requires-python = ">=3.10"`.
- [ ] Ruff target version is updated from `py38` to the appropriate Python 3.10 target.
- [ ] Any Python 3.8-specific build-system comment is removed or rewritten so it no longer claims Python 3.8 support.
- [ ] If classifiers are expanded, they do not imply Python 3.8 support.
- [ ] Packaging metadata remains minimal and still uses `pyproject.toml` as the source of truth.

**Verification:**

- [ ] Run `rg "3\.8|py38" pyproject.toml` and confirm no stale Python 3.8 metadata remains.
- [ ] Run `uv sync --dev` after lockfile work in Task 5.
- [ ] Run `uv build` through `just ci` in Task 5.

**Dependencies:** Task 1 is recommended first so the policy decision is documented before metadata changes.

**Likely Touch Surface:**

- `pyproject.toml`

**Estimated Scope:** S

**Why:** One package metadata boundary, one tool config change, clear grep/build proof, no product behavior change.

### Task 3: Align CI with the Python `>=3.10` baseline

**Description:** Update GitHub Actions so CI no longer tests Python 3.8 and instead uses the new supported baseline plus the newest target already in use.

**Acceptance Criteria:**

- [ ] `.github/workflows/ci.yml` removes Python `3.8` from the matrix.
- [ ] The matrix includes a Python `>=3.10` baseline and the current latest target used by the project.
- [ ] CI still runs uv sync, Ruff format check, Ruff lint, Pytest, CLI smoke test, and package build.
- [ ] No CI step uses `pip`, `pip3`, direct `python`, or `python3` as the documented/default workflow.

**Verification:**

- [ ] Run `rg '3\.8' .github/workflows/ci.yml` and confirm no stale Python 3.8 CI entry remains.
- [ ] Review the workflow to confirm the same quality gates still run.
- [ ] Run `just ci` locally in Task 5.

**Dependencies:** Task 2

**Likely Touch Surface:**

- `.github/workflows/ci.yml`

**Estimated Scope:** S

**Why:** One CI matrix contract, bounded workflow edit, clear grep and local gate proof.

### Task 4: Sync docs and repository instructions with the new baseline

**Description:** Update documentation and repo instructions that currently mention Python 3.8 support or Python 3.8 compatibility checks so they match the new baseline.

**Acceptance Criteria:**

- [ ] `docs/installation.md` states Python `>=3.10` as the requirement.
- [ ] `docs/packaging.md` no longer describes Python 3.8-compatible build constraints as current policy.
- [ ] `docs/testing.md` describes the updated CI matrix and removes Python 3.8 verification guidance if present.
- [ ] `AGENTS.md` no longer instructs agents to verify Python 3.8 compatibility after the baseline change.
- [ ] Any README or docs references discovered by `rg "3\.8|Python 3.8|py38" README.md docs AGENTS.md` are updated or deliberately left only if they describe historical context.

**Verification:**

- [ ] Run `rg "3\.8|Python 3.8|py38" README.md docs AGENTS.md pyproject.toml .github/workflows/ci.yml` and inspect every remaining hit.
- [ ] Follow links from `docs/INDEX.md` to confirm the dependency, packaging, testing, and installation docs remain discoverable.

**Dependencies:** Tasks 1–3

**Likely Touch Surface:**

- `docs/installation.md`
- `docs/packaging.md`
- `docs/testing.md`
- `AGENTS.md`
- `README.md` if stale Python requirement text appears there
- `docs/INDEX.md` only if doc descriptions change materially

**Estimated Scope:** M

**Why:** Cross-doc consistency touches several files, but the behavior is one outcome: project docs and agent instructions agree on Python `>=3.10`.

### Task 5: Refresh lockfile and run the Phase 1 proof gate

**Description:** Regenerate the lockfile for the new Python baseline and run the local quality gate.

**Acceptance Criteria:**

- [ ] `uv.lock` is refreshed after the `requires-python` change.
- [ ] The lockfile no longer carries unnecessary Python 3.8 resolution branches caused by the old baseline.
- [ ] Dependency sync succeeds on the new baseline Python version.
- [ ] `just ci` succeeds in the active project environment.
- [ ] Any failure is fixed within the Phase 1 boundary or reported as a blocker if it implies broader dependency work.

**Verification:**

- [ ] Run `uv lock` or `uv sync --dev` as appropriate for lockfile refresh.
- [ ] Run `uv sync --dev --python 3.10` to prove the new minimum baseline resolves.
- [ ] Run `uv sync --dev` for the active local environment.
- [ ] Run `just ci`.
- [ ] Run `git diff --stat` and confirm the changed files match the Phase 1 boundary.

**Dependencies:** Tasks 2–4

**Likely Touch Surface:**

- `uv.lock`
- Any file already touched by Tasks 2–4 if verification reveals stale references

**Estimated Scope:** S

**Why:** One reproducibility proof, one lockfile update, one full local gate; failures may reveal hidden compatibility issues but should not expand scope silently.

## Checkpoints

- [ ] After Task 1: Review the dependency policy wording before metadata changes. It should be clear that vendoring is a last resort, not the default.
- [ ] After Tasks 2–4: Run the stale-reference grep before refreshing the lockfile, then verify Python 3.10 sync explicitly.
- [ ] After Task 5: Perform `pa-code-review` before merging because the change touches packaging, CI, docs, lockfile, and agent instructions.
- [ ] After review: Run `pa-doc-update` only if implementation changes a canonical doc beyond the planned dependency policy and baseline updates.

## Risks and Mitigations

- **Risk:** Dropping Python 3.8 leaves stale instructions behind.
  - **Impact:** High
  - **Mitigation:** Use repo-wide grep for `3.8`, `Python 3.8`, and `py38` across code, docs, CI, and instructions.

- **Risk:** Lockfile refresh causes large dependency churn unrelated to Phase 1.
  - **Impact:** Medium
  - **Mitigation:** Inspect `uv.lock` diff; if churn is broader than expected, stop and report before bundling unrelated dependency upgrades. Verify the new Python 3.10 baseline separately from the active local environment.

- **Risk:** Policy doc overcommits to removing dependencies before tests exist.
  - **Impact:** Medium
  - **Mitigation:** Phrase later phases as governed paths, not completed decisions. Keep actual removals out of Phase 1.

- **Risk:** Build-system modernization expands scope.
  - **Impact:** Medium
  - **Mitigation:** Only update comments/metadata needed for Python `>=3.10`; do not change setuptools strategy unless current checks fail or the old constraint becomes misleading.

- **Risk:** `AGENTS.md` is untracked or local-context-sensitive.
  - **Impact:** Medium
  - **Mitigation:** Treat it as part of the repo context if present, but inspect its status before editing and avoid changing unrelated local workflow instructions.

## Open Questions

- None blocking for Phase 1. The user has already accepted Python `>=3.10` and retaining `mutagen` as pinned/audited.

## Recommended Next Phase

`pa-tdd` for Task 1 first, then continue through Tasks 2–5 sequentially. Do not parallelize Tasks 2–5 because metadata, CI, docs, and lockfile changes depend on the same Python baseline contract.
