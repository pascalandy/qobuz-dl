# Use cases

This guide organizes `qobuz-dl` by local-library goal. Examples use `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl`, the recommended no-install workflow. If you installed the optional persistent tool with `uv tool install git+https://github.com/pascalandy/qobuz-dl.git`, you may replace `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl` with `qobuz-dl`. From a local checkout, use `uv run qobuz-dl ...`.

## Library-building workflows for collectors

`qobuz-dl` is most useful when you already think in albums, playlists, folders, tags, and repeatable intake runs. These workflows map common enthusiast jobs to the commands and options documented below.

| Goal | Workflow | Start with |
|---|---|---|
| Add a hi-res album to a local library | Download the album URL with `--quality 27` to request the highest hi-res tier supported by the CLI. Leave fallback enabled to accept a lower available tier, or add `--no-fallback` when you only want the requested quality. | `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --quality 27` |
| Keep clean folder names | Use `--folder-format` and `--track-format` with metadata such as album artist, album, year, bit depth, sample rate, track number, and title. | `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl ALBUM_URL -ff "{albumartist} - {album} ({year})" -tf "{tracknumber}. {tracktitle}"` |
| Intake an artist catalog | Download an artist URL. Add `--albums-only` to skip singles, EPs, and Various Artists releases where applicable; add `--smart-discography` to reduce likely spam/extras and prefer practical remaster/quality choices. | `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/artist/ARTIST_ID --albums-only --smart-discography` |
| Capture a label or playlist | Download label URLs, Qobuz playlist URLs, Last.fm playlist URLs, or a text file of saved URLs. Playlist downloads can create `.m3u` files unless you pass `--no-m3u`. | `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl urls.txt` |
| Avoid duplicate downloads | Let the local downloaded-ID database skip IDs that were already downloaded. Use `--no-db` for a one-off bypass or `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --purge` to reset the database. | `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl ALBUM_URL` |
| Choose an artwork policy | Keep the default `cover.jpg`, embed artwork with `--embed-art`, request original-quality covers with `--og-cover`, or skip cover downloads with `--no-cover`. | `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl ALBUM_URL --embed-art --og-cover` |
| Discover from the terminal | Use `fun` for interactive search with queueing, or `lucky` when a best-match album, track, artist, or playlist search is good enough. | `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun --limit 10` |

## 1. Account and authentication

You need an active Qobuz subscription. `qobuz-dl` creates a local config on first use and stores the account details needed for later commands.

During command startup, `Logged: OK` means the login response supplied a usable token and eligible membership data, and the token was installed for the session. Free accounts and malformed login responses fail before this message; `qobuz-dl` does not print the membership label returned by Qobuz.

### Log in / create the first config

Run any command that requires config, or explicitly reset/create config:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -r
```

The prompt asks for:

- Qobuz email
- Qobuz password
- default download folder
- default quality

If you want max available resolution as your normal default, enter `27` for the default quality. If you leave the first-run quality prompt empty, the current config creator uses `6` / CD quality.

### Where auth/config and the database live

The current implementation stores config and duplicate-tracking state under one per-user directory:

| Platform/runtime | Config file | Downloaded-IDs database |
|---|---|---|
| Linux and macOS | `~/.config/qobuz-dl/config.ini` | `~/.config/qobuz-dl/qobuz_dl.db` |
| Windows | `%APPDATA%\qobuz-dl\config.ini` | `%APPDATA%\qobuz-dl\qobuz_dl.db` |

These paths come from the running process: non-Windows systems use the current user's home directory plus `.config`, and Windows uses the `APPDATA` environment variable. The CLI does not currently use `XDG_CONFIG_HOME` or macOS `~/Library/Application Support`.

The config file stores:

- `email`
- `password`, as an MD5 hash of the Qobuz password
- `app_id`
- `secrets`
- `default_folder`
- `default_quality`
- `default_limit`
- `no_m3u`
- `albums_only`
- `no_fallback`
- `og_cover`
- `embed_art`
- `no_cover`
- `no_database`
- `smart_discography`
- `folder_format`
- `track_format`

Before a command starts authentication or initializes the Qobuz client, the CLI parses and validates the existing config. The configured `default_quality` must be `5`, `6`, `7`, or `27`. `default_limit` must be an integer. Boolean preferences use ConfigParser's standard forms. `1`, `yes`, `true`, and `on` mean true. `0`, `no`, `false`, and `off` mean false. Explicit CLI options still override valid config defaults.

Treat the config file as a secret. The saved password is hashed, not plaintext, but that hash is still used for the tool's login flow. `--show-config` redacts `email`, `password`, `app_id`, `secrets`, `private_key`, and `user_auth_token` if those keys are present, but the actual config file contains the saved values. The current config creator does not write `user_auth_token`; Qobuz login returns that token when a command initializes, and the process keeps it in memory for that run.

On POSIX systems, config creation and reset set the `qobuz-dl` directory to `0700` and `config.ini` to `0600`. Commands that load config also repair these permissions before reading it, without changing the file's contents.

On Windows, config privacy depends on the directory's access control list. POSIX permission guarantees do not apply. If permission repair or config persistence fails, the CLI exits with a storage error that omits credentials and config contents.

The database is a local SQLite file used only for duplicate tracking. It stores downloaded item IDs so repeated runs can skip releases that were already downloaded. It is not required for authentication.

### Move auth/config to another computer

You can copy the config file to another computer to avoid re-entering the Qobuz email, password, default preferences, app ID, and app secrets. This does not bypass Qobuz: commands such as `dl`, `fun`, and `lucky` still log in online when they initialize, reject invalid credentials, and require an eligible active subscription.

1. On the source computer, locate the files:

   ```sh
   uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --show-config
   ```

2. Transfer the displayed `Configuration` file to the destination computer as `config.ini`. Transfer the displayed `Database` file as `qobuz_dl.db` too only if you want to preserve duplicate-tracking history.

3. On Linux or macOS, copy the transferred files into place and restrict them to your user:

   ```sh
   mkdir -p ~/.config/qobuz-dl
   cp /secure-transfer/config.ini ~/.config/qobuz-dl/config.ini
   [ -f /secure-transfer/qobuz_dl.db ] && cp /secure-transfer/qobuz_dl.db ~/.config/qobuz-dl/qobuz_dl.db
   chmod 700 ~/.config/qobuz-dl
   chmod 600 ~/.config/qobuz-dl/config.ini
   [ -f ~/.config/qobuz-dl/qobuz_dl.db ] && chmod 600 ~/.config/qobuz-dl/qobuz_dl.db
   ```

   Replace `/secure-transfer` with the directory where you put the transferred files.

   On Windows PowerShell, place the files under `%APPDATA%\qobuz-dl`:

   ```powershell
   New-Item -ItemType Directory -Force "$env:APPDATA\qobuz-dl"
   Copy-Item .\config.ini "$env:APPDATA\qobuz-dl\config.ini"
   if (Test-Path .\qobuz_dl.db) { Copy-Item .\qobuz_dl.db "$env:APPDATA\qobuz-dl\qobuz_dl.db" }
   ```

   Keep the directory readable only by your Windows user account.

4. If `default_folder` contains an old absolute path or a path from another operating system, edit it before the first download on the new computer.

Use an encrypted transfer or trusted local copy method. Do not paste `config.ini` into issues, chat logs, shell history, public sync folders, or commits. If the copied app ID or app secrets stop working after Qobuz changes its web app, run `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --reset` on the destination computer to refresh the config.

### Check whether config already exists

Show the config path, database path, and redacted config values:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --show-config
```

Short form:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -sc
```

Note: this confirms local configuration exists. If no config exists yet, normal first-run config creation runs before the paths and redacted values are printed. `--show-config` exits before initializing the Qobuz client, so it is not a dedicated login-validation command. Account access is validated when a Qobuz command initializes and talks to Qobuz.

### Reset authentication/config

Use this when credentials changed, the config is broken, app credentials need to be refreshed, or you want a fresh setup:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --reset
```

Short form:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -r
```

`--reset` prompts for Qobuz email, Qobuz password, default download folder, and default quality, fetches the current Qobuz app ID and app secrets, rewrites `config.ini`, and exits before initializing the Qobuz client. It does not delete `qobuz_dl.db`; use `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --purge` if you also want to remove duplicate-tracking history.

The replacement is written to a temporary file in the same directory, then installed atomically. A failure before replacement preserves the previous config's contents.

## 2. Primary downloads

These are the main content-oriented use cases.

### Download a single track

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/track/TRACK_ID
```

With explicit max available quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/track/TRACK_ID --quality 27
```

### Download an album

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID
```

With explicit max available quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --quality 27
```

### Download all albums from an artist

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/artist/ARTIST_ID
```

### Download main artist albums only

Skip singles, EPs, and Various Artists releases where applicable:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/artist/ARTIST_ID --albums-only
```

For a more practical artist-discography filter that tries to reduce likely spam/extras and prefer useful remaster/quality choices:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/artist/ARTIST_ID --smart-discography
```

You can combine both:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/artist/ARTIST_ID --albums-only --smart-discography
```

## 3. Other downloads

### Download a Qobuz playlist

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/playlist/PLAYLIST_ID
```

### Download a label catalog

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/label/LABEL_ID
```

Only main albums from the label:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/label/LABEL_ID --albums-only
```

### Download many URLs from a text file

Create a text file with one URL per line. Lines starting with `#` are ignored.

```text
https://play.qobuz.com/album/ALBUM_ID
https://play.qobuz.com/track/TRACK_ID
# https://play.qobuz.com/artist/SKIPPED_ARTIST_ID
https://play.qobuz.com/playlist/PLAYLIST_ID
```

Then run:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl urls.txt
```

### Download a Last.fm playlist

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://www.last.fm/user/USERNAME/playlists/PLAYLIST_ID
```

## 4. Discovery and selection

Use discovery when you do not already have the exact Qobuz URL.

### Search interactively, select results, and queue downloads

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun
```

Limit the number of search results shown per query:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun --limit 10
```

Interactive mode lets you search for albums, tracks, artists, or playlists, select numbered results, and queue one or more downloads. Selection accepts comma-separated numbers and ranges such as `1,3-5`.

### Lucky download: search and download the first match

By default, `lucky` searches albums:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky "artist album name"
```

Download the first matching track:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type track "artist song title"
```

Download the first matching artist result:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type artist "artist name"
```

Download the first matching playlist:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type playlist "playlist name"
```

Download the first N matches:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --type album --number 3 "search terms"
```

## 5. Download preferences and configuration

Most download preferences can be supplied as command flags for one run. To make a preference permanent, edit the config file shown by `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --show-config`.

### Audio quality

Recommended user-facing choices:

| User choice | CLI quality | Meaning |
|---|---:|---|
| MP3 | `5` | MP3 320 kbps |
| CD quality | `6` | FLAC lossless, 16-bit / 44.1 kHz |
| Max available resolution | `27` | Requests the highest hi-res tier supported by the CLI; with fallback enabled, lower available quality may be used when needed |

Use MP3:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --quality 5
```

Use CD quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --quality 6
```

Use max available resolution for one run:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --quality 27
```

Make max available resolution the persistent default by setting this in the config file shown by `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --show-config`:

```ini
default_quality = 27
```

Advanced note: the CLI also supports `--quality 7` for 24-bit up to 96 kHz, but the simpler product model is MP3, CD quality, or max available resolution.

### Quality fallback behavior

By default, fallback is enabled: if the requested quality is unavailable, `qobuz-dl` can fall back to an available lower quality.

Disable fallback and skip releases unavailable at the requested quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --quality 27 --no-fallback
```

### Download directory

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --directory "Music/Qobuz"
```

Short form:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID -d "Music/Qobuz"
```

### Folder and track naming

Set folder naming for one run:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID \
  --folder-format "{albumartist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]"
```

Set track filename naming for one run:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID \
  --track-format "{tracknumber}. {artist} - {tracktitle}"
```

Short forms:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID \
  -ff "{albumartist} - {album} ({year})" \
  -tf "{tracknumber}. {tracktitle}"
```

Common pattern keys include:

- `artist`
- `albumartist`
- `album`
- `year`
- `sampling_rate`
- `bit_depth`
- `tracktitle`
- `tracknumber`
- `version`

### Cover art behavior

Default behavior downloads `cover.jpg`.

Embed cover art into audio files:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --embed-art
```

Download original-quality cover art when available:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --og-cover
```

Do not download `cover.jpg`:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --no-cover
```

Combine options:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --embed-art --og-cover
```

### Playlist file behavior

By default, playlist downloads can create `.m3u` playlist files. Disable `.m3u` creation:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/playlist/PLAYLIST_ID --no-m3u
```

### Duplicate tracking

By default, `qobuz-dl` records a top-level album or track ID only after that request is genuinely finalized. Type and quality filters, demos, missing download URLs, tagging failures, and partial albums remain unrecorded and retryable. A retry reuses any expected audio files that were already finalized, then downloads the missing files.

Rows already present in the database are trusted as before. `qobuz-dl` does not audit or repair old rows, so use `--no-db` or purge the database when you need to retry an ID that history already marks as downloaded.

Bypass duplicate tracking for one run:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/ALBUM_ID --no-db
```

Delete the downloaded-IDs database so previously tracked releases may download again:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --purge
```

Short form:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -p
```

`--purge` is idempotent for scripts. When the database exists, it exits with status `0` and writes `The database was deleted.` to standard error. When the database is already absent, it exits with status `0` and writes `The database is already absent.` to standard error. A deletion failure exits nonzero, reports the database path, and advises checking its permissions. Purge does not create `config.ini` or initialize the Qobuz client.

### View or edit persistent defaults

Show the config path and redacted settings:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --show-config
```

Then edit the displayed config file to make defaults persistent, for example:

- `default_folder`
- `default_quality`
- `default_limit`
- `no_m3u`
- `albums_only`
- `no_fallback`
- `og_cover`
- `embed_art`
- `no_cover`
- `no_database`
- `folder_format`
- `track_format`
- `smart_discography`

## 6. Troubleshooting and maintenance

### Show help

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --help
```

Command-specific help:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl --help
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun --help
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --help
```

### Show version

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --version
```

### Inspect config and database locations

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --show-config
```

### Recover from a corrupted config

If the config is unreadable, malformed, incomplete, or contains an invalid typed value, the CLI refuses it before authentication and client initialization. The diagnostic identifies the requirement when possible and gives the reset command, but does not echo malformed values or config contents.

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl --reset
```
