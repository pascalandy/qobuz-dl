# Changelog

All notable changes to this fork of `qobuz-dl` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-06-12

First production-ready release of this fork.

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
