# qobuz-dl

Search, explore, and download Lossless and Hi-Res music from [Qobuz](https://www.qobuz.com/). It *just works*™ (2025).

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=VZWSWVGZGJRMU&source=url)

## Features

* Download FLAC and MP3 files from Qobuz
* Explore and download music directly from your terminal with **interactive** or **lucky** mode
* Download albums, tracks, artists, playlists, and labels with **download** mode
* Download music from Last.fm playlists
* Queue support in **interactive** mode
* Duplicate handling with a portable local database
* Support for albums with multiple discs
* Support for M3U playlists
* Download URLs from a text file
* Extended tags

## Quick start

You'll need an **active Qobuz subscription**.

```sh
pip3 install --upgrade qobuz-dl
qobuz-dl
```

Windows users need one extra dependency before installing:

```sh
pip3 install windows-curses
pip3 install --upgrade qobuz-dl
qobuz-dl.exe
```

See [Installation](docs/installation.md) for requirements, first-run setup, and reset instructions.

## Examples

Download an album URL in 24-bit, sub-96 kHz quality:

```sh
qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb -q 7
```

Run interactive mode with a limit of 10 results:

```sh
qobuz-dl fun -l 10
```

Download the first album result for a search:

```sh
qobuz-dl lucky playboi carti die lit
```

See [Examples](docs/examples.md) for download mode, Last.fm playlists, interactive mode, lucky mode, and duplicate-tracking behavior.

## Usage

```text
qobuz-dl [-h] [-r] [-p] {fun,dl,lucky} ...
```

Commands:

* `fun` — interactive mode
* `dl` — input/download mode
* `lucky` — lucky mode

Run command-level help for detailed options:

```sh
qobuz-dl <command> --help
```

See the [CLI reference](docs/cli.md) for the full top-level usage output.

## Documentation

* [Installation](docs/installation.md)
* [Examples](docs/examples.md)
* [CLI reference](docs/cli.md)
* [Module usage](docs/module-usage.md)
* [Dependencies](docs/dependencies.md)
* [Packaging](docs/packaging.md)

## Module usage

`qobuz-dl` can also be used from Python. See [Module usage](docs/module-usage.md).

## Credits

`qobuz-dl` is inspired by the discontinued Qo-DL-Reborn. This tool uses two modules from Qo-DL: `qopy` and `spoofer`, both written by Sorrow446 and DashLt.

## Disclaimer

* This tool was written for educational purposes. I will not be responsible if you use this program in bad faith. By using it, you are accepting the [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf).
* `qobuz-dl` is not affiliated with Qobuz.
