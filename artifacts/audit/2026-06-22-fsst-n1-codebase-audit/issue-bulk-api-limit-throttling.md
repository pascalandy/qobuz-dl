# Vision: Bulk API, Media Bandwidth, And Throttling

Mode: `pa-vision` / AlignmentDraft
Severity: Medium
Status: weak

## Request Or Decision

Decide how bulk collection downloads and media transfers should behave when Qobuz call limits are unpublished and server throttling signals may change without notice.

Verification caveat: the Qobuz numeric API limit and media byte-rate policy remain blocked because no accessible current primary source provided those numbers.

## Current State

Collection metadata calls use fixed 500-item pages for playlist, artist, and label metadata (`qobuz_dl/qopy.py:93-115`). `multi_meta()` keeps requesting pages until the reported count is exhausted (`qobuz_dl/qopy.py:175-187`). For each item, download flows may call metadata endpoints, `track/getFileUrl`, cover downloads, booklet downloads, and media streaming. CLI search result limits accept any integer for `fun --limit` and `lucky --number` (`qobuz_dl/commands.py:36-40`, `qobuz_dl/commands.py:70-75`).

No retry, backoff, throttling, maximum queue size, or rate-limit handling was found in production code. `HttpClient` has a 30-second timeout (`qobuz_dl/http.py:8`, `qobuz_dl/http.py:44-52`), but timeout is not rate governance.

`http.stream_download()` reads fixed-size chunks and writes them immediately (`qobuz_dl/http.py:105-145`), and `download_with_progress()` calls it without a pacing option (`qobuz_dl/downloader.py:349-365`). `HttpStatusError` stores status and body, not headers (`qobuz_dl/http.py:15-20`), so a `429` response's `Retry-After` header is not available to central retry logic today.

Current primary-source check: Qobuz's API Terms say Qobuz may limit the number of calls an application makes and the extent of content accessed without notice. RFC 6585 defines HTTP `429 Too Many Requests` and says responses may include a `Retry-After` header indicating how long to wait before another request. I could not verify any current official Qobuz numeric rate limit or media byte-rate policy. `developer.qobuz.com` did not resolve in this environment; the static Apps Guidelines PDF returned 403.

## Observed Constraints

- The app's high-value workflows include artist, label, and playlist bulk downloads.
- Default tests must not hit live Qobuz.
- The external numeric API call limit is blocked, not merely unknown.
- A media bandwidth cap would be a user/network courtesy control, not proof of Qobuz compliance, unless Qobuz publishes a specific policy.

## Desired End State

Bulk operations should have user-visible queue sizing, conservative default limits, and retry/backoff behavior for transient API and media failures. Optional media pacing should be available if the maintainer wants a user-facing local-network control. The docs should explicitly state that Qobuz numeric call limits and media byte-rate limits were not publicly verified and that the tool avoids aggressive behavior by design.

## Proposed Interaction Or Behavior

- Add bounded defaults or prompts for very large artist/label/playlist queues.
- Reject negative search limits and warn on unusually high limits.
- Add central retry/backoff for transient HTTP status and request errors where safe, especially `429` with `Retry-After`.
- Add opt-in media stream pacing if maintainers want bandwidth control.
- Report how many collection pages and item downloads are about to run before starting.

## Design Decisions

- Rate-safety belongs in the Qobuz API/download orchestration and HTTP boundary, not scattered in command parsing alone.
- Offline tests should model rate-limit and transient-error responses with fake sessions.
- Do not invent a Qobuz numeric rate limit.
- Do not add a hard default media bandwidth cap without stronger Qobuz-specific evidence.

## Patterns To Follow

- Say "not verified" when official numbers are unavailable.
- Calculate internal request counts from known code behavior.
- Prefer conservative, user-visible bulk controls.
- Keep pacing and `Retry-After` handling centralized in `qobuz_dl/http.py`.

## Patterns To Avoid

- Do not claim a current Qobuz calls-per-hour number without a primary source.
- Do not claim a current Qobuz media byte-rate limit without a primary source.
- Do not make catalog-scale scraping easier.
- Do not add sleep calls that make tests slow or nondeterministic.
- Do not implement per-call sleeps outside the HTTP boundary.

## Success Signals

- Negative and unreasonably large CLI limits are handled intentionally.
- Bulk download output shows planned queue size.
- Tests cover transient HTTP/rate-limit responses without live network.
- Tests cover `429`/`Retry-After` parsing and bounded retry behavior without live network.
- Optional media pacing, if added, is testable through fake streamed responses.
- Docs state the blocked external Qobuz numeric limit plainly.

## Open Questions And Risks

- Current official Qobuz numeric API limits remain blocked.
- Current official Qobuz media byte-rate and player pacing guidance remain blocked.
- Too much throttling could frustrate legitimate personal-library use.
- Too little throttling risks account/API instability.

## Calculated Evidence

- Page size in code: 500 collection items.
- 501 items require 2 collection metadata pages.
- 1001 items require 3 collection metadata pages.
- 2500 items require 5 collection metadata pages.
- These counts exclude per-item track/file URL calls and media downloads.
- Media downloads currently stream as fast as `urlopen`, the server, network, and filesystem allow; no byte-rate cap is present in `stream_download()`.

## What Needs Human Review

The maintainer should decide whether to prioritize user control, conservative defaults, maximum compatibility with current behavior, or an opt-in bandwidth cap for local-network courtesy.

## Recommended Next Phase

`pa-architect` for bulk-operation policy, then `pa-tdd` for parser validation and mocked retry/backoff behavior.
