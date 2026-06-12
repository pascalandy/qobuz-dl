# Packaging

## Current state

`qobuz-dl` uses modern Python packaging metadata in `pyproject.toml` and uses `uv` as the default project workflow.

- Build backend: `setuptools.build_meta`
- Build requirements: `setuptools>=61,<77` and `wheel`
- Project metadata source: `[project]` in `pyproject.toml`
- License metadata: `{ text = "GPL-3.0-only" }`, which is accepted by the configured setuptools backend range
- Console scripts: `qobuz-dl` and `qdl`, both pointing to `qobuz_dl:main`
- Package discovery: `qobuz_dl*`
- Lock file: `uv.lock`
- Source distribution manifest: `MANIFEST.in`
- Default local commands: `uv sync` and `uv run ...`

`setup.py` remains as a minimal setuptools shim:

```python
from setuptools import setup

setup()
```

Keep package metadata, dependencies, entry points, and package discovery in `pyproject.toml`. Do not reintroduce duplicate metadata in `setup.py`.

Keep source distribution ownership in `MANIFEST.in`. It includes the README, license, legacy `requirements.txt`, markdown docs, tests, and test fixtures so source archives preserve the project documentation and offline test inputs.

Use `uv` for local installs, lockfile updates, command execution, and package builds. Do not make `pip` or direct `python` commands the documented default.

## Dependency sources

Runtime dependencies are declared in `pyproject.toml`. The default runtime dependency set is intentionally small:

- `mutagen>=1.47,<2`

`requirements.txt` still lists the same runtime dependency for compatibility with workflows that install from requirements files. Keep it synchronized when runtime dependencies change. Project-owned replacements now cover terminal colors, generated-name sanitization, interactive prompts, Last.fm fixture parsing, progress reporting, and HTTP calls.

The supported runtime baseline is Python 3.10 or newer. Keep `requires-python`, the CI matrix, documentation, and `uv.lock` aligned when the baseline changes.

## Local artifacts

`.gitignore` excludes local download output and common build or environment artifacts, including:

- `Qobuz Downloads`
- `.DS_Store`
- `__pycache__/` and Python bytecode
- `*.egg-info/`
- `build/` and `dist/`
- `.venv/`
- `.cache/` and `.pytest_cache/`
- `.coverage` and `htmlcov/`

## Releases

Releases are tag-triggered through GitHub Actions (`.github/workflows/release.yml`).

Release steps:

1. Update `version` in `pyproject.toml` and refresh the lock file with `uv lock`.
2. Document the changes in `CHANGELOG.md`.
3. Run `just ci` locally and commit.
4. Tag the commit `vX.Y.Z` (the tag must match the package version) and push the tag.

The workflow re-runs the quality gates (format check, lint, tests), verifies the tag matches the package version, builds the source and wheel distributions with `uv build`, and publishes a GitHub release with the artifacts attached and generated release notes.
