# AGENTS.md — qobuz-dl fork

We are working in the local fork at:

```text
/Users/andy16/Documents/github_local/qobuz-dl
```

## Agent operating contract

- This is a Python CLI project for downloading/searching Qobuz music.
- Use `uv` by default for Python/project commands.
- Do not document or default to `pip`, `pip3`, or bare `python`/`python3` workflows outside `uv`.
- Run local project entry points through `uv run ...`, especially `uv run qobuz-dl ...`.
- A global/prod CLI may exist at `/Users/andy16/.local/bin/qobuz-dl`; do not confuse it with this checkout.
- Before finishing implementation, tooling, packaging, or docs changes, run `just ci` unless explicitly blocked.

## Local development pointers

Canonical details live in [`docs/development.md`](docs/development.md).

- Local fork command: `uv run qobuz-dl ...`
- Optional shell alias: `qdl-dev`
- The `qdl-dev` alias and shell config are Chezmoi-managed.
- Do not edit `~/.zshrc` directly; edit `/Users/andy16/.local/share/chezmoi/dot_zshrc` if shell config changes are needed.

## Testing and quality rules

Canonical details live in [`docs/testing.md`](docs/testing.md).

- Main proof gate: `just ci`
- Common commands are exposed by the `justfile` (`just test`, `just lint`, `just fmt-check`, `just smoke`, `just build`, etc.).
- Default tests must not require Qobuz credentials, an active subscription, live Qobuz API calls, live Last.fm pages, or real media downloads.
- Mock network behavior by default.
- Live API/download checks must be opt-in integration tests only.

## Packaging and dependency rules

Canonical packaging details live in [`docs/packaging.md`](docs/packaging.md).
Canonical dependency policy and inventory live in [`docs/dependencies.md`](docs/dependencies.md).

- Package metadata, dependencies, entry points, and package discovery belong in `pyproject.toml`.
- `setup.py` is intentionally minimal; do not reintroduce duplicate metadata there.
- `uv.lock` is committed and should stay in sync with dependency/metadata changes.
- Keep `requirements.txt` synchronized while it exists.
- Current runtime dependency policy intentionally keeps `mutagen>=1.47,<2` as the retained pinned/audited dependency.
- `qobuz_dl/http.py` is the production HTTP boundary; do not bypass it for new network behavior.

## Documentation rules

Documentation map: [`docs/INDEX.md`](docs/INDEX.md).

- `README.md` is the concise front door.
- Detailed docs live under `docs/`.
- Keep docs updated when behavior, tooling, packaging, or dependency policy changes.
- Use `pa-doc-update` when docs are impacted by an implementation change.

## Start checklist

1. Run `git status --short`.
2. Read the relevant files and docs for the task.
3. Keep changes minimal and production-quality.
4. Run `just ci` before finalizing code/tooling changes, unless blocked and reported.
