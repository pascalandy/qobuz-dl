# Vision: Qobuz API direction

## Request / decision

Decide whether this fork should evolve from a Qobuz downloader into a broader Qobuz API/SDK client, and define the safest direction before planning implementation.

## Mode

AlignmentDraft, with a light DirectionCheck lens.

## Beneficiary

Primary beneficiary: maintainers and future contributors of this `qobuz-dl` fork who need to keep downloads working without turning the project into a brittle, undocumented API clone.

Secondary beneficiary: advanced users who want reliable access to their own Qobuz purchases, favorites, playlists, and downloads from a CLI.

## Current state

The project is a Python CLI focused on search and downloads. It supports album, track, artist, label, playlist, Last.fm, interactive, and lucky-mode flows. Its API client is centered in `qobuz_dl/qopy.py` and uses Qobuz v0.2-style endpoints such as `user/login`, `album/get`, `track/get`, search endpoints, `playlist/get`, `artist/get`, `label/get`, and `track/getFileUrl`.

Official endpoint documentation is not currently accessible. `developer.qobuz.com` returned 503, and the likely historical GitHub repository `Qobuz/api-documentation` returns 404. Official PDFs confirm a third-party API, API terms, required app credentials, and broad capabilities such as search, playlists, favorites, purchases, and quality choice, but they do not confirm concrete endpoint paths.

Community clients provide useful triangulation but not authority. The best current substitutes are QobuzApiSharp, qobuz-api-rust, Minim, gobuz, and capture-based SDK experiments such as `qobuz_tidal_api_client`.

## Desired end state

This fork should become a **well-documented, conservative Qobuz downloader with a safer internal API client**, not a general-purpose Qobuz SDK by default.

The target state is:

- authentication is explicit and honest about official vs scraped credentials;
- endpoint coverage is documented by confidence level: official, inferred, local-used, stale/risky;
- download-critical flows remain stable and tested without live network calls;
- purchases, favorites, and user playlists can become first-class read-only sources if endpoint behavior is validated;
- mutation features such as playlist editing and favorite changes stay out of scope unless explicitly approved later;
- docs clearly state that endpoint-level contracts are not official unless verified from Qobuz primary sources.

## Key decisions / pattern choices

1. **Do not claim official SDK parity.** The project should document Qobuz API/SDK research, but avoid presenting itself as an official SDK or complete client.
2. **Prefer read-only library expansion.** Purchases, favorites, and user playlists fit the downloader mission better than write/mutation operations.
3. **Treat auth modernization as the first implementation concern.** Direct email/password `user/login` is the most fragile area and should not be expanded blindly.
4. **Use community projects as triangulation, not source of truth.** QobuzApiSharp and Minim are useful references, but this project should keep its own endpoint confidence table.
5. **Keep tests offline.** Any new API behavior needs fake responses and characterization tests, not live Qobuz calls in default CI.

## Patterns to avoid

- Do not scrape or index the full Qobuz catalog; official terms warn against full-service indexing/scraping.
- Do not hard-code community endpoint assumptions as if they are official contracts.
- Do not add playlist/favorite mutation commands before read-only auth and source flows are reliable.
- Do not add broad dependencies or async rewrites merely because other SDKs use them.
- Do not document Qobuz Connect as available to third-party clients unless official technical docs appear.

## Success signals

- Maintainers can open `docs/research/qobuz-official-api.md` and immediately see which API claims are official, inferred, or unknown.
- A contributor can identify the local endpoint surface from `docs/research/local-project-capabilities.md` before editing `qobuz_dl/qopy.py`.
- Auth changes reduce user confusion by supporting token-based workflows or clearly explaining why password login is fragile.
- New read-only source features, if added, are backed by mocked tests and documented CLI behavior.
- The README and docs avoid implying official Qobuz affiliation beyond the required API Terms disclaimer.

## Risks and review points

- **Legal/terms risk:** The project already depends on reverse-engineered behavior. Docs must keep the official/unofficial boundary clear.
- **Auth drift risk:** Qobuz may change login, token, or file URL flows. Auth should be isolated behind a smaller client boundary.
- **Scope creep risk:** “API and SDK” can expand into every Qobuz capability. Keep the next phase focused on downloader-aligned read-only capabilities.
- **Maintenance risk:** Community references may be stale. Validate against the local project’s use cases instead of chasing full parity.
- **User trust risk:** Users need precise language about credentials, app secrets, subscriptions, and what the tool can or cannot guarantee.

## Recommendation

Proceed, but with a narrowed direction: build a documented, conservative downloader API client first; defer a general SDK.

One-line reason: the value is real for maintainers and power users, but the official API contract is too unavailable to justify broad SDK claims.

## Recommended next phase

Use `pa-plan-slicer` to split the work into small slices:

1. documentation baseline and endpoint confidence matrix;
2. auth/token modernization spike;
3. internal signed-request helper cleanup;
4. read-only favorites/user-playlists/purchases feasibility slice;
5. CLI/docs update only after one read-only source proves stable.
