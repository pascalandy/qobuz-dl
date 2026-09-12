# AGENTS.md: qobuz-dl fork

## Agent operating contract

- Python CLI for Qobuz download/search
- Use `uv` by default for Python/project cmds
- Do not doc/default to `pip`, `pip3`, bare `python`/`python3` outside `uv`
- Run local entry pts via `uv run ...`, esp. `uv run qobuz-dl ...`
- A globally installed CLI can differ from this checkout; verify imported source before testing behavior
- Before finishing impl/tooling/packaging/docs changes, run `just ci` unless blocked

## Local development pointers

Canonical details: [`docs/development.md`](docs/development.md)

- Use the current worktree, not a hard-coded machine path or the `qdl-dev` alias that changes directories
- Shell aliases are Chezmoi-managed; follow the source paths in the development guide instead of editing applied shell config

## Find the owner before changing behavior

- For cross-module work, read [Architecture](docs/architecture.md) for data flow, side effects, failure semantics, and the owner/test map
- For automation contracts, read the [agent operation design](docs/feat/2026-09-12-agent-ergonomics/design-agent-ergonomics.md) and its linked implementation plan; proposed commands are not available until implemented
- For current work, query [epic #20](https://github.com/pascalandy/qobuz-dl/issues/20) and open PRs with `gh`; verify base/head commits and distinguish accepted policy, open implementation, and code in this checkout
- Keep discoveries in their owning test or canonical document; use GitHub for live work status and dated artifacts for historical evidence
- Default investigation to help, source, and offline fixtures; bare startup and `--show-config` can initialize missing config, while `QobuzDL` construction creates output/state
- Independent experiments use separate temporary state and output paths through test fixtures; the current CLI has no `--state-dir` flag and concurrent library writers are not supported

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
