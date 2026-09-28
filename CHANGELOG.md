# Changelog

All notable changes to this fork of `qobuz-dl` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Breaking

- `scripts/check.py` (`just ci`) is silent on success except for one stdout line in `sha256sum` format, `<sha256>  dist/<wheel>`, which replaces `verified wheel sha256: <sha256>`. A failing gate exits `1` whatever its own status, and stderr shows its captured output followed by a rerun command. `--help` now prints help instead of running the gates. Each gate runs in its own process group, so an interrupt also stops the tools a gate started
- `scripts/verify_install.py` exits `2` instead of `1` for an invalid revision or extra argument, and `75` instead of `1` when a command times out or the floating source moves during verification. The `+ command` echo on stderr appears only with `--verbose`
- The live verifier (`just live-qobuz`) reads the password through `--password-file PATH|-` and rejects a lone `QOBUZ_DL_LIVE_PASSWORD` with exit `2`. It prints the report path on stdout, keeps stderr empty on success, and exits `130` or `143` instead of `1` for SIGINT or SIGTERM, including during cleanup and report writing
- `qobuz-dl dl`, `lucky`, and `fun` print each finalized audio path on stdout, once per run, and exit with the run's outcome: `1` when any item failed for a lasting reason (previously `0`), `75` when every failure was temporary, such as a timeout, HTTP 5xx or `429`, or exhausted rate-limit retries, and `0` otherwise
- `qobuz-dl` is quiet on stderr by default: progress, purge messages, and other informational lines appear only with `-v/--verbose` or `--debug`. Stack traces appear only with `--debug` or `QOBUZ_DL_DEBUG=1`. Color is off for a non-terminal, with `NO_COLOR`, with `TERM=dumb`, or with `--no-color`. `fun` menus and setup prompts write to stderr
- Ctrl-C exits `130` instead of `0` and SIGTERM exits `143`; finished files are kept. Login and web-bundle failures exit `1`, or `75` when temporary. A missing config without a terminal, `--reset` or `fun` with `--no-input` or piped stdin, a bare `qobuz-dl`, an unknown command, conflicting `--reset`/`--purge`/`--show-config`/command, and a `--limit` below 1 exit `2`. `-h` wins over every other argument, so `qobuz-dl dl -q 99 -h` exits `0`
- The `-sc`, `-ff`, and `-tf` short options are removed; use `--show-config`, `--folder-format`, and `--track-format`. Long options can no longer be abbreviated. `lucky --number` becomes `-l/--limit`; `--number` stays as a hidden alias for one release. `--no-m3u`, `--no-fallback`, `--no-cover`, and `--no-db` are now the negative forms of `--m3u`, `--fallback`, `--cover`, and `--db`
- `import qobuz_dl` no longer calls `logging.basicConfig` or imports the CLI; `qobuz_dl.main` imports it when called
- Sources are validated before config, login, or downloads: anything but an `https` Qobuz URL on `play`, `open`, or `www.qobuz.com`, an `https` Last.fm playlist URL, or a readable text file exits `2` and names the file and line. The lenient parser previously skipped such sources and exited `0`. A text file that includes itself exits `2`. A `lucky` query under three characters exits `2`

### Added

- Global `-v/--verbose`, `--debug`, `--no-color`, `--no-input`, and `--version` work before or after a command; `qobuz-dl help [COMMAND]` matches `COMMAND --help`; an unknown command suggests the closest one; every help lists examples and exit codes
- Each switch gains a `--no-` form, so a saved config value can be overridden for one run in either direction: `--[no-]embed-art`, `--[no-]og-cover`, `--[no-]albums-only`, `--[no-]smart-discography`, `--[no-]m3u`, `--[no-]cover`, `--[no-]fallback`, and `--[no-]db`
- Error text, log records, and tracebacks mask email, password, auth-token, and request-signature values
- `DownloadResult.retryable`, `RunResult`, `QobuzDL.download_sources`, `core.expand_sources`, and `http.is_retryable`; `http.HttpTransportError` and `http.HttpTruncatedError` mark temporary transport failures, and `HttpTruncatedError` is still a `ConnectionError`
- `qobuz_dl.console` holds the command-line conventions shared by every entry point: exit codes, the usage-error format, help precedence, signal exits, color decisions, and secret input
- `scripts/check.py` gains `-v/--verbose` and `--debug` (or `CHECK_DEBUG=1`); GitHub Actions runs it with `--verbose`
- `scripts/verify_install.py` gains `-v/--verbose`, `--debug` (or `VERIFY_INSTALL_DEBUG=1`), and `--timeout DURATION`
- The live verifier gains `--email`, `--password-file`, `--track-id`, `--query`, `--quality`, `-o/--output PATH|-`, and `-v/--verbose`; each input except the password falls back to its existing environment variable, and `QOBUZ_DL_LIVE_PASSWORD_FILE` names a password file

### Changed

- Package maturity is now Beta while the unchanged access model continues to use app parameters derived from Qobuz's public web bundle, as documented in [Qobuz access and project status](docs/qobuz-access.md)
- Every helper script's `--help` lists examples and exit codes, rejects abbreviated long options, and prints usage errors as usage, the error, and `run '<command> --help' for usage`
- A failed artist, label, or playlist lookup no longer ends the run with a traceback; it is reported and the next source runs

## [1.0.0] - 2026-06-12

First 1.0.0 release of this fork.

### Fixed

- Artist, label, and playlist downloads now fetch every page of results. Collections with more than 500 items were previously truncated to the first page silently, both in regular downloads and in `--smart-discography` filtering.
- `--smart-discography` now filters to the requested artist before choosing the best duplicate quality/remaster candidate, so same-title albums by other artists cannot suppress valid requested-artist albums.
- Invalid URLs now print a clear error message instead of crashing. `get_url_info` raises `ValueError` for unrecognizable URLs and `handle_url` reports them cleanly, even before a client is initialized.
- Last.fm playlist downloads skip tracks that have no Qobuz match instead of crashing and aborting the rest of the playlist.
- Copyright tags now use the correct symbols: `(P)` maps to ℗ (phonogram) and `(C)` maps to © (copyright). They were swapped.
- MP3 tagging no longer crashes when the Qobuz API omits the `copyright` field; it falls back to `n/a` like FLAC tagging.
- Favorites API calls (`favorite/getUserFavorites`) now preserve requested favorite type, offset, and limit; the request signature also falls back to the active app secret.
- Bundle extraction failures raise a descriptive `BundleError` instead of a misleading `NotImplementedError("Bundle URL found")`.
- The "search query too short" message printed a literal `{RED}` instead of the color code.
- Very long track names are truncated per file name rather than across the whole path, so deep download directories can no longer corrupt the target directory part of the path.
- `--albums-only` no longer crashes on releases without an artist entry.

### Changed

- The password prompt during `-r` config setup is now hidden (`getpass`) instead of echoing to the terminal.
- Download streaming chunk size raised from 1 KiB to 64 KiB for faster downloads.
- URL text files are read as UTF-8; blank lines are ignored and Windows line endings are handled.
- Package metadata updated for the fork: version 1.0.0, fork repository URLs, PyPI classifiers, and keywords.

### Removed

- Dead code: unused `_get_description` helper.
- Stale `.flake8` configuration (the project lints with ruff).
- The ruff exclusion for `qobuz_dl/qopy.py`; the module is now formatted and linted like the rest of the codebase.

### Internal

- `tqdm_download` renamed to `download_with_progress` (the tqdm dependency was removed earlier in this fork).
- SQLite connections are now closed deterministically.
- Regression tests added for every fix above (68 tests total, all offline).
- CI smoke-tests every subcommand and `--version`.
- New tag-triggered release workflow publishes GitHub releases from read-only build artifacts, with repository write permission reserved for the publish job.

## [0.9.9.10-fork] - 2026-05

Fork baseline, diverging from upstream [vitiko98/Qobuz-DL](https://github.com/vitiko98/Qobuz-DL) 0.9.9.10.

### Changed

- Hardened the runtime dependency surface: removed `beautifulsoup4`, `colorama`, `pathvalidate`, `pick`, `requests`, and `tqdm`; only `mutagen` remains. Project-owned replacements cover terminal colors, filename sanitization, interactive prompts, Last.fm parsing, progress reporting, and HTTP.
- Moved all packaging metadata to `pyproject.toml` with a committed `uv.lock`; `uv` is the default workflow.
- Split the README into focused documents under `docs/`.
- Made CLI help self-documenting with examples for every command.
- Added an offline characterization test suite and GitHub Actions CI.
