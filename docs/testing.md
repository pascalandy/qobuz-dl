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

## Measure coverage

Run the ordinary offline test suite with line and branch coverage:

```sh
just coverage
```

This optional command prints the current coverage and missing lines for `qobuz_dl`. It does not enforce a minimum or run as part of `just ci` or GitHub Actions.

See the [coverage receipt for issue 45](../artifacts/coverage/2026-09-12-issue-45.md) for the dated Python 3.13 measurement, scope, and behavior-linked gaps.

## GitHub Actions CI/CD

GitHub Actions runs the CI gate on pushes to `master` or `main` and on pull requests. Pull requests can target non-default branches, so branch-on-branch pull requests receive the same checks. Generated `graphite-base` branches are excluded. Maintainers can also start the workflow manually with `workflow_dispatch`.

The CI matrix configures these hosted GitHub Actions jobs:

- Ubuntu with Python 3.10
- Ubuntu with Python 3.13
- Windows with Python 3.13
- macOS with Python 3.13

Python 3.10 is the minimum supported runtime. Each job installs dependencies with `uv sync --dev --frozen` before it runs the full `scripts/check.py` gate.

Windows tests exercise CLI startup when `APPDATA` is absent and create final files for ordinary, reserved, empty, and long Unicode names. The macOS test creates a Unicode path, writes FLAC tags, renames the file, and reads it from the final path. These tests use synthetic local media and do not require Qobuz credentials, a subscription, Qobuz API access, or media network access. Each native test skips explicitly on other operating systems, so a Linux simulation does not count as native verification.

The matrix covers only the listed hosted runner images and Python versions. It does not cover every operating system release, Python version, filesystem, or authenticated download path. A workflow definition states the intended matrix; only completed hosted jobs prove a specific revision on Windows and macOS.

The workflow uses read-only repository permissions. The successful Ubuntu Python 3.13 job uploads the built `dist/` files as the `qobuz-dl-dist` artifact for release and download inspection.

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

## Prepare the live Qobuz verifier

The live verifier is disabled by default. Ordinary tests and `just ci` do not read Qobuz credentials or start the verifier's network backend. Prove this gate and the rest of the verifier contract with local fakes:

```sh
uv run --frozen pytest tests/test_live_qobuz_verification.py
```

Do not run the live procedure as part of verifier preparation. [Issue #48](https://github.com/pascalandy/qobuz-dl/issues/48) owns explicit authorization, the account and track inputs, the live run, and the receipt's publication or disposal.

For an authorized run, use an active Qobuz account and one track that you may download. Choose a search query that returns exactly one match for that track within the first 50 results. Keep the credentials out of the repository, shell history, logs, and issue comments.

Run the verifier from the repository root in a temporary subshell. Enter the account values only at the prompts:

```sh
bash -eu <<'LIVE_QOBUZ'
receipt_dir="$(mktemp -d)"

read -r -p 'Qobuz email: ' QOBUZ_DL_LIVE_EMAIL </dev/tty
read -r -s -p 'Qobuz password: ' QOBUZ_DL_LIVE_PASSWORD </dev/tty
printf '\n'
read -r -p 'Authorized Qobuz track ID: ' QOBUZ_DL_LIVE_TRACK_ID </dev/tty
read -r -p 'Search query: ' QOBUZ_DL_LIVE_SEARCH_QUERY </dev/tty
read -r -p 'Quality (5, 6, 7, or 27): ' QOBUZ_DL_LIVE_QUALITY </dev/tty

export QOBUZ_DL_LIVE_EMAIL QOBUZ_DL_LIVE_PASSWORD
export QOBUZ_DL_LIVE_TRACK_ID QOBUZ_DL_LIVE_SEARCH_QUERY QOBUZ_DL_LIVE_QUALITY
export QOBUZ_DL_LIVE_REPORT="$receipt_dir/live-qobuz.json"
export QOBUZ_DL_LIVE=I_UNDERSTAND_THIS_USES_QOBUZ

printf 'Sanitized receipt: %s\n' "$QOBUZ_DL_LIVE_REPORT"
just live-qobuz
LIVE_QOBUZ
```

The subshell removes the input variables from your environment when the command ends. The verifier creates a private temporary config and separate temporary destinations for the interruption probe and the complete download. The private config disables interpolation, so it reads credential values literally. The cleanup phase attempts to remove the private config and both destinations. A passed receipt requires a `passed` cleanup status. Any cleanup failure makes the complete run fail. The report path must be an absolute path to a `.json` file in an existing directory.

The run checks these phases in order:

1. Extract bundle credentials.
2. Log in with the supplied account.
3. Find the authorized track through the supplied search query.
4. Request one signed media URL at the requested quality.
5. Call the production `download_with_progress` path, stop from its `after_write` hook after the first written chunk, and require an empty interruption destination.
6. Download the same track once to the dedicated destination.
7. Require exactly one non-empty finalized path inside the dedicated destination. Validate media properties with Mutagen and require audio payload. Full decoding and integrity verification are outside this check.
8. Fetch one authoritative record for the same authorized track. Compare the final MP3 or FLAC title, artist, album, and track number with that record.
9. Remove the private config and both temporary destinations.

An invalid authoritative record reports `metadata_reference_invalid`. A tag mismatch reports `metadata_mismatch`. These fixed failures do not include the track ID, the reference values, or the final tag values.

The JSON receipt contains its schema version, the full Git SHA, the operating system, the machine type, the Python version, and the requested quality. It reads the obtained format and sample rate from the completed media. It also records FLAC bit depth or MP3 bitrate when applicable. The receipt contains the result, a fixed reason code, each phase status including `cleanup`, and the verifier limits.

During backend work, the verifier captures Python standard output and standard error and disables logging. The command prints only a generic result with a phase and fixed reason code. A `KeyboardInterrupt` during a verification phase becomes an `interrupted` failure. The verifier then attempts cleanup and writes a sanitized receipt. A cleanup failure replaces any earlier result with `cleanup_failed`. If receipt writing fails, the command reports only `report_write_failed` and preserves an existing receipt. The receipt excludes the email, password, password hash, track ID, search query, app credentials, auth token, signed URL, local paths, backend output, and raw exceptions. Inspect the receipt before publication.

An offline test pass proves only that the verifier is prepared and disabled by default. It does not prove that Qobuz accepted the account, found the track, or delivered media. Only the authorized run in issue #48 can provide that evidence.

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

Keep API and media exhaustion scenarios separate. For media streams, cover both returned and raised `429` responses before transfer. Prove that failures after response acceptance do not retry, append another response, or send a `Range` request.

The CI and local `just ci` gate build and install the exact wheel before testing its imports and entry points. This catches packaging metadata errors that source checks can miss.

## Good next tests

Add coverage in this order:

1. CLI parsing and command defaults
2. Downloaded-ID database behavior
3. Filename and path sanitization
4. Last.fm parsing with static HTML fixtures
5. Qobuz API client behavior with mocked HTTP responses
6. Optional integration tests guarded by credentials and explicit markers
