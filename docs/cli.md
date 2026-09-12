# CLI reference

Use `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl` as the default no-install workflow. If you installed the optional persistent tool with `uv tool install git+https://github.com/pascalandy/qobuz-dl.git`, you may replace `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl` with `qobuz-dl`. From a local checkout, keep using `uv run qobuz-dl ...`.

## Usage

```text
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl [-h] [--version] [-r] [-p] [-sc] {fun,dl,lucky} ...
```

The CLI can download from direct URLs, local text files, interactive search, or best-match search.

On Windows, `--help`, `--version`, and `<command> --help` work when `APPDATA` is missing or empty. Commands that continue into config or database work require a nonempty `APPDATA` value. See [Where auth/config and the database live](use-cases.md#where-authconfig-and-the-database-live) for paths and the missing-`APPDATA` diagnostic.

For the plaintext prompt, stored password digest, and current login transport, see [Account and authentication](use-cases.md#1-account-and-authentication).

## Global options

| Option | Description |
|---|---|
| `-h`, `--help` | Show help and exit. Help is available without creating config. |
| `--version` | Show the installed package version and exit. |
| `-r`, `--reset` | Create or reset the config file. |
| `-p`, `--purge` | Delete the downloaded-IDs database. Deleting it exits with status `0` and reports `The database was deleted.` Finding it already absent exits with status `0` and reports `The database is already absent.` A deletion failure exits nonzero, reports the database path, and advises checking its permissions. Purge does not create config or initialize the Qobuz client. Previously tracked releases may download again. |
| `-sc`, `--show-config` | Show config path, database path, and redacted config values. |

## Commands

| Command | Description |
|---|---|
| `fun` | Interactively search Qobuz, select albums/tracks/artists/playlists, queue results, choose quality, and download. |
| `dl` | Download Qobuz URLs, Last.fm playlist URLs, or URLs from a local text file. |
| `lucky` | Search Qobuz and download the first matching result or the first N matching results. |

Run command-level help for detailed options:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl <command> --help
```

## API rate-limit retries

If a known replay-safe Qobuz API read returns HTTP `429`, qobuz-dl makes up to three total attempts. The policy covers catalog metadata, searches, favorites, user playlists, and the API request that fetches a track's media URL.

A single `Retry-After` header can specify seconds or an HTTP date. If the header is absent, invalid, or ambiguous, qobuz-dl waits one second before the second attempt. It waits two seconds before the third attempt.

The cumulative requested wait is limited to 30 seconds for each API call. If the next wait would exceed the remaining budget, qobuz-dl stops without waiting or sending another request. Press `Ctrl-C` to interrupt a wait.

Login requests and unknown API endpoints remain single-attempt operations. qobuz-dl does not infer a numeric Qobuz quota. Other HTTP failures, transport failures, and invalid JSON do not trigger the retry policy.

When retries run out, the CLI exits nonzero with `Qobuz API rate limit retries exhausted.` The message omits response bodies, headers, and request parameters. A collection stops before it starts the next item.

## Audio rate-limit retries

An audio download uses the same policy. It permits up to three attempts, honors `Retry-After`, uses the fallback waits, and limits cumulative waits to 30 seconds. These limits apply only while qobuz-dl acquires the response.

The policy handles both a returned `429` response and a raised HTTP `429` error. A later successful attempt follows the same transfer, tagging, and finalization path as a direct success.

After qobuz-dl accepts a non-429 response, it never retries that stream, even when it has read no bytes. Read, write, progress, close, and content-length failures do not start another request. qobuz-dl does not append responses, send a `Range` request, or resume a partial transfer.

If acquisition retries run out, the download has the ordinary `failed` state and `request_error` reason. On exhaustion or cancellation, qobuz-dl removes the owned temporary file and does not publish an incomplete final file. A partial album result keeps paths finalized before the failed track.

Cover art, booklets, and other extras remain single-attempt downloads. Non-429 HTTP failures and transport failures do not trigger a retry. The policy does not limit or pace transferred audio bytes.

## `dl` sources

`uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl SOURCE...` accepts:

- Qobuz album URLs
- Qobuz track URLs
- Qobuz artist URLs
- Qobuz label URLs
- Qobuz playlist URLs
- Last.fm playlist URLs
- local text files containing one URL per line; lines starting with `#` are ignored

Examples:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb --quality 7
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl urls.txt --directory Music --no-cover
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://www.last.fm/user/example/playlists/123 --quality 6
```

## Common download options

These options are shared by `fun`, `dl`, and `lucky`.

| Option | Description |
|---|---|
| `-d`, `--directory PATH` | Download directory. |
| `-q`, `--quality QUALITY` | Audio quality: `5` = MP3 320, `6` = FLAC lossless, `7` = 24-bit <=96kHz, `27` = 24-bit >96kHz. |
| `--albums-only` | For artist/label downloads, skip singles, EPs, and Various Artists releases. |
| `--no-m3u` | Do not create `.m3u` playlist files when downloading playlists. |
| `--no-fallback` | Disable quality fallback; skip each track that Qobuz marks as a quality downgrade. |
| `-e`, `--embed-art` | Embed cover art into audio files. |
| `--og-cover` | Download cover art at original quality when available. |
| `--no-cover` | Do not download `cover.jpg`. |
| `--no-db` | Disable persistent history for this run. Do not read or update the local database. Verified evidence created earlier in the process can satisfy a later occurrence. For direct track and album requests, an unexplained pre-existing path still conflicts. |
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

For MP3 quality (`--quality 5`), the default folder name ends with `[MP3]` for both album and direct-track downloads. qobuz-dl still uses a valid custom `--folder-format`.

## Final audio filename behavior

`--track-format` produces one final audio filename component. If the pattern has one trailing lowercase `.mp3` or `.flac` suffix, qobuz-dl removes that suffix before it applies the existing invalid-character and whitespace cleanup. It then appends the extension for the downloaded audio. Album and direct-track downloads use this same rule, so the pattern produces one final audio extension.

If cleanup leaves an empty name or a Windows-reserved first stem, qobuz-dl uses `track-<digest>` plus the original `.flac` or `.mp3` extension. Reserved first stems include `CON`, `PRN`, `AUX`, `NUL`, `COM1` through `COM9`, `LPT1` through `LPT9`, and their recognized superscript variants, with or without another extension. If the complete name is too long, qobuz-dl keeps a whole-character prefix and adds `~<digest>` before the extension. The digest comes from the unmodified formatted name and acts as a deterministic discriminator for repaired and truncated names.

The complete filename, including its extension, stays within the destination filesystem's component-byte limit. qobuz-dl reads that limit from the existing destination directory, including a `Disc N` directory. It uses 255 bytes only when the platform cannot provide a limit. If the required fallback cannot fit, the download fails before writing audio data.

qobuz-dl chooses the final path before checking for an existing file. The same path is used for tagging and is reported by [`DownloadResult.finalized_paths`](module-usage.md#download-results).

This behavior applies only to final audio filename components. It does not repair generated folders or enforce a full-path limit. It also does not prevent collisions caused by general lossy cleanup, an ordinary name that matches a generated repaired name, identical output from a custom format, case folding, Unicode normalization, digest collisions, or concurrent processes that publish the same path. The reserved-name rules are policy checks, not proof on native Windows or macOS. Native platform verification remains tracked in [issue #43](https://github.com/pascalandy/qobuz-dl/issues/43).

## `fun` examples

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun --limit 10
```

Interactive selection accepts comma-separated numbers and ranges, for example `1,3-5`.

## `lucky` examples

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky "playboi carti die lit"
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type track --number 3 "artist song"
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type playlist --number 1 "jazz classics"
```

`--type` accepts `artist`, `album`, `track`, or `playlist`.
