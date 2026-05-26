I did not write `/artifacts/dependency-hardening/independent-dd.md` because this was a read-only/no-edit due-diligence pass and artifact-writing conflicts with that constraint. Findings below.

# Independent Due Diligence — Dependency Hardening Phase 1

## Overall result

**PASS with minor non-blocking concerns.**

All five ACs are materially satisfied. Main concerns are documentation freshness/provenance and current diff breadth, not acceptance blockers.

## AC results

### AC-1 — Dependency policy/inventory

**PASS**

Evidence:
- Four hardening paths present: `docs/dependencies.md:7-12`
  - remove/replace internally
  - optionalize
  - pin and audit
  - vendor with provenance
- Vendoring responsibility warning present: `docs/dependencies.md:14`
- Later removals require characterization tests first: `docs/dependencies.md:16`
- `mutagen` intentionally retained due high-consequence metadata writing: `docs/dependencies.md:18`, `docs/dependencies.md:53`
- Inventory/import sites accurate against current imports:
  - `beautifulsoup4`: `qobuz_dl/core.py`
  - `colorama`: `qobuz_dl/color.py`
  - `mutagen`: `qobuz_dl/metadata.py`, `qobuz_dl/utils.py`
  - `pathvalidate`: `qobuz_dl/core.py`, `qobuz_dl/downloader.py`
  - `pick`: `qobuz_dl/core.py`
  - `requests`: `qobuz_dl/bundle.py`, `qobuz_dl/core.py`, `qobuz_dl/downloader.py`, `qobuz_dl/qopy.py`
  - `tqdm`: `qobuz_dl/downloader.py`

### AC-2 — Python/Ruff metadata

**PASS**

Evidence:
- `requires-python = ">=3.10"`: `pyproject.toml:12`
- Ruff target `py310`: `pyproject.toml:48`
- No stale Python 3.8 build comment; current comment is generic license/backend metadata: `pyproject.toml:1-4`
- Metadata remains minimal: `pyproject.toml:7-58`

### AC-3 — CI matrix/workflow

**PASS**

Evidence:
- CI matrix is `3.10` + `3.13`: `.github/workflows/ci.yml:20-21`
- Keeps uv sync: `.github/workflows/ci.yml:35-36`
- Keeps Ruff format/lint: `.github/workflows/ci.yml:38-42`
- Keeps Pytest: `.github/workflows/ci.yml:44-45`
- Keeps CLI smoke: `.github/workflows/ci.yml:47-48`
- Keeps build: `.github/workflows/ci.yml:50-51`
- No pip/direct-python default workflow in CI.

### AC-4 — Python >=3.10 docs alignment

**PASS**

Evidence:
- Installation says Python 3.10+: `docs/installation.md:4-9`
- Packaging says Python 3.10+: `docs/packaging.md:42`
- Testing says CI matrix is Python 3.10 + 3.13: `docs/testing.md:97`
- AGENTS aligns to Python 3.10 + 3.13: `AGENTS.md:37`
- README uses uv and does not mention Python 3.8: `README.md:24-36`

Remaining Python 3.8 references found only in historical SDLC/artifact material and incidental lockfile URLs/hashes, which is allowed by AC-4.

Non-blocking note:
- `docs/development.md:30` uses `uv run python -c ...` as a diagnostic. This is not “direct python” as the default workflow, but if the project wants zero `python` command examples, this is the only notable current doc example.

### AC-5 — Lockfile + validation evidence

**PASS based on recorded evidence; not independently re-run**

Evidence:
- `uv.lock` baseline refreshed to `requires-python = ">=3.10"`: `uv.lock:3`
- Lockfile diff is consistent with dropping Python 3.8/3.9 resolution branches and wheels; no package version changes observed in `uv.lock`.
- Validation evidence recorded in `artifacts/dependency-hardening/implementation-handoff.md:34-42`:
  - `uv sync --dev --python 3.10`
  - `uv sync --dev`
  - `just ci`

Validation gap:
- I did not re-run `just ci` or sync commands during this read-only pass to avoid generating/modifying local artifacts. The handoff evidence claims all required commands passed.

## Missed/stale issues

1. **Possibly stale “Last verified” note**
   - `docs/packaging.md:55-57` says the page reflects commit `5e1f644`, but the page now contains newer Python 3.10 baseline content. This is not an AC blocker, but it is stale documentation metadata.
   - Clearly in-scope fix: update or remove the “Last verified” section.

2. **Current diff includes source-file churn**
   - Current diff includes multiple `qobuz_dl/*.py` changes, mostly Ruff import sorting/formatting plus one user-facing install string update in `qobuz_dl/core.py`.
   - This may be pre-existing work, but if bundled into Phase 1 it is broader than pure dependency-policy/metadata/docs/CI work.
   - Not an AC blocker, but provenance should be confirmed before commit.

## Scope drift

- No dependency removal/replacement was attempted.
- No vendoring was added.
- No new runtime dependency was introduced.
- Potential drift is limited to source formatting/import-order churn in `qobuz_dl/`.

## Lockfile churn concerns

Low concern:
- `uv.lock` changed substantially by line count, but the meaningful churn appears tied to the Python baseline change:
  - `requires-python` changed from `>=3.8` to `>=3.10`
  - older resolution markers/wheels removed
  - package versions did not appear to change

## Clearly in-scope fixes

- Update/remove `docs/packaging.md:55-57` stale “Last verified” note.
- Optionally replace `docs/development.md:30` with a non-`python` diagnostic if strict zero Python command examples are desired.