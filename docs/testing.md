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

Run the full local gate:

```sh
just ci
```

Run individual checks:

```sh
just fmt-check
just lint
just test
just smoke
just build
```

## GitHub Actions CI/CD

GitHub Actions runs the CI gate on pushes and pull requests to `master`/`main`. Maintainers can also start the workflow manually with `workflow_dispatch`.

The CI matrix runs on Python 3.10, the minimum supported runtime, and Python 3.13, the latest target currently used by the project. Each matrix job installs dependencies with `uv sync --dev --frozen`, then runs formatting, linting, tests, CLI smoke checks, and the package build.

The workflow uses read-only repository permissions. The Python 3.13 job uploads the built `dist/` files as the `qobuz-dl-dist` artifact for release/download inspection.

Apply formatting:

```sh
just fmt
```

Apply safe lint fixes:

```sh
just lint-fix
```

## Build testing

The build check verifies that the source distribution and wheel can be built from `pyproject.toml`:

```sh
just build
```

## Smoke testing

The smoke test verifies that the installed CLI starts and exposes help for each command:

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

The CI and local `just ci` gate also build the package. This catches packaging metadata errors that import and CLI tests can miss.

## Good next tests

Add coverage in this order:

1. CLI parsing and command defaults
2. Downloaded-ID database behavior
3. Filename and path sanitization
4. Last.fm parsing with static HTML fixtures
5. Qobuz API client behavior with mocked HTTP responses
6. Optional integration tests guarded by credentials and explicit markers
