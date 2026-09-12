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
9. Print the verified wheel's SHA-256 digest and copy the verified wheel and the source distribution to `dist/`.

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

## Verify the public Git install

The install verifier checks the same Git source that the public no-install and persistent-install instructions use. This check requires network access and is opt-in:

```sh
just verify-install
```

To verify an exact revision, pass a full 40-character hexadecimal commit SHA:

```sh
just verify-install-revision FULL_40_CHARACTER_COMMIT_SHA
```

The verifier uses temporary uv cache, tool, bin, managed-Python, work, and temp locations. It disables uv config discovery and preserves `HOME`. It scopes `APPDATA`, `LOCALAPPDATA`, and XDG paths to temporary locations for software that honors them.

The actual qobuz-dl probes are limited to `--help` and `--version`. Startup tests prove that these commands do not initialize or write qobuz-dl config. On POSIX systems, qobuz-dl resolves its config from `HOME/.config`, so the verifier does not claim a temporary POSIX qobuz-dl config directory or isolation for stateful qobuz-dl commands.

The floating check resolves the current fork source, records its full commit SHA from `direct_url.json`, and pins the temporary persistent install to that commit. The revision form also confirms that the source resolves to the requested SHA.

The JSON result records the source URL, resolved commit, package and Python versions, console entry points, runtime requirements, install locations, uv versions, and command outcomes. The verifier requires package version `1.0.0`, the `qobuz-dl` and `qdl` entry points, and `mutagen>=1.47,<2` as the only runtime dependency. It also confirms that both temporary environments report the same Git provenance.

The package version is identity metadata, not revision evidence. The Git URL and resolved commit establish provenance.

`just ci` does not run this verifier. Default local and hosted CI remain offline with respect to the fork installation source and do not depend on GitHub availability.

## Test boundaries

Default tests must not require:

- Qobuz credentials
- an active Qobuz subscription
- live Qobuz API calls
- live Last.fm pages
- real media downloads

Network behavior should be tested with mocks. Live API or download tests should be opt-in integration tests only.

`tests/test_auth_contract.py` uses synthetic credentials and blocks sockets. It proves one UTF-8 MD5 operation during CLI setup, unchanged digest forwarding, and the current local login and Favorites request placement. It does not prove which methods or parameter locations the Qobuz server accepts or requires. See [Authentication credential and transport evidence](research/authentication-transport.md).

## Fixture and mock conventions

Small readable static fixtures live under `tests/fixtures/`. Characterization tests should pair those fixtures with local fakes or `monkeypatch` so references to Last.fm, Qobuz, or media URLs never perform live network calls in the default suite.

The Last.fm characterization tests pass static HTML fixtures through the importer with mocked Qobuz search and download boundaries. They prove row pairing, nested text handling, incomplete-row skipping, source order, repeated-row preservation, search queries, and downloaded IDs. These offline tests do not prove that live Last.fm pages are available or still use the fixture's HTML structure.

HTTP-adjacent tests should prefer local fake response/session classes that implement only the behavior under test, such as `json()`, `raise_for_status()`, `headers`, `read()`, or context-manager entry and exit. Interactive tests should use built-in prompt/input fakes instead of requiring a real terminal or manual input.

Rate-limit tests must inject a controlled wall clock and sleep function. Assert the requested waits and call count. Do not delay the test suite.

The CI and local `just ci` gate build and install the exact wheel before testing its imports and entry points. This catches packaging metadata errors that source checks can miss.

## Good next tests

Add coverage in this order:

1. CLI parsing and command defaults
2. Downloaded-ID database behavior
3. Filename and path sanitization
4. Last.fm parsing with static HTML fixtures
5. Qobuz API client behavior with mocked HTTP responses
6. Optional integration tests guarded by credentials and explicit markers
