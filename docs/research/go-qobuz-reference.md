# Research: go-qobuz unofficial client

## Summary

`gitlab.com/dunn.dev/go-qobuz` is a GPL-3.0 Go client for Qobuz published as `v0.1.0` on pkg.go.dev. It is useful future reference material for this fork, especially for authentication hardening, bundle scraping, credential caching, and request-signing tests.

It is **not** an official Qobuz SDK or API contract. Its README explicitly describes Qobuz as using an undocumented API and implements the same reverse-engineered `api.json/0.2` surface already used by this project.

## Source

- Package docs: <https://pkg.go.dev/gitlab.com/dunn.dev/go-qobuz>
- Repository: <https://gitlab.com/dunn.dev/go-qobuz>
- Inspected version: `v0.1.0`
- License: GPL-3.0

## Capabilities observed

### Authentication

The client implements a full reverse-engineered auth flow:

1. Fetch `https://play.qobuz.com/login`.
2. Extract the web-player `bundle.js` URL.
3. Parse `app_id` and candidate app secrets from the bundle.
4. Validate candidate secrets against `track/getFileUrl`.
5. Login through `user/login` with email, password, and `app_id` to obtain `user_auth_token`.

It also exposes a credential-cache abstraction. Cached credentials include:

- `app_id`
- app secret
- `user_auth_token`
- email
- timestamp

The default freshness window is seven days.

### Endpoints and methods

Observed exported methods cover:

- `user/login`
- `artist/search`
- `album/search`
- `artist/get`
- `album/get`
- `track/getFileUrl`
- `favorite/getUserFavorites`
- `favorite/create`

The README says “full API coverage,” but the exported API surface is narrower than this project’s current `qobuz_dl/qopy.py`, which also includes track search, playlist search/get, user playlists, label metadata, and favorite tracks/artists helpers.

### Track URL signing

The client uses the same legacy signed URL pattern as this project:

```text
MD5("trackgetFileUrlformat_id" + formatID + "intentstreamtrack_id" + trackID + request_ts + secret)
```

It requests `track/getFileUrl` with:

- `track_id`
- `format_id`
- `intent=stream`
- `request_ts`
- `request_sig`

### Quality IDs

The package documents these quality constants:

| Format ID | Meaning |
|---:|---|
| `5` | MP3 320 kbps |
| `6` | FLAC 16-bit / 44.1 kHz |
| `7` | Hi-Res up to 24-bit / 96 kHz |
| `27` | Hi-Res up to 24-bit / 192 kHz |

These match the IDs already accepted by `qobuz_dl/qopy.py`.

## Comparison to this fork

Useful overlaps:

- same base API URL: `https://www.qobuz.com/api.json/0.2/`
- same `user/login` token model
- same `track/getFileUrl` signature formula
- same quality IDs
- similar bundle-scraping objective
- similar need for an isolated HTTP boundary

Potentially useful differences:

- more explicit credential object and cache freshness policy
- injectable HTTP transport design
- separate auth, bundle, catalog, search, and favorites files
- tests around endpoint paths, request headers, errors, and signing behavior
- slightly more flexible bundle URL and app ID parsing than the current local `qobuz_dl/bundle.py`

Limitations:

- still reverse-engineered and undocumented by Qobuz
- no official endpoint guarantee
- narrower actual endpoint surface than its README implies
- mutation support exists (`favorite/create`), which should remain out of scope here unless explicitly approved

## Implementation implications

Treat `go-qobuz` as a triangulation source, not a source of truth.

Good future uses:

- compare bundle-scraping regexes when hardening `qobuz_dl/bundle.py`
- adapt the credential-cache concept in Python, without copying implementation mechanically
- add characterization tests for request signing and endpoint parameters
- use its package organization as a reference when splitting `qobuz_dl/qopy.py` into smaller client modules

Avoid:

- claiming official SDK parity based on this package
- importing or shelling out to the Go client
- copying code without considering GPL attribution and project fit
- expanding mutation commands merely because the Go client exposes one

## Confidence

- **High:** The package is an unofficial Go client using the same reverse-engineered `api.json/0.2` family as this project.
- **High:** Its auth and track URL signing patterns align with existing local behavior.
- **Medium:** Its bundle-scraping patterns may be more robust, but should be validated against live Qobuz web-player changes before adoption.
- **Low:** Any endpoint-level implication beyond the observed source code and package docs.
