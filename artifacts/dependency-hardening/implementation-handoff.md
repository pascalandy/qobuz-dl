# Dependency Hardening Phase 1 Implementation Handoff

## Changed files

Edited for approved Phase 1 scope:

- `docs/dependencies.md` — expanded dependency inventory into canonical dependency policy.
- `docs/INDEX.md` — updated dependency-doc description to include policy purpose.
- `docs/installation.md` — changed runtime requirement to Python 3.10+.
- `docs/packaging.md` — removed Python 3.8 build-support wording and added baseline-alignment note.
- `docs/testing.md` — documented CI matrix as Python 3.10 + 3.13.
- `AGENTS.md` — removed Python 3.8 verification guidance and updated CI/build notes.
- `.github/workflows/ci.yml` — changed CI matrix from 3.8/3.13 to 3.10/3.13.
- `pyproject.toml` — changed `requires-python` to `>=3.10`, Ruff target to `py310`, and rewrote the Python 3.8 build comment.
- `uv.lock` — refreshed after the new Python baseline.
- `qobuz_dl/downloader.py` — formatting-only update required by Ruff after changing target to `py310`; no behavior change.

Note: the worktree already contained many dirty/untracked files before this task. I did not revert unrelated changes.

## AC status

- AC-1: Passed. `docs/dependencies.md` now documents the four paths: remove/replace internally, optionalize, pin/audit, and vendor with provenance. It states vendoring transfers maintenance responsibility, names `mutagen` as intentionally retained for high-consequence metadata writing, keeps the dependency inventory/import-site mapping accurate, and requires characterization tests before later removals.
- AC-2: Passed. `pyproject.toml` now has `requires-python = ">=3.10"`, Ruff `target-version = "py310"`, no Python 3.8-specific build comment, and minimal metadata remains centralized in `pyproject.toml`.
- AC-3: Passed. `.github/workflows/ci.yml` now uses Python `3.10` and `3.13`; existing gates remain `uv sync --dev --frozen`, Ruff format/lint, Pytest, CLI smoke, and `uv build`.
- AC-4: Passed. `docs/installation.md`, `docs/packaging.md`, `docs/testing.md`, `AGENTS.md`, and `docs/INDEX.md` are aligned to Python 3.10+. Stale Python 3.8 references remain only in the historical SDLC artifacts under `docs/sdlc/2026-05-26-dependency-hardening/`.
- AC-5: Passed. `uv.lock` is refreshed for `>=3.10`; Python 3.10 sync, current-env sync, and `just ci` succeeded.

## Commands run

- `git status --short` — exit 0; showed pre-existing dirty/untracked work.
- `rg "3\.8|Python 3\.8|py38" README.md docs AGENTS.md pyproject.toml .github/workflows/ci.yml` — exit 0 before edits; found stale references in current docs/config plus historical SDLC artifacts.
- `rg "from (bs4|colorama|mutagen|pathvalidate|pick|requests|tqdm)|import (bs4|colorama|mutagen|pathvalidate|pick|requests|tqdm|BeautifulSoup)" qobuz_dl` — exit 0; verified import-site inventory.
- `uv lock` — exit 0; refreshed lockfile for Python `>=3.10`.
- `uv sync --dev --python 3.10` — exit 0; created Python 3.10 environment and installed 22 packages.
- `uv sync --dev` — exit 0; current environment sync succeeded.
- `just ci` — exit 1 initially; Ruff format check wanted a formatting-only change in `qobuz_dl/downloader.py` after the Ruff target moved to `py310`.
- `just lint` — exit 0.
- `just test` — exit 0; 7 tests passed.
- `just smoke` — exit 0; CLI help smoke checks passed.
- `just build` — exit 0; source distribution and wheel built.
- `uv run ruff format --check qobuz_dl/downloader.py --diff` — exit 1; identified the exact required formatting-only change.
- `just ci` — exit 0 after the formatting-only fix; format, lint, tests, smoke, and build all passed.
- `rg "3\.8|py38" pyproject.toml || true` — exit 0; no matches.
- `rg '3\.8' .github/workflows/ci.yml || true` — exit 0; no matches.
- `rg "3\.8|Python 3\.8|py38" README.md docs AGENTS.md pyproject.toml .github/workflows/ci.yml || true` — exit 0; remaining matches are only in historical SDLC artifacts.
- `rg "mutagen|vendor|optional|audit|characterization" docs/dependencies.md` — exit 0; policy topics are findable.

## Validation evidence

- `uv.lock` now starts with `requires-python = ">=3.10"` and no longer has the old Python 3.8/3.9 resolution-marker branches.
- CI matrix is `python-version: ["3.10", "3.13"]`.
- `pyproject.toml` uses `requires-python = ">=3.10"` and `target-version = "py310"`.
- Stale-reference grep has no non-historical Python 3.8/`py38` hits.
- Full local gate passed with `just ci`.

## Autonomous fixes

- Applied the single Ruff formatting change in `qobuz_dl/downloader.py` required by the approved `py310` target. This was in scope because `just ci` could not pass after the metadata/tooling baseline change without it. The change only wraps the existing multi-context `with` statement and does not alter runtime behavior.

## Remaining risks/blockers

- No Phase 1 blocker remains.
- The repository still has broad pre-existing dirty/untracked work outside this Phase 1 slice. Reviewers should account for that when inspecting the final diff.
- `mutagen` is documented as retained/pin-audit, but it is not newly pinned in this phase because the approved scope did not request runtime dependency pin changes.

## Decisions needing parent/user input

None.
