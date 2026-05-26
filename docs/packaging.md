# Packaging

## Current state

`qobuz-dl` uses modern Python packaging metadata in `pyproject.toml`.

- Build backend: `setuptools.build_meta`
- Build requirements: `setuptools>=61` and `wheel`
- Project metadata source: `[project]` in `pyproject.toml`
- Console scripts: `qobuz-dl` and `qdl`, both pointing to `qobuz_dl:main`
- Package discovery: `qobuz_dl*`
- Lock file: `uv.lock`

`setup.py` remains as a minimal setuptools shim:

```python
from setuptools import setup

setup()
```

Keep package metadata, dependencies, entry points, and package discovery in `pyproject.toml`. Do not reintroduce duplicate metadata in `setup.py`.

## Dependency sources

Runtime dependencies are declared in `pyproject.toml`:

- `beautifulsoup4`
- `colorama`
- `mutagen`
- `pathvalidate`
- `pick==1.6.0`
- `requests`
- `tqdm`

`requirements.txt` still lists the same runtime dependencies for compatibility with workflows that install from requirements files. Keep it synchronized when runtime dependencies change.

## Local artifacts

`.gitignore` excludes local download output and common build or environment artifacts, including:

- `Qobuz Downloads`
- `.DS_Store`
- `__pycache__/` and Python bytecode
- `*.egg-info/`
- `build/` and `dist/`
- `.venv/`

## Last verified

This page reflects commit `5e1f644`, which moved package metadata from `setup.py` to `pyproject.toml` and added `uv.lock`.
