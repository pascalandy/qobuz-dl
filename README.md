# qobuz-dl

Build and manage a local music library from [Qobuz](https://www.qobuz.com/) without leaving your terminal. `qobuz-dl` helps collectors and hi-fi listeners search, download, tag, and organize FLAC or MP3 releases from albums, tracks, artists, labels, playlists, Last.fm playlists, or URL lists.

It is made for people who care about managing their own files: pull a new hi-res album into your folder structure, queue a discography intake, turn a playlist into local tracks plus an M3U file, keep cover art with the music, and avoid downloading the same release twice.

[![CI](https://github.com/pascalandy/qobuz-dl/actions/workflows/ci.yml/badge.svg)](https://github.com/pascalandy/qobuz-dl/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://github.com/pascalandy/qobuz-dl/blob/master/pyproject.toml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green.svg)](LICENSE)
[![Changelog](https://img.shields.io/badge/changelog-keep%20a%20changelog-orange.svg)](CHANGELOG.md)

## Features

* Download albums, tracks, artists, playlists, labels, Last.fm playlists, or batches from a text file
* Choose MP3 320, CD-quality FLAC, 24-bit up to 96 kHz, or the highest hi-res tier supported by the CLI
* Explore Qobuz from the terminal with **interactive** search, multi-select queueing, and **lucky** best-match downloads
* Build artist intake runs with `--albums-only` and `--smart-discography`; pull label catalogs with `dl`
* Organize files with folder and track naming patterns using album, artist, year, bit depth, sample rate, and track metadata
* Keep library artwork with `cover.jpg`, embedded cover art, original-quality cover downloads, or no-cover mode
* Write audio tags for FLAC and MP3 files
* Queue support in **interactive** mode
* Duplicate handling with a portable local database
* Support for albums with multiple discs
* Support for M3U playlists
* Hardened dependency footprint: this fork removed the original runtime dependencies on `beautifulsoup4`, `colorama`, `pathvalidate`, `pick`, `requests`, and `tqdm`; only `mutagen` remains for audio metadata. See [Dependencies](docs/dependencies.md) for details.

## Quick start

You'll need an **active Qobuz subscription**. Run with `uvx`; no app install is required:

```sh
uvx qobuz-dl
```

For a persistent CLI, optionally install the tool and run `qobuz-dl` directly:

```sh
uv tool install qobuz-dl
qobuz-dl
```

Use `uv` for user-facing and local project commands. See [Installation](docs/installation.md) for requirements, first-run setup, optional persistent install, and reset instructions.

## Examples

Download an album while requesting the highest hi-res tier the CLI supports:

```sh
uvx qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb --quality 27
```

Download an album into a library-friendly folder layout with embedded original-quality artwork:

```sh
uvx qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb \
  --quality 27 \
  --folder-format "{albumartist}/{album} ({year}) [{bit_depth}B-{sampling_rate}kHz]" \
  --track-format "{tracknumber}. {tracktitle}" \
  --embed-art \
  --og-cover
```

Run interactive mode with a limit of 10 results:

```sh
uvx qobuz-dl fun -l 10
```

Download the first album result for a search:

```sh
uvx qobuz-dl lucky playboi carti die lit
```

See [Use cases](docs/use-cases.md) for library-building workflows, and [Examples](docs/examples.md) for download mode, Last.fm playlists, interactive mode, lucky mode, and duplicate-tracking behavior.

## Usage

```text
uvx qobuz-dl [-h] [--version] [-r] [-p] [-sc] {fun,dl,lucky} ...
```

Commands:

* `fun` — interactively search Qobuz and queue downloads
* `dl` — download Qobuz/Last.fm URLs or URLs from a text file
* `lucky` — search Qobuz and download the first matching results

Run command-level help for detailed options:

```sh
uvx qobuz-dl <command> --help
```

See the [CLI reference](docs/cli.md) for global options and command descriptions.

## Documentation

* [Installation](docs/installation.md)
* [Examples](docs/examples.md)
* [Use cases](docs/use-cases.md)
* [CLI reference](docs/cli.md)
* [Module usage](docs/module-usage.md)
* [Dependencies](docs/dependencies.md)
* [Development](docs/development.md)
* [Packaging](docs/packaging.md)
* [Testing](docs/testing.md)
* [Changelog](CHANGELOG.md)
* [Contributing](CONTRIBUTING.md)

## Module usage

`qobuz-dl` can also be imported as a library. See [Module usage](docs/module-usage.md).

## Credits

This is a maintained fork of [vitiko98/Qobuz-DL](https://github.com/vitiko98/Qobuz-DL). You can support the original author via [PayPal](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=VZWSWVGZGJRMU&source=url).

`qobuz-dl` is inspired by the discontinued Qo-DL-Reborn. This tool uses two modules from Qo-DL: `qopy` and `spoofer`, both written by Sorrow446 and DashLt.

## Disclaimer

* This tool was written for educational purposes. I will not be responsible if you use this program in bad faith. By using it, you are accepting the [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf).
* `qobuz-dl` is not affiliated with Qobuz.
