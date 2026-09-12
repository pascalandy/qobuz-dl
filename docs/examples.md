# Examples

These examples use `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl`, the recommended no-install workflow. If you installed the optional persistent tool with `uv tool install git+https://github.com/pascalandy/qobuz-dl.git`, you may replace `uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl` with `qobuz-dl`. From a local checkout, keep using `uv run qobuz-dl ...`, for example `uv run qobuz-dl --help`.

## Download mode

Download an album URL in 24-bit, sub-96 kHz quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb -q 7
```

Download multiple URLs to a custom directory:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/artist/2038380 https://play.qobuz.com/album/ip8qjy1m6dakc -d "Some pop from 2020"
```

Download multiple URLs from a text file:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl this_txt_file_has_urls.txt
```

Download albums from a label and embed cover art into the downloaded files:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/label/7526 --embed-art
```

Download a Qobuz playlist in maximum quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/playlist/5388296 -q 27
```

Download all music from an artist except singles, EPs, and VA releases:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://play.qobuz.com/artist/2528676 --albums-only
```

Run this command for all download-mode options:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl --help
```

## Last.fm playlists

Last.fm playlists can be created from listening history or imported from Spotify, Apple Music, and YouTube. Visit:

```text
https://www.last.fm/user/<your profile>/playlists
```

Example:

```text
https://www.last.fm/user/vitiko98/playlists
```

Download a Last.fm playlist in maximum quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl https://www.last.fm/user/vitiko98/playlists/11887574 -q 27
```

The importer builds one Qobuz track search for each complete Last.fm table row. It keeps each row's artist and title pairing, joins text split across nested tags, and preserves the source order. The importer skips rows with an empty artist or title. It also skips rows without a closing `</tr>`, so fields from those rows do not combine with later rows. Repeated complete rows remain available to later download and playlist processing.

## Interactive mode

Run interactive mode with a limit of 10 results:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun -l 10
```

Enter a search query when prompted:

```text
Logging...
Logged: OK

1. Albums
2. Tracks
3. Artists
4. Playlists
I'll search for [number]: 2
Ok, we'll search for tracks
Enter your search: [Ctrl + c to quit]
- fka twigs magdalene
```

`qobuz-dl` displays numbered results. Choose releases with comma-separated numbers and ranges such as `1,3-5`, confirm whether to keep searching, then choose a numbered quality option.

Run this command for all interactive-mode options:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun --help
```

## Lucky mode

Download the first album result:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky playboi carti die lit
```

Download the first five artist results:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky joy division -n 5 --type artist
```

Download the first three track results in 320 kbps quality:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky eric dolphy remastered --type track -n 3 -q 5
```

Download the first track result without cover art:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky jay z story of oj --type track --no-cover
```

Run this command for all lucky-mode options:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky --help
```

## Reset and duplicate tracking

Reset the config file:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -r
```

Direct track, album, Qobuz playlist, and matched Last.fm playlist requests reuse only verified artifacts at the current destination and effective quality. Playlist `.m3u` files keep source order and repeated successful occurrences. Unmatched, unavailable, refused, failed, and conflicted occurrences are omitted without moving later successes.

To disable persistent history reads and writes, add `--no-db` at the end of a command. Verified evidence created earlier in the same process remains available for later occurrences in that process.

To completely reset the downloaded-IDs database, run:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -p
```
