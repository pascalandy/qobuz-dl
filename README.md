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

You'll need Git, `uv`, and an **active Qobuz subscription**. Run this fork without installing the app:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl
```

For a persistent CLI, optionally install the tool and run `qobuz-dl` directly:

```sh
uv tool install git+https://github.com/pascalandy/qobuz-dl.git
qobuz-dl
```

See [Installation](docs/installation.md) for source selection, reproducible revisions, first-run setup, reinstall instructions, and the install verifier.

## Qobuz access and project status

This is an unofficial Beta project. It is not affiliated with or certified by Qobuz. The current client derives app parameters from Qobuz's public web bundle, so Qobuz changes can break setup or downloads without notice. You still need an eligible Qobuz account and subscription.

The public Qobuz documents linked by this project do not prove that Qobuz currently approves this client. They also do not establish a current contract or legal compliance for your use. Read [Qobuz access and project status](docs/qobuz-access.md) for the decision and its evidence limits.

## Examples

Download an album while requesting the highest hi-res tier the CLI supports:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb --quality 27
```

Download an album into a library-friendly folder layout with embedded original-quality artwork:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb \
  --quality 27 \
  --folder-format "{albumartist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]" \
  --track-format "{tracknumber}. {tracktitle}" \
  --embed-art \
  --og-cover
```

Run interactive mode with a limit of 10 results:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun -l 10
```

Download the first album result for a search:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky playboi carti die lit
```

See [Use cases](docs/use-cases.md) for library-building workflows, and [Examples](docs/examples.md) for download mode, Last.fm playlists, interactive mode, lucky mode, and duplicate-tracking behavior.

## Usage

```text
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl [-h] [--version] [-r] [-p] [-sc] {fun,dl,lucky} ...
```

Commands:

* `fun` — interactively search Qobuz and queue downloads
* `dl` — download Qobuz/Last.fm URLs or URLs from a text file
* `lucky` — search Qobuz and download the first matching results

Run command-level help for detailed options:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl <command> --help
```

See the [CLI reference](docs/cli.md) for global options and command descriptions.

## Documentation

* [Installation](docs/installation.md)
* [Examples](docs/examples.md)
* [Use cases](docs/use-cases.md)
* [Qobuz access and project status](docs/qobuz-access.md)
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

* This application uses the Qobuz API but is not certified by Qobuz
* `qobuz-dl` is unofficial and is not affiliated with Qobuz
* You are responsible for checking the terms and laws that apply to your account, subscription, location, and use
