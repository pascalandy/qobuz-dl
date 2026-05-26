# Dependencies

This page documents the runtime dependencies declared in `pyproject.toml` and `requirements.txt`, and where the code uses them.

## Dependency inventory

| Dependency | Declared version | Used for | Main import sites |
|---|---:|---|---|
| `beautifulsoup4` | unpinned | Parse Last.fm playlist pages | `qobuz_dl/core.py` |
| `colorama` | unpinned | Cross-platform terminal colors and style reset | `qobuz_dl/color.py` |
| `mutagen` | unpinned | Read and write FLAC and MP3 metadata | `qobuz_dl/metadata.py`, `qobuz_dl/utils.py` |
| `pathvalidate` | unpinned | Sanitize generated filenames and paths | `qobuz_dl/core.py`, `qobuz_dl/downloader.py` |
| `pick` | `==1.6.0` | Interactive terminal selection menus | `qobuz_dl/core.py` |
| `requests` | unpinned | Qobuz API calls, Last.fm page fetches, and file downloads | `qobuz_dl/bundle.py`, `qobuz_dl/core.py`, `qobuz_dl/downloader.py`, `qobuz_dl/qopy.py` |
| `tqdm` | unpinned | Download progress bars | `qobuz_dl/downloader.py` |

## Dependency roles

### `beautifulsoup4`

`beautifulsoup4` is imported as `BeautifulSoup` in `qobuz_dl/core.py`. It parses Last.fm playlist HTML so `qobuz-dl` can extract playlist titles and track data.

### `colorama`

`colorama` is centralized in `qobuz_dl/color.py`. The rest of the application imports color constants from that module instead of importing `colorama` directly.

### `mutagen`

`mutagen` handles audio metadata:

- `qobuz_dl/metadata.py` writes FLAC pictures and ID3 tags
- `qobuz_dl/utils.py` reads metadata from MP3 and FLAC files

### `pathvalidate`

`pathvalidate` protects filesystem writes by sanitizing generated names:

- `qobuz_dl/core.py` sanitizes content names
- `qobuz_dl/downloader.py` sanitizes folder, path, and track filename formats

### `pick`

`pick` powers interactive terminal menus in `qobuz_dl/core.py`, including search type, item selection, yes/no prompts, and quality selection.

`pick` is pinned to `1.6.0`. Keep the pin unless a newer version is tested against the interactive flows.

### `requests`

`requests` is the main HTTP client:

- `qobuz_dl/qopy.py` creates the Qobuz API session
- `qobuz_dl/bundle.py` uses a `requests.Session`
- `qobuz_dl/core.py` handles request errors and fetches Last.fm playlists
- `qobuz_dl/downloader.py` downloads media streams and handles HTTP errors

### `tqdm`

`tqdm` renders progress bars during downloads in `qobuz_dl/downloader.py`.

## Dependency source of truth

- `pyproject.toml` is the package metadata source of truth
- `requirements.txt` exists for compatibility with requirements-based installation workflows
- `uv.lock` captures the resolved dependency graph for reproducible local installs

When runtime dependencies change, update `pyproject.toml`, keep `requirements.txt` synchronized, and refresh `uv.lock`.
