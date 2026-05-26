# Examples

These examples assume `qobuz-dl` was installed with `uv tool install qobuz-dl`. From a local checkout, prefix commands with `uv run`, for example `uv run qobuz-dl --help`.

## Download mode

Download an album URL in 24-bit, sub-96 kHz quality:

```sh
qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb -q 7
```

Download multiple URLs to a custom directory:

```sh
qobuz-dl dl https://play.qobuz.com/artist/2038380 https://play.qobuz.com/album/ip8qjy1m6dakc -d "Some pop from 2020"
```

Download multiple URLs from a text file:

```sh
qobuz-dl dl this_txt_file_has_urls.txt
```

Download albums from a label and embed cover art into the downloaded files:

```sh
qobuz-dl dl https://play.qobuz.com/label/7526 --embed-art
```

Download a Qobuz playlist in maximum quality:

```sh
qobuz-dl dl https://play.qobuz.com/playlist/5388296 -q 27
```

Download all music from an artist except singles, EPs, and VA releases:

```sh
qobuz-dl dl https://play.qobuz.com/artist/2528676 --albums-only
```

Run this command for all download-mode options:

```sh
qobuz-dl dl --help
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
qobuz-dl dl https://www.last.fm/user/vitiko98/playlists/11887574 -q 27
```

## Interactive mode

Run interactive mode with a limit of 10 results:

```sh
qobuz-dl fun -l 10
```

Enter a search query when prompted:

```text
Logging...
Logged: OK
Membership: Studio

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
qobuz-dl fun --help
```

## Lucky mode

Download the first album result:

```sh
qobuz-dl lucky playboi carti die lit
```

Download the first five artist results:

```sh
qobuz-dl lucky joy division -n 5 --type artist
```

Download the first three track results in 320 kbps quality:

```sh
qobuz-dl lucky eric dolphy remastered --type track -n 3 -q 5
```

Download the first track result without cover art:

```sh
qobuz-dl lucky jay z story of oj --type track --no-cover
```

Run this command for all lucky-mode options:

```sh
qobuz-dl lucky --help
```

## Reset and duplicate tracking

Reset the config file:

```sh
qobuz-dl -r
```

By default, `qobuz-dl` skips already downloaded items by ID and prints this message:

```text
This release ID ({item_id}) was already downloaded
```

To skip this check, add `--no-db` at the end of a command.

To completely reset the downloaded-IDs database, run:

```sh
qobuz-dl -p
```
