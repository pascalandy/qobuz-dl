# Dependency Hardening Phase 1 — Final Validation

Date: 2026-05-26

## Result

**FAIL** — AC-1 through AC-5 appear satisfied, and the local `uv`/`just ci` checks pass, but the required `git diff --check -- .` gate fails on trailing whitespace in the current diff.

## Acceptance criteria

- **AC-1 — docs/dependencies.md policy paths/vendor/characterization/mutagen/inventory:** PASS
  - `docs/dependencies.md` defines the dependency policy paths: remove/replace internally, optionalize, pin and audit, vendor with provenance.
  - Vendoring requirements are documented with provenance, license, retained API, local modifications, refresh procedure, and tests.
  - Characterization-test expectations are documented before dependency removals.
  - `mutagen` is explicitly retained as pin-and-audit for high-consequence metadata handling.
  - Runtime dependency inventory is present with versions, paths, roles, and import sites.
- **AC-2 — pyproject Python/Ruff/no stale 3.8 metadata:** PASS
  - `pyproject.toml` has `requires-python = ">=3.10"`.
  - Ruff has `target-version = "py310"`.
  - No stale Python 3.8 classifier or build comment found in `pyproject.toml`.
- **AC-3 — CI matrix and gates preserved:** PASS
  - `.github/workflows/ci.yml` matrix is `3.10` and `3.13`.
  - CI gates preserved: `uv sync --dev --frozen`, Ruff format check, Ruff lint, Pytest, CLI smoke test, and `uv build`.
- **AC-4 — AGENTS/docs aligned to Python >=3.10; remaining 3.8 hits scoped:** PASS
  - `AGENTS.md`, installation, packaging, and testing docs align to Python 3.10+.
  - Remaining `3.8`/`py38` hits are historical SDLC docs/artifacts or incidental lockfile hash/URL substrings.
- **AC-5 — lockfile baseline refreshed:** PASS
  - `uv.lock` starts with `requires-python = ">=3.10"`.
  - `uv sync --dev --python 3.10` and `uv sync --dev` both completed without lockfile refresh errors.

## Commands run

| Command | Exit | Notes |
|---|---:|---|
| `git status --short` | 0 | Repo already has many modified/untracked implementation files and artifacts. |
| `test -x /opt/homebrew/bin/rg && echo available || echo missing` | 0 | `/opt/homebrew/bin/rg` is available. |
| `/opt/homebrew/bin/rg -n "3\\.8\|Python 3\\.8\|py38" README.md docs AGENTS.md pyproject.toml .github/workflows/ci.yml uv.lock artifacts/dependency-hardening || true` | 0 | Matches only historical SDLC/artifact references plus incidental `uv.lock` URL/hash substrings. |
| `/opt/homebrew/bin/rg -n "Dependency policy\|Remove or replace internally\|Optionalize\|Pin and audit\|Vendor with provenance\|characterization tests\|mutagen\|Dependency inventory" docs/dependencies.md` | 0 | Required dependency-policy topics found. |
| `/opt/homebrew/bin/rg -n "requires-python\|target-version\|python-version\|ruff format\|ruff check\|pytest\|qobuz-dl --help\|uv build\|uv sync" pyproject.toml .github/workflows/ci.yml justfile AGENTS.md docs/testing.md docs/packaging.md docs/installation.md uv.lock` | 0 | Python/Ruff/CI/local gates confirmed. |
| `uv sync --dev --python 3.10` | 0 | Resolved 23 packages; checked 22 packages. |
| `uv sync --dev` | 0 | Resolved 23 packages; checked 22 packages. |
| `just ci` | 0 | Ruff format check passed; Ruff lint passed; 7 pytest tests passed; CLI help smoke passed; `uv build` succeeded. |
| `GIT_EXTERNAL_DIFF= GIT_PAGER=cat git diff --check -- .` | 2 | Fails on trailing whitespace in `qobuz_dl/qopy.py`. |

## Blockers

Required whitespace gate failure:

```text
qobuz_dl/qopy.py:11: trailing whitespace.
+from qobuz_dl.color import GREEN, YELLOW
qobuz_dl/qopy.py:35: trailing whitespace.
+                "Content-Type": "application/json;charset=UTF-8",
```

No project/source files were modified during this validation. This report file is the only intentional output artifact.

## Confidence

**High** for AC-1 through AC-5 content validation and local test/build health. Overall release confidence is **blocked** until `git diff --check -- .` passes.
