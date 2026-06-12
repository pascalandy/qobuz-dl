# Contributing

Thanks for your interest in improving `qobuz-dl`. This document covers the essentials; the canonical details live in [`docs/`](docs/INDEX.md).

## Setup

Requirements: [uv](https://docs.astral.sh/uv/) and [just](https://github.com/casey/just) (optional but recommended).

```sh
git clone https://github.com/pascalandy/qobuz-dl.git
cd qobuz-dl
just sync        # or: uv sync --dev
```

## Workflow

Run everything through `uv`; never document or default to bare `pip`/`python`.

| Command | Purpose |
| --- | --- |
| `just test` | Run the test suite |
| `just lint` | Lint with ruff |
| `just fmt` | Format with ruff |
| `just smoke` | CLI smoke checks |
| `just ci` | Full local quality gate (format check, lint, tests, smoke, build) |

`just ci` must pass before any change is considered done.

## Ground rules

- **Tests are offline.** The default test suite must never need Qobuz credentials, a subscription, live network calls, or real media downloads. Mock the network. Live checks are opt-in integration tests only.
- **`qobuz_dl/http.py` is the only HTTP boundary.** Route any new network behavior through it.
- **Packaging lives in `pyproject.toml`.** Keep `uv.lock` and `requirements.txt` in sync with dependency changes. `setup.py` stays minimal.
- **New runtime dependencies need a strong justification.** The fork intentionally keeps `mutagen` as its only runtime dependency; see [docs/dependencies.md](docs/dependencies.md).
- **Update docs with behavior changes.** `README.md` is the concise front door; details belong in `docs/`. Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes.
- **Add a regression test for every bug fix.**

## Releases

1. Update the version in `pyproject.toml`, refresh `uv.lock` (`uv lock`), and update `CHANGELOG.md`.
2. Run `just ci`.
3. Commit, then tag `vX.Y.Z` (must match the package version) and push the tag.
4. The [release workflow](.github/workflows/release.yml) runs the gates, builds the package, and publishes a GitHub release with artifacts.

## License

By contributing you agree your contributions are licensed under [GPL-3.0](LICENSE), the project license.
