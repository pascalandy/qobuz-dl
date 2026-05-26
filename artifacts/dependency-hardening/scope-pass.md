# Dependency Hardening Phase 1 Scope Pass

## Current status vs Phase 1 plan

- Phase 1 is planned but not implemented yet.
- `pyproject.toml` still declares `requires-python = ">=3.8"` and Ruff `target-version = "py38"`.
- `.github/workflows/ci.yml` still tests `3.8` and `3.13`.
- `uv.lock` still has `requires-python = ">=3.8"` and resolution branches for `<3.9`, `3.9.*`, and `>=3.10`.
- `docs/dependencies.md` is still mostly inventory/update guidance; it is not yet a dependency policy.
- `docs/installation.md`, `docs/packaging.md`, and `AGENTS.md` still describe Python 3.8 support/build constraints.
- `docs/testing.md` has no stale Python 3.8 text, but also does not document the current/target CI matrix.
- `README.md` and `docs/INDEX.md` do not appear to contain stale Python 3.8 references.

## Stale Python 3.8 / py38 references

Current non-SDLC stale references to update:

- `pyproject.toml:3` — build-system comment says older backend is needed for Python 3.8 builds.
- `pyproject.toml:12` — `requires-python = ">=3.8"`.
- `pyproject.toml:48` — Ruff `target-version = "py38"`.
- `.github/workflows/ci.yml:21` — matrix includes `"3.8"`.
- `AGENTS.md:37` — CI described as Python `3.8` and `3.13`.
- `AGENTS.md:42-43` — instructs Python 3.8 compatibility verification.
- `AGENTS.md:68` — setuptools range described as Python 3.8-compatible.
- `docs/installation.md:6` — Python 3.8 or newer.
- `docs/packaging.md:10` — license metadata accepted for Python 3.8 builds.
- `uv.lock:3` — `requires-python = ">=3.8"` plus Python 3.8/3.9 resolution markers and wheels.

SDLC plan docs intentionally mention Python 3.8 as historical/current-state context and should not be treated as stale implementation docs.

## Dependency policy gaps

`docs/dependencies.md` still needs to define:

- The four dependency paths: remove/replace internally, optionalize, pin/audit, vendor with provenance.
- Explicit vendoring rule: vendoring transfers maintenance responsibility and is not automatic risk removal.
- Characterization-test requirement before dependency replacement/removal.
- `mutagen` rationale as intentionally retained because metadata writing is high-consequence.
- Audit expectations and cadence/tooling for retained dependencies.
- Future path per dependency, not just current use sites.

Potential policy ambiguity: Phase 1 says `mutagen` is retained as pinned/audited, but current `pyproject.toml`, `requirements.txt`, and docs list it unpinned. Decide whether Phase 1 only documents a future pin/audit policy or actually pins `mutagen` now.

## Likely files requiring edits

Primary Phase 1 touch surface:

- `docs/dependencies.md` — expand inventory into policy.
- `pyproject.toml` — Python `>=3.10`, Ruff target `py310`, stale build comment.
- `.github/workflows/ci.yml` — replace `3.8` with `3.10`; keep `3.13` unless changed by decision.
- `uv.lock` — refresh after metadata change.
- `docs/installation.md` — Python `>=3.10` requirement.
- `docs/packaging.md` — remove/rewrite Python 3.8 build constraint language.
- `docs/testing.md` — document updated CI matrix and proof commands.
- `AGENTS.md` — update repo instructions and remove Python 3.8 verification guidance.
- `docs/INDEX.md` — only if dependency doc purpose/title changes materially.
- `README.md` — likely no edit needed unless adding explicit Python requirement.
- `requirements.txt` — only if a decision is made to pin `mutagen` or otherwise change runtime dependency declarations.

## Validation commands to run after implementation

```sh
rg "3\.8|Python 3\.8|py38" README.md docs AGENTS.md pyproject.toml .github/workflows/ci.yml
rg "mutagen|vendor|optional|audit|characterization" docs/dependencies.md
uv lock
uv sync --dev --python 3.10
uv sync --dev
just ci
git diff --stat
```

If the lockfile changes more broadly than expected, inspect before proceeding.

## Unapproved product / scope / architecture decisions

- Exact CI baseline matrix: likely `3.10` + `3.13`, but confirm if more versions are desired.
- Whether to pin `mutagen` in Phase 1 or only document that it will be pinned/audited later.
- Which audit tool/process is canonical for retained dependencies.
- Whether to keep `setuptools>=61,<77` for now with updated wording, or modernize license metadata/build backend now.
- Whether `requirements.txt` remains a supported compatibility artifact long term; docs currently say to keep it synchronized.
