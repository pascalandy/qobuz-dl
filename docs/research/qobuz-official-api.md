# Research: Qobuz official developer/API/SDK documentation

## Summary
Officially accessible Qobuz API documentation appears limited from the provided primary-source excerpts: the public developer portal (`developer.qobuz.com`) returned HTTP 503 during the parent research pass, while two official static PDFs document integration requirements and terms. The official sources confirm that Qobuz exposes an API for third-party apps, requires Qobuz-issued application credentials, supports user/library/playlists/search/playback-related capabilities, and can mutate user data; specific REST endpoint paths were not confirmed in the accessible official materials.

> Note: This document combines parent-session web research, a read-only repository exploration pass, and clearly labeled community evidence. Official endpoint-level documentation was not accessible during the research pass.

## Findings
1. **Official developer portal currently unavailable in the research pass** — `https://developer.qobuz.com` returned HTTP 503 via the parent’s Exa fetch, so endpoint-level official documentation could not be verified from the portal. [Source](https://developer.qobuz.com)

2. **Official integration guidelines reference separate API integration docs** — Qobuz’s official “Apps & UX Guidelines” refer developers to “Qobuz API Integration” documentation on GitHub and state that Qobuz apps use no private API methods, implying third-party developers should have equivalent documented API tools. The actual GitHub integration docs were not available in the supplied excerpts. [Source](https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf)

3. **Official capability inventory: required top-level app areas** — Qobuz requires first-level entries for Search, Playlists, Favorites, Purchases, and Recommendations/Discoveries in third-party integrations. Search should be segmented by Artist, Album, Songs, and Playlists. [Source](https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf)

4. **Official capability inventory: user-library and playlist operations** — The guidelines say integrations must display favorites for artists/albums/tracks, display bought albums/tracks, list and reorder playlists, and support API mutations such as add/remove favorites, edit/create/delete playlists, and add tracks to playlists. [Source](https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf)

5. **Official mandatory product/API features** — Mandatory integration features include login/logout, player controls, search, suggestions, favorites display, add/remove favorites, playlist management, and quality choice. Bonus/optional features include current playlist display, offline mode/import/cache, signup, list reordering, playback history, and social sharing. [Source](https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf)

6. **Official operational guidance** — Qobuz’s guidelines call out pagination, performance, preload/seek behavior, offline timeout, localization, rights/device/login/signup management, caching/reporting, HTTP headers including user information, notifications, and internationalization. This confirms expected API/client behavior areas but not concrete endpoint paths. [Source](https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf)

7. **Official authentication/model notes** — The API Terms require a Qobuz-granted Application ID and Application secret, forbid sharing those credentials, and allow Qobuz to modify, suspend, or limit API access. Apps must respect geoblocking/IP restrictions and must not perform full-service indexing/scraping. [Source](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf)

8. **Official certification/disclaimer requirement** — Applications using the API must display: “This application uses the Qobuz API but is not certified by Qobuz.” [Source](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf)

9. **SDK availability remains unconfirmed from official sources** — The supplied official excerpts mention API integration documentation but do not identify an official SDK package, language binding, repository, or current SDK distribution. Confidence is low until the referenced GitHub/API docs or developer portal can be accessed.

10. **Qobuz Connect is not confirmed as a general third-party API** — A Qobuz Help Center article about Qobuz Connect was not technically informative in the supplied fetch; the search summary suggested Qobuz Connect is not generally documented for third-party apps. Treat Qobuz Connect as not officially documented for general API use based on current evidence.

## Search for the referenced GitHub API documentation

The official Apps & UX Guidelines say to “refer to Qobuz API Integration documentation available on Github,” but the likely historical repository is no longer publicly reachable:

- `https://github.com/Qobuz/api-documentation` returned GitHub 404.
- `https://api.github.com/repos/Qobuz/api-documentation` returned GitHub API 404.
- `https://github.com/Qobuz/api-documentation/blob/master/endpoints/artist/search.md` also returned 404.

No true public fork or mirror of `Qobuz/api-documentation` was found. The strongest clue that it once existed is that older community libraries link to it, for example `taschenb/python-qobuz` describes itself as an unofficial Python library for the `Qobuz-API` and links to `https://github.com/Qobuz/api-documentation`. Search also found old references to paths like `endpoints/artist/search.md`, but not an accessible copy.

Closest substitutes are **not official mirrors**:

- `DJDoubleD/QobuzApiSharp` — unofficial C# client exposing Qobuz v0.2 REST API with generated XML-comment documentation. This is probably the best community endpoint reference because it organizes endpoints by service classes and has generated docs.
- `loxoron218/qobuz-api-rust` / `qobuz-api-rust` on docs.rs — unofficial Rust migration of QobuzApiSharp with broad coverage for auth, content, search, favorites, streaming URL generation, and web-player credential extraction.
- `bbye98/minim` documentation — explicitly says there is no available official documentation for the private Qobuz API and that endpoints were determined by observing HTTP traffic. Useful as a transparent reverse-engineered reference, not as official truth.
- `arthursoares/qobuz_tidal_api_client` — describes a reusable SDK with `docs/api-spec.md` validated from Proxyman captures of official clients. Promising for a modern capture-based spec, but still unofficial and reverse-engineered.
- `markhc/gobuz` — small Go client showing practical endpoint usage for album/artist/track/playlist/search/auth/file URL flows.
- Older clients such as `taschenb/python-qobuz`, `audiogum/clj-qobuz`, and `vvaidy/qobuz` are useful historical evidence that the public GitHub docs existed, but they are stale.

Research conclusion: treat `Qobuz/api-documentation` as deleted/private/unavailable. Use community clients only as triangulation, never as an official source of contract, and keep this project’s docs explicit about that uncertainty.

## Endpoint / capability inventory

### Officially supported capabilities from accessible Qobuz sources
- Authentication/session: login and logout are mandatory app functions; API credentials require Qobuz-issued Application ID and Application secret.
- Search: global search segmented by Artist, Album, Songs/Tracks, and Playlists.
- Suggestions/recommendations: suggestions are mandatory; Recommendations/Discoveries are required first-level areas.
- Favorites: display favorite artists, albums, tracks; add/remove favorites.
- Purchases: display purchased/bought albums and tracks.
- Playlists: list playlists, reorder playlists, create/edit/delete playlists, add tracks to playlists.
- Playback/player: player controls, preload/seek expectations, quality choice.
- Offline/cache: optional offline mode/import/cache; offline timeout guidance.
- UX/API behavior: pagination, performance, localization/i18n, rights/device management, caching/reporting, HTTP headers with user info, notifications.

### Official endpoint paths
No concrete endpoint paths were verified from accessible official documents in the supplied source excerpts.

### Unofficial/community reverse-engineered endpoints — not confirmed official
Community clients and reverse-engineering commonly describe the base URL as:

- `https://www.qobuz.com/api.json/0.2/`

Commonly cited legacy/newer endpoint names include:

- Auth/session: `user/login`, `oauth2/login`, `session/start`
- Metadata: `track/get`, `album/get`, `artist/get`, `label/get`
- Search: `track/search`, `album/search`, `artist/search`, `playlist/search`
- Playlists: `playlist/get`, `playlist/getUserPlaylists`
- Favorites: `favorite/getUserFavorites`
- Streaming/download URL: `track/getFileUrl`, `file/url`

These endpoint names should be treated as unofficial/reverse-engineered unless cross-checked against the unavailable official developer/API integration docs.

## Sources
- Kept: Qobuz Apps & UX Guidelines V1.0 (https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf) — official Qobuz integration/UX document; strongest accessible primary source for capabilities and required app behavior.
- Kept: Qobuz API Terms of Use (https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf) — official primary source for credential model, API restrictions, geoblocking, anti-scraping, and disclaimer requirements.
- Kept with caveat: Qobuz developer portal (https://developer.qobuz.com) — official developer domain, but returned HTTP 503 during the research pass and could not be used to verify endpoints.
- Dropped/limited: Qobuz Help Center article about Qobuz Connect — supplied fetch was not technically informative; no endpoint/API details confirmed.
- Dropped/limited: Community endpoint lists and clients — useful for practical compatibility clues but not official; endpoint names listed above only as reverse-engineered evidence.

## Deprecated / changed areas
- The official Terms explicitly reserve Qobuz’s right to modify, suspend, or limit the API, so endpoint stability cannot be assumed from unofficial clients.
- Community evidence suggests possible auth/download evolution from older `user/login` and `track/getFileUrl` names toward newer `oauth2/login`, `session/start`, and `file/url` flows, but this was not confirmed in official docs.
- Qobuz Connect appears not to have broadly available technical third-party documentation in the supplied evidence.

## Confidence / gaps
- **High confidence:** Qobuz has official third-party API terms, requires issued app ID/secret, and officially supports search, favorites, purchases, playlists, playback controls, quality selection, and user-data mutation capabilities.
- **Medium confidence:** The API is intended to expose the same non-private methods used by Qobuz apps, based on the official guidelines.
- **Low confidence:** Exact endpoint paths, request/response schemas, auth token/session flows, streaming URL semantics, and SDK availability.
- **Main gaps / next steps:** Retry `developer.qobuz.com`; locate the referenced “Qobuz API Integration” GitHub documentation; verify whether official SDKs exist; compare any official endpoint reference against current community clients; confirm whether Qobuz Connect has a partner-only technical API.