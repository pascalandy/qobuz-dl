We are working in my fork of `qobuz-dl` at:

/Users/andy16/Documents/github_local/qobuz-dl

Important repo context:
- This is a Python CLI project for downloading/searching Qobuz music.
- Use `uv` by default for all Python/project commands.
- Do NOT use `pip`, `pip3`, direct `python`, or `python3` as the documented/default workflow.
- Local dev commands should use `uv run ...`.
- Global/prod CLI may exist at `/Users/andy16/.local/bin/qobuz-dl`; avoid confusing it with the local checkout.
- For the local fork, use:
  - `uv run qobuz-dl ...`
  - or shell alias `qdl-dev`, defined in chezmoi managed zsh config

Chezmoi/dotfiles context:
- My shell config is managed with Chezmoi.
- Do not edit `~/.zshrc` directly.
- Source of truth is:
  `/Users/andy16/.local/share/chezmoi/dot_zshrc`
- The dev alias is:
  `alias qdl-dev='cd "$HOME/Documents/github_local/qobuz-dl" && uv run qobuz-dl'`

Current tooling foundation:
- `pyproject.toml` contains project metadata, dev dependencies, Ruff config, and Pytest config.
- `uv.lock` is committed and should stay in sync.
- `justfile` provides local commands:
  - `just sync`
  - `just fmt`
  - `just fmt-check`
  - `just lint`
  - `just lint-fix`
  - `just test`
  - `just smoke`
  - `just build`
  - `just ci`
- CI is in `.github/workflows/ci.yml`.
- CI runs on `master` and `main`, Python `3.10` and `3.13`.
- CI uses `uv`, Ruff, Pytest, CLI smoke test, and `uv build`.

Quality rules:
- Before finishing implementation, run `just ci`.
- Do not add tests that require Qobuz credentials, active subscription, live Qobuz API, live Last.fm pages, or real media downloads by default.
- Network behavior should be mocked.
- Live API/download checks should be opt-in integration tests only.

Docs structure:
- `README.md` is the concise front door.
- Detailed docs live under `/docs`:
  - `docs/INDEX.md`
  - `docs/installation.md`
  - `docs/examples.md`
  - `docs/cli.md`
  - `docs/module-usage.md`
  - `docs/dependencies.md`
  - `docs/development.md`
  - `docs/packaging.md`
  - `docs/testing.md`
- Keep docs updated when behavior/tooling changes.
- Use `pa-doc-update` if docs are impacted by a change.

Packaging notes:
- `setup.py` is intentionally minimal:
  `from setuptools import setup`
  `setup()`
- Package metadata lives in `pyproject.toml`.
- Build backend is setuptools with `setuptools>=61,<77` for accepted license metadata.
- `uv build` must pass.

Recent important decisions:
- README was decoupled into focused docs.
- Installation docs now use `uv tool install qobuz-dl`.
- Development docs explain global/prod CLI vs local fork workflow.
- Testing foundation was added with Ruff, Pytest, Just, CI, and smoke/build checks.
- `.gitignore` ignores local downloads, macOS files, Python caches, `.venv`, `.cache`, `.pytest_cache`, coverage, `build`, and `dist`.

Start by checking:
1. `git status --short`
2. relevant files for the task
3. run `just ci` before finalizing code/tooling changes

Please continue from this context and keep the work clean, minimal, and production-quality.
