# CLI reference

Use `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl` as the default no-install workflow. If you installed the optional persistent tool with `uv tool install git+https://github.com/pascalandy/qobuz-dl.git`, you may replace `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl` with `qobuz-dl`. From a local checkout, keep using `uv run qobuz-dl ...`.

## Usage

```text
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl [-h] [-r | -p | --show-config] [-v] [--debug] [--no-color] [--no-input] [--version] {fun,dl,lucky,help} ...
```

The CLI can download from direct URLs, local text files, interactive search, or best-match search.

On Windows, `--help`, `--version`, and `<command> --help` work when `APPDATA` is missing or empty. Commands that continue into config or database work require a nonempty `APPDATA` value. See [Where auth/config and the database live](use-cases.md#where-authconfig-and-the-database-live) for paths and the missing-`APPDATA` diagnostic.

For the plaintext prompt, stored password digest, and current login transport, see [Account and authentication](use-cases.md#1-account-and-authentication).

## Global options

| Option | Description |
|---|---|
| `-h`, `--help` | Show help and exit. Help wins over every other argument and is available without creating config. |
| `--version` | Show the installed package version and exit. |
| `-r`, `--reset` | Create or reset the config file. It prompts, so it needs a terminal. |
| `-p`, `--purge` | Delete the downloaded-IDs database. It exits `0` whether the database was deleted or already absent, and reports which with `--verbose`. A deletion failure exits `1`, reports the database path, and advises checking its permissions. Purge does not create config or initialize the Qobuz client. Previously tracked releases may download again. |
| `--show-config` | Show config path, database path, and redacted config values. |
| `-v`, `--verbose` | Show progress on stderr. |
| `--debug` | Show debug logs and stack traces on stderr; `QOBUZ_DL_DEBUG=1` does the same. |
| `--no-color` | Never color output. Color is also off for a non-terminal, with `NO_COLOR`, or with `TERM=dumb`. |
| `--no-input` | Never prompt. A command that needs input exits `2` instead. |

`--reset`, `--purge`, `--show-config`, and a command are mutually exclusive; combining them exits `2`. The last five options work before or after a command name, as in `qobuz-dl -v dl URL` or `qobuz-dl dl URL -v`. Long options must be spelled out; abbreviations exit `2`.

## Commands

| Command | Description |
|---|---|
| `fun` | Interactively search Qobuz, select albums/tracks/artists/playlists, queue results, choose quality, and download. |
| `dl` | Download Qobuz URLs, Last.fm playlist URLs, or URLs from a local text file. |
| `lucky` | Search Qobuz and download the first matching result or the first N matching results. |
| `help` | Show help for qobuz-dl or a command; `help dl` prints the same text as `dl --help`. |

A bare `qobuz-dl` exits `2` with usage and a first-run hint; run `qobuz-dl --reset` for first-time setup. An unknown command exits `2` and suggests the closest one.

Run command-level help for detailed options:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl <command> --help
```

## Results and exit codes

`dl`, `lucky`, and `fun` print each finalized audio path on stdout, one per line, as soon as the file is final. A reused verified artifact counts as finalized. A path appears once per run even when several requests resolve to it. Prompts, menus, warnings, and errors go to stderr. A successful run prints nothing on stderr unless you pass `--verbose` or `--debug`, and neither option changes stdout or the exit code.

| Exit | Meaning |
|---|---|
| `0` | Every requested item is finalized or skipped by your own filter, such as `--albums-only` or an empty release |
| `1` | At least one item failed for a lasting reason, such as a quality refusal under `--no-fallback`, a demo, a path conflict, no search match, or a permanent HTTP error |
| `2` | An invalid source, text file, or search query; nothing ran and no login happened |
| `75` | Every failure was temporary: a timeout, a dropped connection, HTTP 5xx or `429`, or exhausted rate-limit retries. A rerun is safe because verified artifacts are reused |

| `130` | Interrupted with Ctrl-C (SIGINT); files finalized before the interrupt are kept and their paths were already printed |
| `143` | Terminated with SIGTERM, with the same guarantees |

An interrupt outranks every other code, and a permanent failure outranks a temporary one: a run with both exits `1`.

A run that exits `1` or `75` ends its stderr with one line per failure reason and problem, such as `qobuz-dl: 1 of 3 items could not be downloaded: path_conflict`, then the next command: `retry: ...` for a temporary failure, or `see why: qobuz-dl --verbose ...` otherwise.

Login failures exit `1`, or `75` when the login or web-bundle request failed for a temporary reason. Errors name what failed and, when there is one, the command to run next. Stack traces appear only with `--debug`, and every message masks email, password, token, and request-signature values. On Windows, an external `TerminateProcess` cannot be caught, so a process stopped that way exits without the `143` guarantees.

## API rate-limit retries

If a known replay-safe Qobuz API read returns HTTP `429`, qobuz-dl makes up to three total attempts. The policy covers catalog metadata, searches, favorites, user playlists, and the API request that fetches a track's media URL.

A single `Retry-After` header can specify seconds or an HTTP date. If the header is absent, invalid, or ambiguous, qobuz-dl waits one second before the second attempt. It waits two seconds before the third attempt.

The cumulative requested wait is limited to 30 seconds for each API call. If the next wait would exceed the remaining budget, qobuz-dl stops without waiting or sending another request. Press `Ctrl-C` to interrupt a wait.

Login requests and unknown API endpoints remain single-attempt operations. qobuz-dl does not infer a numeric Qobuz quota. Other HTTP failures, transport failures, and invalid JSON do not trigger the retry policy.

When retries run out, the CLI reports `Qobuz API rate limit retries exhausted.` and stops before the next item. It exits `75`, or `1` when an earlier item already failed for a lasting reason. The message omits response bodies, headers, and request parameters.

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

qobuz-dl validates every source before it reads config or logs in. A Qobuz URL must use `https` on `play.qobuz.com`, `open.qobuz.com`, or `www.qobuz.com`, with an optional locale such as `/us-en`, then `album`, `artist`, `track`, `playlist`, or `label`, an optional slug, and the ID. A Last.fm URL must use `https` on `last.fm` or `www.last.fm`, with an optional locale, then `/user/<name>/playlists/<id>`. Query strings and fragments are ignored. Anything else must be an existing UTF-8 text file. A text file may list other text files; including the same file twice keeps both occurrences, but a file that includes itself, directly or through others, is an error. An invalid source exits `2` and names it, with `file:line` when it came from a text file.

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
| `--albums-only`, `--no-albums-only` | For artist/label downloads, skip singles, EPs, and Various Artists releases. |
| `--m3u`, `--no-m3u` | Create, or do not create, `.m3u` playlist files when downloading playlists. |
| `--fallback`, `--no-fallback` | Allow quality fallback, or skip each track that Qobuz marks as a quality downgrade. |
| `-e`, `--embed-art`, `--no-embed-art` | Embed cover art into audio files. |
| `--og-cover`, `--no-og-cover` | Download cover art at original quality when available. |
| `--cover`, `--no-cover` | Download, or skip, `cover.jpg`. |
| `--db`, `--no-db` | `--no-db` disables persistent history for this run: it neither reads nor updates the local database. Verified evidence created earlier in the process can satisfy a later occurrence. For direct track and album requests, an unexplained pre-existing path still conflicts. |
| `--folder-format PATTERN` | Folder naming pattern. |
| `--track-format PATTERN` | Track naming pattern. |
| `-s`, `--smart-discography`, `--no-smart-discography` | For artist discographies, filter likely spam/extras and prefer practical remaster/quality choices. |

Each switch without a value has a `--no-` form. Without either form, the saved config value applies; either form overrides it for one run.

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

Interactive selection accepts comma-separated numbers and ranges, for example `1,3-5`. `fun` needs a terminal: with `--no-input` or piped stdin it exits `2`.

## `lucky` examples

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky "playboi carti die lit"
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type track --limit 3 "artist song"
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type playlist --limit 1 "jazz classics"
```

`--type` accepts `artist`, `album`, `track`, or `playlist`. `-l/--limit` must be a positive integer; `--number` remains a hidden alias for one release.
