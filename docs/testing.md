# Testing

This project uses `uv` for local environments and command execution. Do not use `pip` or direct `python` commands as the default workflow.

## Current test foundation

The test suite uses:

- `pytest` for unit tests
- `ruff` for linting and formatting
- `just` as the local command runner
- GitHub Actions for CI

Tests live under `tests/`. Tool caches and local environments are ignored through `.gitignore`, including `.cache/`, `.pytest_cache/`, `.venv/`, and coverage output.

## Local setup

Install project and development dependencies:

```sh
uv sync --dev
```

Or use the command runner:

```sh
just sync
```

## Quality checks

`just ci` is the canonical full gate. It runs `uv run --frozen python scripts/check.py`, the same repository check that GitHub Actions uses.

Run it locally:

```sh
just ci
```

The runner performs these checks in order:

1. Check Ruff formatting.
2. Run Ruff linting.
3. Run the pytest suite.
4. From the checkout, run `qobuz-dl --help`, `qobuz-dl --version`, `qobuz-dl dl --help`, `qobuz-dl fun --help`, `qobuz-dl lucky --help`, `qdl --help`, and `qdl --version`.
5. Build exactly one wheel and one source distribution in a temporary directory.
6. Create a temporary virtual environment and install the exact wheel by its absolute path.
7. From an empty directory outside the checkout, verify that `qobuz_dl` imports from the temporary environment.
8. Repeat the seven CLI probes with the installed `qobuz-dl` and `qdl` entry points. Both version commands must print the exact package version.
9. Print the verified wheel's SHA-256 digest and copy the verified wheel and source distribution to `dist/`.

Run individual checks:

```sh
just fmt-check
just lint
just test
just smoke
just build
```

## GitHub Actions CI/CD

GitHub Actions runs the CI gate on pushes to `master` or `main` and on pull requests. Pull requests can target non-default branches, so branch-on-branch pull requests receive the same checks. Generated `graphite-base` branches are excluded. Maintainers can also start the workflow manually with `workflow_dispatch`.

The CI matrix runs the full `scripts/check.py` gate on Python 3.10, the minimum supported runtime, and Python 3.13, the latest project target. Each matrix job installs dependencies with `uv sync --dev --frozen` before it starts the runner.

The workflow uses read-only repository permissions. The Python 3.13 job uploads the built `dist/` files as the `qobuz-dl-dist` artifact for release/download inspection.

A separate tag-triggered release workflow publishes GitHub releases; see [Packaging — Releases](packaging.md#releases).

Apply formatting:

```sh
just fmt
```

Apply safe lint fixes:

```sh
just lint-fix
```

## Build testing

The focused build command verifies that the source distribution and wheel can be built from `pyproject.toml`:

```sh
just build
```

## Focused source smoke testing

The focused smoke command checks the source environment. It verifies that `qobuz-dl` starts and exposes help for each subcommand:

```sh
just smoke
```

This runs:

```sh
uv run qobuz-dl --help
uv run qobuz-dl dl --help
uv run qobuz-dl fun --help
uv run qobuz-dl lucky --help
```

This focused check does not prove the built wheel. Run `just ci` for the installed-wheel proof, including isolated imports and the `qobuz-dl` and `qdl` entry points.

## Test boundaries

Default tests must not require:

- Qobuz credentials
- an active Qobuz subscription
- live Qobuz API calls
- live Last.fm pages
- real media downloads

Network behavior should be tested with mocks. Live API or download tests should be opt-in integration tests only.

## Fixture and mock conventions

Small readable static fixtures live under `tests/fixtures/`. Characterization tests should pair those fixtures with local fakes or `monkeypatch` so references to Last.fm, Qobuz, or media URLs never perform live network calls in the default suite.

HTTP-adjacent tests should prefer local fake response/session classes that implement only the behavior under test, such as `json()`, `raise_for_status()`, `headers`, `read()`, or context-manager entry and exit. Interactive tests should use built-in prompt/input fakes instead of requiring a real terminal or manual input.

The CI and local `just ci` gate build and install the exact wheel before testing its imports and entry points. This catches packaging metadata errors that source checks can miss.

## Good next tests

Add coverage in this order:

1. CLI parsing and command defaults
2. Downloaded-ID database behavior
3. Filename and path sanitization
4. Last.fm parsing with static HTML fixtures
5. Qobuz API client behavior with mocked HTTP responses
6. Optional integration tests guarded by credentials and explicit markers
