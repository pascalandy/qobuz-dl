# AGENTS.md — qobuz-dl fork

Local fork:

```text
/Users/andy16/Documents/github_local/qobuz-dl
```

## Agent operating contract

- Python CLI for Qobuz download/search
- Use `uv` by default for Python/project cmds
- Do not doc/default to `pip`, `pip3`, bare `python`/`python3` outside `uv`
- Run local entry pts via `uv run ...`, esp. `uv run qobuz-dl ...`
- Global/prod CLI may exist at `/Users/andy16/.local/bin/qobuz-dl`; do not confuse w/ checkout
- Before finishing impl/tooling/packaging/docs changes, run `just ci` unless blocked

## Local development pointers

Canonical details: [`docs/development.md`](docs/development.md)

- Local fork cmd: `uv run qobuz-dl ...`
- Optional shell alias: `qdl-dev`
- `qdl-dev` alias + shell config are Chezmoi-managed
- Do not edit `~/.zshrc` directly; edit `/Users/andy16/.local/share/chezmoi/dot_zshrc` if shell config changes needed

## Testing and quality rules

Canonical details: [`docs/testing.md`](docs/testing.md)

- Main proof gate: `just ci`
- Common cmds in `justfile` (`just test`, `just lint`, `just fmt-check`, `just smoke`, `just build`, etc.)
- Default tests must not need Qobuz creds, active subscription, live Qobuz API, live Last.fm pages, or real media downloads
- Mock network by default
- Live API/download checks = opt-in integration tests only

## Packaging and dependency rules

Canonical packaging: [`docs/packaging.md`](docs/packaging.md)
Canonical dependency policy/inventory: [`docs/dependencies.md`](docs/dependencies.md)

- Package metadata, deps, entry pts, package discovery belong in `pyproject.toml`
- `setup.py` intentionally minimal; do not re-add duplicate metadata
- `uv.lock` committed; keep synced w/ dep/metadata changes
- Keep `requirements.txt` synced while it exists
- Runtime dep policy keeps `mutagen>=1.47,<2` as retained pinned/audited dep
- `qobuz_dl/http.py` is prod HTTP boundary; do not bypass for new network behavior

## Documentation rules

Doc map: [`docs/INDEX.md`](docs/INDEX.md)

- `README.md` = concise front door
- Detailed docs under `docs/`
- Update docs when behavior/tooling/packaging/dep policy changes
- Use `pa-doc-update` when docs impacted by impl change

## Start checklist

1. Run `git status --short`
2. Read relevant files/docs for task
3. Keep changes minimal + production-quality
4. Run `just ci` before finalizing code/tooling changes, unless blocked + reported
