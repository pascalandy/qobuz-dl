# Dependency Hardening Phase 2 — Acceptance Criteria

Baseline working tree changes are intentional. Phase 2 must add characterization coverage without removing, replacing, optionalizing, or vendoring runtime dependencies.

## Official AC

- **AC-1 Sanitization:** Tests characterize current `pathvalidate`-backed generated filename/path behavior for album, artist, playlist, and track names, including illegal characters and empty/whitespace-heavy names, using pure helpers/temp dirs and no downloads.
- **AC-2 Last.fm parsing:** Tests use small static HTML fixtures and mocked `requests.get` to characterize playlist title sanitization, artist/title query formation, download calls, and the no-usable-track-list path with no live Last.fm/Qobuz calls.
- **AC-3 Qobuz API client HTTP:** Tests use fake sessions/responses to characterize `qopy.Client.api_call` success params/headers enough, login status mapping, invalid app secret handling, invalid quality handling, and avoid real authenticated clients/network.
- **AC-4 Bundle/download HTTP-adjacent:** Tests fake Qobuz bundle HTML/JS and streamed downloads; cover app ID extraction, compact secret extraction if readable, successful streamed writes, interrupted download `ConnectionError`, and avoid progress rendering assertions/live media.
- **AC-5 Interactive/terminal boundary:** Tests characterize exported color constants as strings and a shallow mocked `pick`/`input` interactive selected-item flow returning URLs when `download=False`; defer brittle terminal/curses behavior explicitly if needed.
- **AC-6 Metadata formatting:** Tests cover pure metadata helper behavior for versions/classical work titles, genre normalization, and copyright symbol replacement without binary media fixtures.
- **AC-7 Proof/docs:** `just test` and `just ci` pass; tests are deterministic/offline; durable fixture/mock conventions are documented in `docs/testing.md` only if useful; no runtime dependencies are changed.

## Validation commands

- Targeted pytest for new characterization tests.
- `just test`
- `just ci`
- `rg "requests.get|Session\(|last.fm|qobuz.com" tests -n` with inspection that hits are mocked/faked.
- `git diff --stat` to confirm Phase 2 boundaries.
