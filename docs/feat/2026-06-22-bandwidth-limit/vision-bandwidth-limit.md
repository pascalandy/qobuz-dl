# Vision: bandwidth limit and polite download behavior

## Request / decision

Decide whether `qobuz-dl` should add bandwidth limiting or other polite download controls so it does not consume unbounded Qobuz/media bandwidth, and define the safest direction before implementation planning.

## Mode

DirectionCheck.

Lenses used: How Might We and Pre-Mortem.

How might we let power users download their own Qobuz content responsibly without pretending this CLI has official streamer-device bandwidth guidance?

## Success criteria and evaluation method

Evaluation method: pass/fail against the original FSST criteria.

| Criterion | Status | Evidence |
|---|---:|---|
| Repo download path checked | Pass | `qobuz_dl/http.py` owns `stream_download`; `qobuz_dl/downloader.py` calls it for tracks, covers, and booklets. |
| External evidence checked | Pass | Qobuz API terms, Qobuz audio-format article, RFC 6585, RFC 8216, Spotify rate-limit docs, TIDAL API discussion, YouTube quota docs. |
| Qobuz-specific uncertainty stated | Pass | No public Qobuz media bytes-per-second policy or streamer-device cap was found. |
| Direction pressure-tested | Pass | This artifact names anti-goals, assumptions, risks, options, and a Revise recommendation. |
| Future feature concrete enough to plan | Pass | The recommended feature set names CLI/config, HTTP-boundary, tests, and non-goals. |

## Beneficiary

Primary beneficiary: maintainers and advanced users of this `qobuz-dl` fork who want large downloads to behave predictably and respectfully without turning the project into a hidden high-throughput scraper.

Secondary beneficiary: future contributors who need one clear ownership boundary for network pacing, retries, and download streaming behavior.

## Current state

`qobuz-dl` downloads media at whatever speed the origin and local network allow. The streaming boundary is centralized in `qobuz_dl/http.py::stream_download`, which opens a URL, reads fixed-size chunks, writes them to disk, reports progress, checks `content-length`, and returns the byte count.

The album and track flow in `qobuz_dl/downloader.py` calls `http.stream_download` for audio files, covers, and booklets. Album downloads are sequential across tracks today. There is no CLI/config option for byte-rate limiting, no central request retry/backoff policy, and no special handling for `429 Too Many Requests`.

This is a good starting point: the feature can be added at the HTTP boundary without changing metadata tagging, path formatting, duplicate tracking, or Qobuz endpoint code.

## External evidence

- Qobuz's API terms say Qobuz may limit API calls and content access without notice, forbid damaging service use, and forbid indexing the service or collecting user information. This supports conservative client behavior but does not define a media download speed cap. Source: [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf).
- Qobuz describes network-player playback compatibility for FLAC and other formats from 16-bit/44.1 kHz through 24-bit/192 kHz. This supports the idea that streamer devices consume audio at playback-related bitrates, but it does not prove how Qobuz's own apps buffer or download full files. Source: [Qobuz audio formats article](https://www.qobuz.com/us-en/magazine/story/Qobuz-Vous/The-audio-formats-available-at179478/).
- HTTP `429 Too Many Requests` is the standard signal that a client has sent too many requests in a time window; responses may include `Retry-After`. Source: [RFC 6585 section 4](https://datatracker.ietf.org/doc/html/rfc6585#section-4).
- HLS streaming transfers media through playlists and media segments, with variant bandwidths declared in playlists. This is structurally different from `qobuz-dl` downloading whole file URLs. Source: [RFC 8216](https://datatracker.ietf.org/doc/html/rfc8216).
- Spotify's Web API guidance recommends planning around rolling-window rate limits, respecting `Retry-After`, batching requests, avoiding unnecessary refreshes, studying request patterns, and lazy-loading heavy features. This is strong analogous evidence for API-call politeness, not a Qobuz media-byte cap. Source: [Spotify Web API rate limits](https://developer.spotify.com/documentation/web-api/concepts/rate-limits).
- TIDAL API maintainers publicly stated that `429` responses include `Retry-After` to show when it is safe to retry. This is another music-service signal that client-side backoff matters. Source: [TIDAL API discussion](https://github.com/orgs/tidal-music/discussions/135).
- YouTube Data API uses quotas to preserve service quality and prevent abusive or unfair access; larger quota requests require compliance review. This reinforces the general principle that media platforms expect clients to fit provider capacity and policy. Source: [YouTube Data API quota and compliance audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).

Evidence gap: no public Qobuz document found in this pass defines official request-per-second limits, media transfer caps, streamer prefetch depth, or a recommended third-party downloader bandwidth.

## Options considered

### Option 1: do nothing

This keeps current download speed and avoids new code, but it leaves no user-controlled way to be cautious on large album, artist, label, or playlist downloads. It also misses an obvious HTTP-boundary improvement: graceful handling of provider rate-limit signals.

### Option 2: add a default global bandwidth cap

This matches the user's instinct most directly, but it rests on thin evidence. A default cap could frustrate users who intentionally use `qobuz-dl` as a downloader, not a streamer. It could also create fake confidence by implying Qobuz endorses a specific throughput.

### Option 3: add optional bandwidth limiting plus polite HTTP handling

This is the strongest direction. It gives cautious users an explicit cap, keeps current behavior by default, centralizes pacing in `qobuz_dl/http.py`, and adds provider-friendly behavior for `429`/`Retry-After` without inventing a Qobuz policy.

### Option 4: emulate streamer-unit buffering

This should not be the first version. Streamer devices and apps often use segmented streaming, buffers, adaptive choices, and app-specific policy. `qobuz-dl` receives whole-file URLs. Emulation would be mostly guesswork unless Qobuz publishes or grants partner guidance.

## Recommendation

Revise.

One-line reason: the responsible-client goal is valid, but the feature should ship as optional bandwidth control and central rate-limit/backoff behavior, not as an undocumented default streamer-emulation cap.

## Desired end state

`qobuz-dl` should offer a clearly named, user-configurable way to limit media download throughput while preserving today's unlimited behavior unless the user opts in.

The target state is:

- audio, cover, and booklet downloads can be paced through one HTTP streaming boundary;
- metadata/API requests can respect `429` and `Retry-After` where those signals are available;
- the CLI and config language says "limit download bandwidth" or "polite network behavior", not "simulate Qobuz streamer";
- default behavior remains unlimited until maintainers intentionally choose a conservative default from stronger evidence;
- tests stay offline by using fake responses, fake clocks/sleepers, and mocked retry paths;
- docs state that no public Qobuz bandwidth recommendation was found.

## Proposed feature set

1. Add an optional CLI/config setting for media byte-rate limiting, such as `--download-rate-limit 2MiB/s` or `--download-rate-limit 0` for unlimited. Exact naming should be settled during implementation planning.
2. Implement throttling in `qobuz_dl/http.py::stream_download`, not in album/track-specific code. Use a small token-bucket or paced-sleep helper with injectable time/sleep dependencies for deterministic tests.
3. Keep album and playlist downloads sequential. Do not add parallel downloads as part of this feature.
4. Add central handling for `429 Too Many Requests` on API/text/JSON calls where practical. Respect `Retry-After` when present; otherwise use capped exponential backoff with jitter and a strict retry limit.
5. Expose clear errors when a provider keeps throttling after retries. Do not retry forever.
6. Document that this feature is for local network friendliness and provider politeness, not for bypassing terms, hiding automation, or making high-volume scraping acceptable.

## Anti-goals

- Do not claim Qobuz recommends a specific bandwidth cap.
- Do not make default downloads slower without a separate product decision.
- Do not emulate HLS/DASH/player buffering for whole-file downloads.
- Do not add concurrent download workers.
- Do not bypass `qobuz_dl/http.py` for new network behavior.
- Do not add a broad dependency only to parse byte sizes or sleep between chunks.
- Do not use live Qobuz, Last.fm, or media downloads in default tests.

## Load-bearing assumptions

### Must be true

- All media-file download paths that matter pass through `http.stream_download`, or can be routed there without broad refactoring.
- Python's standard library timing and sleep functions are enough for a simple throttle.
- Users who want caution will accept an explicit opt-in setting rather than a hidden default.

### Should be true

- Existing sequential downloads already avoid the worst abuse pattern: many simultaneous file transfers.
- Provider throttling will surface as HTTP status codes or dropped/interrupted transfers that the HTTP boundary can observe.
- A byte-rate cap is more useful for large media files than for small metadata calls.

### Might be true

- Some users would prefer a named preset such as `--polite` over a numeric cap.
- A future default cap could be justified if maintainers get Qobuz guidance or see real provider throttling against normal use.
- Request pacing for paginated metadata may matter more than media throttling for artist, label, or playlist workflows.

## Risks and review points

- **False compliance risk:** a rate limit does not make reverse-engineered or high-volume behavior acceptable by itself. Docs must keep that boundary clear.
- **User-experience risk:** a cap that is too low makes downloads feel broken. First version should be opt-in and visible.
- **Test brittleness risk:** real sleeps in tests would slow CI. Use injected clocks/sleepers or a helper that can be tested without waiting.
- **Retry storm risk:** naive retry loops can worsen provider load. Retries need caps, jitter, and `Retry-After` handling.
- **Ownership drift risk:** adding throttles inside `downloader.py` would duplicate logic across covers, booklets, and audio. Keep the network behavior in `http.py`.
- **Over-scope risk:** streamer emulation, caching strategy, concurrency controls, and API credential policy are separate decisions.

## Success signals

- A cautious user can set one option and see downloads paced without changing their library organization or tags.
- Default users see no behavior change unless they opt in.
- Tests prove that `stream_download` writes the same bytes while respecting the configured pace.
- Tests prove `429` handling honors `Retry-After` and stops after a bounded retry policy.
- Documentation states the evidence gap plainly: Qobuz may limit calls/content, but no public media throughput recommendation was found.
- Future contributors know to make network-behavior changes in `qobuz_dl/http.py`.

## Recommended next phase

Use `pa-plan-slicer` before implementation. Suggested slices:

1. Parse and document the CLI/config option with offline command tests.
2. Add a deterministic `stream_download` throttle helper behind `qobuz_dl/http.py`.
3. Add `429`/`Retry-After` handling for JSON/text API calls with bounded retries.
4. Update CLI docs/examples after behavior is implemented and tested.

Implementation should run `just ci` before merge.

## Verification log

- Checked repository instructions in `AGENTS.md`.
- Checked current docs patterns in `docs/feat/2026-05-26-qobuz-api-direction/vision-qobuz-api-direction.md`.
- Checked download code in `qobuz_dl/http.py`, `qobuz_dl/downloader.py`, `qobuz_dl/commands.py`, and `qobuz_dl/cli.py`.
- Checked existing research docs in `docs/research/qobuz-official-api.md` and `docs/research/local-project-capabilities.md`.
- Searched current web sources for Qobuz API rate-limit evidence, Qobuz audio/network-player context, HTTP 429 semantics, HLS streaming structure, and comparable music-platform rate-limit guidance.
- Unverified after this pass: exact Qobuz media CDN behavior, official Qobuz streamer buffering policy, and any private partner guidance. Those are not publicly evidenced here and should remain out of the claim set.
