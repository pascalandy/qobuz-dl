# Bandwidth Limit Vision

## Relationship to agent operation

This June 2026 vision supplies the network-policy boundary for the [agent operation design](../2026-09-12-agent-ergonomics/design-agent-ergonomics.md). Media byte pacing and API/media retries remain separate controls. Keep transfers sequential, default pacing disabled, and network policy inside `qobuz_dl/http.py`.

At the baseline recorded in the [implementation plan](../2026-09-12-agent-ergonomics/impl-plan-agent-ergonomics.md), retries are proposed in [PR #73](https://github.com/pascalandy/qobuz-dl/pull/73) and [PR #74](https://github.com/pascalandy/qobuz-dl/pull/74). Issues [#50](https://github.com/pascalandy/qobuz-dl/issues/50) and [#51](https://github.com/pascalandy/qobuz-dl/issues/51) own the pacing decision and implementation. Refresh those owners before choosing option names or units. Pacing does not depend on retry delivery.

An agent result must distinguish bytes transferred, time spent honoring provider delays, and an applied local byte cap. A whole-run deadline includes retry waits. If a provider delay exceeds the remaining budget, stop with an explicit outcome instead of retrying early. The historical evidence and recommendations below do not establish an official Qobuz throughput limit.

## Request Or Decision

Issue #50 records a fresh maintainer decision about whether `qobuz-dl` should add bandwidth limiting. The historical vision remains useful context, but recovery of its original source is no longer a prerequisite for implementation.

Commit `00641bf4ae4a1a01716215f02bda7e38473dfaea` remains unavailable and was not recovered. The approved policy below supersedes that recovery dependency.

## Maintainer Decision

Approve an explicit, optional cap for audio media downloads. Keep downloads unlimited by default. Reject automatic rate selection.

The accepted rate grammar is `[1-9][0-9]*(KiB/s|MiB/s)`. The value is a positive integer followed immediately by the exact unit `KiB/s` or `MiB/s`. Spaces, decimals, signs, SI units, and case variants are invalid. The exact token `off` is also valid.

Both configuration and the CLI accept a rate or `off`. A CLI value overrides the configured value. CLI `off` therefore disables a configured cap for one invocation. If neither source sets a positive rate, downloads remain unlimited.

The cap applies only to audio media payload bytes. Covers, booklets, Qobuz API traffic, bundle traffic, and Last.fm traffic remain unlimited. This is a local user preference. It is not a Qobuz quota, a claim of Qobuz approval, or a substitute for server-directed rate-limit handling.

Pacing occurs at the application layer while `stream_download` reads and writes an audio response body. The implementation handles one bounded application read at a time and may reduce the read size below the existing 64 KiB maximum to keep waits responsive. The rate calculation counts the time spent reading and writing each chunk, and it banks no idle credit before that chunk. The application does not add read-ahead or retain more than the current chunk. TLS, socket, kernel, proxy, and server buffers remain outside this control, so the setting limits application consumption over time rather than guaranteeing an exact wire rate.

This policy favors a small, predictable control. A positive rate is explicit, `off` is an explicit escape hatch, and command-line precedence supports temporary overrides without changing persistent configuration. Automatic selection has no trustworthy input and would make throughput depend on an undocumented guess.

## Mode

DirectionCheck, using HMW and Pre-Mortem lenses.

HMW: How might we let power users download purchased or streamable Qobuz content without saturating their network or ignoring server throttling signals, while keeping default CLI behavior simple and evidence-based?

Pre-Mortem summary: this feature fails if it promises compliance it cannot prove, hard-codes a cap that frustrates normal users, implements throttling outside the HTTP boundary, or retries rate-limited requests in a way that increases load.

## Success Criteria And Evaluation Method

Evaluation method: pass/fail against the original FSST criteria.

| Criterion | Status | Evidence |
|---|---:|---|
| Success criteria and evaluation method are explicit | Pass | This section freezes the criteria before implementation planning. |
| Repo download path and HTTP boundary are checked | Pass | `qobuz_dl/http.py`, `qobuz_dl/downloader.py`, `qobuz_dl/qopy.py`, and related tests are referenced in Current State. |
| External evidence is credible and scoped | Pass | Evidence uses Qobuz primary sources, HTTP standards/docs, HLS structure, Spotify/TIDAL music API rate-limit guidance, and YouTube quota governance. |
| Qobuz-specific uncertainty is explicit | Pass | The evidence gap names the missing Qobuz media byte-rate, streamer prefetch, and partner-guidance data. |
| Direction is pressure-tested | Pass | The artifact includes lenses, anti-goals, assumptions, risks, trade-offs, and the approved explicit-pacing decision. |
| Future feature is concrete but not overclaimed | Pass | The maintainer decision fixes the grammar, precedence, payload scope, application-layer boundary, and buffering limit. |
| Recovery dependency is superseded | Pass | The missing commit was not recovered. A fresh maintainer decision now supplies the policy for implementation. |

## Problem Or Opportunity

`qobuz-dl` currently downloads media as fast as the server, network, and filesystem allow. That is efficient, but it gives users no built-in way to reduce local bandwidth pressure, and the HTTP layer has no central policy for rate-limit responses.

The opportunity is not to make `qobuz-dl` identical to the official Qobuz apps. The opportunity is to give users and maintainers a conservative control surface for polite behavior:

- user-controlled media byte pacing when the user needs it;
- central handling of explicit server throttling signals;
- no expansion of parallel download behavior;
- no undocumented claims about Qobuz's internal streaming/player byte-rate model.

## Who It Serves

Primary beneficiary: `qobuz-dl` users who download large albums, playlists, labels, or artist catalogs on shared, metered, slow, or latency-sensitive networks.

Secondary beneficiary: maintainers and future contributors who need network behavior to stay testable and centralized instead of adding per-call ad hoc sleeps around download code.

Indirect beneficiary: Qobuz and upstream media infrastructure, because the client can avoid avoidable request spikes and can respect explicit rate-limit responses.

## Current State

The following snapshot is historical context from before issues #39 and #40. See [API rate-limit retries](../../cli.md#api-rate-limit-retries) and [audio rate-limit retries](../../cli.md#audio-rate-limit-retries) for current `429` behavior. The original snapshot remains here as evidence for the vision.

The production HTTP boundary is `qobuz_dl/http.py`. API calls use `HttpClient.get`, which wraps `get`; streamed file downloads use `stream_download`, which opens the URL with `urlopen`, reads fixed-size chunks, writes them immediately to disk, reports progress, checks `content-length`, and returns the byte count. At the time of this snapshot, it did not pace reads, sleep between chunks, parse `Retry-After`, retry `429`, or expose response headers on `HttpStatusError`.

`qobuz_dl/downloader.py` is the main media caller. Track, cover, and booklet downloads pass through `download_with_progress`, which calls `http.stream_download` and deletes the partial target on failure. Album downloads are sequential: metadata is fetched, cover and optional booklet are downloaded, then each track URL is fetched and each track is streamed and tagged. There is no visible parallel download expansion in this path.

`qobuz_dl/qopy.py` uses the same HTTP boundary for Qobuz API calls. It requests `track/getFileUrl` with `intent=stream`, then `downloader.py` streams the returned media URL. That makes `qobuz_dl/http.py` the right place for shared network behavior, while `downloader.py` remains the right place to pass user-facing download options into streamed media requests.

Existing tests already characterize `http.stream_download` success, status errors, malformed URLs, missing content length, and interrupted downloads. They also characterize `download_with_progress` file writing, progress throttling, and cleanup. Any future implementation should extend these offline tests rather than adding live Qobuz checks to default CI.

## External Evidence

Qobuz's API Terms of Use are the strongest accessible primary source for API governance. They require Qobuz-issued application credentials, forbid sharing those credentials, allow Qobuz to modify, suspend, or limit API access without notice, and say Qobuz may limit both call count and content extent. They also restrict damaging use, full or partial service indexing, and geoblocking bypass. Source: [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf).

Qobuz's public subscription/help pages confirm the service offers high-data audio qualities: MP3 320 kbps, lossless FLAC 16-bit/44.1 kHz, and Hi-Res 24-bit up to 192 kHz, with the maximum quality depending on subscription and label availability. This supports the local-network value of a user cap, because high-resolution FLAC can be materially larger than lossy streams. It does not establish a Qobuz-published media byte-rate throttling rule. Sources: [Qobuz streaming offers](https://www.qobuz.com/us-en/music/streaming/offers), [Qobuz streaming catalogue help](https://help.qobuz.com/en/articles/10139-what-is-in-the-streaming-catalogue).

HTTP `429 Too Many Requests` is the standard explicit signal that a client has sent too many requests in a period. RFC 6585 says a `429` response may include `Retry-After` to tell the client how long to wait before a new request, and it does not define how servers count or identify users. MDN gives the same practical interpretation and notes that `Retry-After` can guide the wait. Sources: [RFC 6585 section 4](https://datatracker.ietf.org/doc/html/rfc6585#section-4), [MDN 429 Too Many Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429).

HLS streaming transfers media through playlists and media segments, with variant bandwidths declared in playlists. That is structurally different from `qobuz-dl` receiving whole-file media URLs from `track/getFileUrl`, so HLS supports caution about streamer analogies more than it supports a specific cap. Source: [RFC 8216](https://datatracker.ietf.org/doc/html/rfc8216).

Comparable music API guidance points toward central backoff rather than guessed hard quotas. Spotify documents a rolling request window, `429` responses, normally present `Retry-After` seconds, backoff, batching, request-pattern review, and lazy loading. This is not Qobuz policy, but it is relevant music-platform precedent for treating rate limits as provider-controlled signals. Source: [Spotify Web API rate limits](https://developer.spotify.com/documentation/web-api/concepts/rate-limits).

TIDAL API maintainers publicly stated that `429` responses include `Retry-After` to show when it is safe to retry. This is another music-service signal that clients should respect provider throttling instead of guessing a fixed safe rate. Source: [TIDAL API discussion](https://github.com/orgs/tidal-music/discussions/135).

YouTube Data API uses quotas to preserve service quality and prevent abusive or unfair access; larger quota requests require compliance review. This reinforces the general principle that media platforms expect clients to fit provider capacity and policy. Source: [YouTube Data API quota and compliance audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).

Qobuz-specific evidence gap: no accessible official source found in this pass states a recommended third-party media download byte rate, chunk cadence, player prefetch policy, or default cap for `track/getFileUrl` media URLs. The artifact therefore treats a bandwidth cap as a user/network courtesy feature, not as proof of Qobuz compliance or official streamer equivalence.

## Desired End State

`qobuz-dl` should support polite download behavior through a small, testable network policy inside the existing HTTP boundary.

Target state:

1. Users can optionally cap audio media download throughput for local-network courtesy.
2. The default behavior remains unlimited.
3. `qobuz_dl/http.py` centrally handles explicit rate-limit responses, especially `429` and `Retry-After`, for API and media requests where retry is safe.
4. Retry behavior is bounded, observable, and avoids retry storms.
5. Album and playlist downloads remain sequential by default; this work does not introduce parallel media fetching.
6. Tests stay offline and mock network behavior.
7. Docs explain the feature as a responsible-use control, not a guarantee of Qobuz approval or official-client parity.
8. Covers, booklets, API calls, bundle traffic, and Last.fm traffic remain unlimited.
9. Automatic rate selection is not supported.

## Approved Feature Shape

Issue #51 should implement this narrow shape:

- Parse `[1-9][0-9]*(KiB/s|MiB/s)` and `off` at the CLI and configuration boundaries.
- Reject spaces, decimals, signs, SI units, case variants, zero, and missing units.
- Resolve the CLI value before the configuration value. Treat CLI `off` as an explicit override of a configured cap.
- Apply pacing only when `stream_download` receives an audio media payload and a positive resolved rate.
- Pace one bounded application read at a time. Count the read and write time for each chunk, and bank no idle credit.
- Allow the read size to fall below the existing 64 KiB maximum to keep waits responsive. Do not add application read-ahead or retain more than the current chunk. Document that lower network layers may buffer outside application control.
- Preserve current progress callbacks and interrupted-download checks.
- Thread the resolved option through `downloader.py` into `http.stream_download` instead of sleeping in album loops.
- Keep covers, booklets, API calls, bundle traffic, and Last.fm traffic outside the pacing path.
- Keep `429` and `Retry-After` behavior separate from this local throughput preference.

## Anti-Goals

- Do not add a hard default media bandwidth cap based only on intuition.
- Do not add an `auto` mode or infer a rate from connection speed, media quality, server behavior, or Qobuz behavior.
- Do not pace covers, booklets, API calls, bundle traffic, or Last.fm traffic.
- Do not claim the feature makes `qobuz-dl` behave like official Qobuz apps or licensed player devices.
- Do not infer undocumented Qobuz media byte-rate policy from audio quality labels alone.
- Do not add parallel downloads, queue workers, async rewrites, or a new HTTP dependency as part of this feature.
- Do not bypass `qobuz_dl/http.py` for new network behavior.
- Do not add default tests that require Qobuz credentials, live API calls, live media URLs, or real downloads.
- Do not treat retries as infinite resilience. Retrying too aggressively can increase provider load.

## Load-Bearing Assumptions

Must be true:

- `qobuz_dl/http.py` remains the central production HTTP boundary for API calls and streamed downloads.
- Most current media downloads can tolerate optional pacing without changing file bytes, metadata tagging, or cleanup behavior.
- The project should not document undocumented Qobuz behavior as fact.

Should be true:

- Users who need this feature are willing to opt in with a clear CLI or configuration setting.
- `429` and `Retry-After` handling can be tested with faked HTTP responses using existing test patterns.
- A small HTTP-layer policy is simpler and safer than per-call sleeps in `downloader.py`.

Might be true:

- Backoff handling may reduce intermittent failures for large playlist or catalog operations, but this should be measured rather than assumed.

## Success Signals

- A user can run a large download with an explicit bandwidth cap and see stable progress without saturating their local connection.
- Invalid rates fail at the CLI or configuration boundary, and CLI `off` disables a configured cap.
- The same invocation leaves covers, booklets, API calls, bundle traffic, and Last.fm traffic unlimited.
- A fake `429` with `Retry-After` is handled by one central path and covered by offline tests.
- Existing tests for streamed downloads, progress logging, cleanup, and content-length mismatch still pass.
- Maintainers can point to `qobuz_dl/http.py` as the single owner of network pacing and backoff behavior.
- Documentation states the Qobuz evidence gap plainly and avoids official-client parity claims.
- No new parallelism or live-network default tests are introduced.

## Trade-Offs And Risks

- User value is real but local. A cap mainly helps the user's network and reduces burstiness; it does not prove provider-side compliance.
- Default caps can frustrate users. Without Qobuz-specific guidance, an opt-in cap is safer than changing default throughput.
- Backoff can hide failures if logs are vague. Users need to know when the CLI is waiting because the server asked it to slow down.
- `Retry-After` can be long or absent. The policy needs maximum attempts, maximum sleep, and clear failure behavior.
- Media downloads may return rate-limit or transient errors differently from JSON API endpoints. The implementation should avoid assuming all servers emit `429`.
- Application-level pacing cannot control TLS, socket, kernel, proxy, or server buffering. Short wire-rate bursts can exceed the configured average.
- A bounded application read can create a short wire-rate burst. Lower network layers can also buffer beyond the current application chunk.
- Exposing too many knobs can make the CLI harder to understand. The approved grammar and `off` token are the complete option set.

## Recommendation

Approve explicit audio media pacing. Reject automatic rate selection.

One-line reason: an explicit local preference gives users control without inventing a Qobuz policy or changing default throughput.

## Current routing

The background research and pressure test are historical direction from 22 June 2026. The maintainer decision above is the current policy. [Issue #20](https://github.com/pascalandy/qobuz-dl/issues/20) owns current sequencing.

[Issue #39](https://github.com/pascalandy/qobuz-dl/issues/39) and [issue #40](https://github.com/pascalandy/qobuz-dl/issues/40) own bounded `429` retries for API reads and media acquisition. [Issue #50](https://github.com/pascalandy/qobuz-dl/issues/50) records the fresh maintainer policy and supersedes recovery of the missing commit as a prerequisite. [Issue #51](https://github.com/pascalandy/qobuz-dl/issues/51) owns implementation of the explicit optional byte-rate limit. [Issue #52](https://github.com/pascalandy/qobuz-dl/issues/52) should be rejected because automatic rate selection is outside the approved policy.

This routing is documentation only. It does not claim that the remote issues have changed state.

## Original Verification Log

- Ran `git status --short` first; the worktree was clean.
- Worked in the isolated branch worktree `codex/fsst-n1-bandwidth-limit-vision`.
- Read `AGENTS.md`, `docs/INDEX.md`, existing `docs/feat` vision patterns, and relevant research docs.
- Checked the current download path in `qobuz_dl/http.py`, `qobuz_dl/downloader.py`, `qobuz_dl/qopy.py`, and existing HTTP/download tests.
- Checked external sources for Qobuz API terms, Qobuz audio qualities, HTTP `429`/`Retry-After`, and comparable music API rate-limit guidance.
- Ran `just ci`: format check, lint, 157 tests, CLI smoke checks, and build passed.

Unverified after this pass: exact Qobuz media CDN behavior, official Qobuz streamer buffering policy, and any private partner guidance. Those claims should stay out of implementation docs unless stronger primary evidence appears.
