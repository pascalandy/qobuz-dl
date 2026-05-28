# CLI reference

Use `uvx qobuz-dl` as the default no-install workflow. If you installed the optional persistent tool with `uv tool install qobuz-dl`, you may replace `uvx qobuz-dl` with `qobuz-dl`. From a local checkout, keep using `uv run qobuz-dl ...`.

## Usage

```text
uvx qobuz-dl [-h] [--version] [-r] [-p] [-sc] {fun,dl,lucky} ...
```

The CLI can download from direct URLs, local text files, interactive search, or best-match search.

## Global options

| Option | Description |
|---|---|
| `-h`, `--help` | Show help and exit. Help is available without creating config. |
| `--version` | Show the installed package version and exit. |
| `-r`, `--reset` | Create or reset the config file. |
| `-p`, `--purge` | Delete the downloaded-IDs database. Previously tracked releases may download again. |
| `-sc`, `--show-config` | Show config path, database path, and redacted config values. |

## Commands

| Command | Description |
|---|---|
| `fun` | Interactively search Qobuz, select albums/tracks/artists/playlists, queue results, choose quality, and download. |
| `dl` | Download Qobuz URLs, Last.fm playlist URLs, or URLs from a local text file. |
| `lucky` | Search Qobuz and download the first matching result or the first N matching results. |

Run command-level help for detailed options:

```sh
uvx qobuz-dl <command> --help
```

## `dl` sources

`uvx qobuz-dl dl SOURCE...` accepts:

- Qobuz album URLs
- Qobuz track URLs
- Qobuz artist URLs
- Qobuz label URLs
- Qobuz playlist URLs
- Last.fm playlist URLs
- local text files containing one URL per line; lines starting with `#` are ignored

Examples:

```sh
uvx qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb --quality 7
uvx qobuz-dl dl urls.txt --directory Music --no-cover
uvx qobuz-dl dl https://www.last.fm/user/example/playlists/123 --quality 6
```

## Common download options

These options are shared by `fun`, `dl`, and `lucky`.

| Option | Description |
|---|---|
| `-d`, `--directory PATH` | Download directory. |
| `-q`, `--quality QUALITY` | Audio quality: `5` = MP3 320, `6` = FLAC lossless, `7` = 24-bit <=96kHz, `27` = 24-bit >96kHz. |
| `--albums-only` | For artist/label downloads, skip singles, EPs, and Various Artists releases. |
| `--no-m3u` | Do not create `.m3u` playlist files when downloading playlists. |
| `--no-fallback` | Disable quality fallback; skip releases unavailable at the requested quality. |
| `-e`, `--embed-art` | Embed cover art into audio files. |
| `--og-cover` | Download cover art at original quality when available. |
| `--no-cover` | Do not download `cover.jpg`. |
| `--no-db` | Disable duplicate tracking for this run; do not read or update the local database. |
| `-ff`, `--folder-format PATTERN` | Folder naming pattern. |
| `-tf`, `--track-format PATTERN` | Track naming pattern. |
| `-s`, `--smart-discography` | For artist discographies, filter likely spam/extras and prefer practical remaster/quality choices. |

## Format pattern keys

Folder and track format patterns may use these keys where available:

- `artist`
- `albumartist`
- `album`
- `year`
- `sampling_rate`
- `bit_depth`
- `tracktitle`
- `tracknumber`
- `version`

## `fun` examples

```sh
uvx qobuz-dl fun
uvx qobuz-dl fun --limit 10
```

Interactive selection accepts comma-separated numbers and ranges, for example `1,3-5`.

## `lucky` examples

```sh
uvx qobuz-dl lucky "playboi carti die lit"
uvx qobuz-dl lucky --type track --number 3 "artist song"
uvx qobuz-dl lucky --type playlist --number 1 "jazz classics"
```

`--type` accepts `artist`, `album`, `track`, or `playlist`.
