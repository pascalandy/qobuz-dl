# Dependency Hardening Phase 2 — Due Diligence Scope/Validation

## Verdict

Phase 2 is substantially covered. I found no blocking acceptance-criteria gaps and no default-test evidence of live Qobuz/Last.fm network, real terminal UI, credential, subscription, or media-download behavior. `just ci` passes locally.

## Validation performed

- Read: `AGENTS.md`, Phase 2 implementation plan, acceptance criteria, implementation handoff, `docs/testing.md`, all new characterization tests, and `tests/fixtures/*`.
- Ran: `just ci` → pass; `26 passed`, Ruff format/lint pass, top-level CLI help smoke pass, `uv build` pass.
- Ran: `rg "requests.get|Session\(|last.fm|qobuz.com" tests -n` and inspected hits; all Phase 2 network-looking references are faked, monkeypatched, or static example URLs.
- Checked current status: repo remains dirty/untracked from the intentional broader baseline; Phase 2 files are under `tests/`, `tests/fixtures/`, `docs/testing.md`, and artifacts.

## AC coverage check

| AC | Status | Evidence |
| --- | --- | --- |
| AC-1 Sanitization | Covered | `tests/test_sanitization_characterization.py:9-80` covers album/artist/track illegal names and empty/whitespace-heavy names; `tests/test_sanitization_characterization.py:83-122` covers playlist and artist URL directory paths through `handle_url` using temp dirs and stubbed downloads. |
| AC-2 Last.fm parsing | Covered | Static fixtures at `tests/fixtures/lastfm_playlist.html` and `tests/fixtures/lastfm_empty_playlist.html`; `tests/test_lastfm_characterization.py:22-39` monkeypatches `qobuz_dl.core.requests.get`; `tests/test_lastfm_characterization.py:45-53` verifies query formation, sanitized playlist path, and download calls; `tests/test_lastfm_characterization.py:56-77` verifies no usable list path. |
| AC-3 Qobuz API client HTTP | Covered | `tests/test_qopy_characterization.py:46-57` checks endpoint/params; `:60-69` maps login status failures; `:72-84` maps invalid app secret for `track/getFileUrl`; `:87-94` rejects invalid quality before session call; `:97-124` fakes `requests.Session` and verifies required headers after auth. |
| AC-4 Bundle/download HTTP-adjacent | Covered | `tests/test_bundle_downloader_characterization.py:56-76` patches `qobuz_dl.bundle.Session`, uses fake login HTML/bundle JS, verifies app ID and compact secret extraction; `:94-108` fakes `requests.get`/`tqdm` and verifies streamed write; `:111-127` verifies short stream raises `ConnectionError`. |
| AC-5 Interactive/terminal boundary | Covered | `tests/test_terminal_interactive_characterization.py:8-21` checks exported color constants are strings; `:24-54` injects a fake `pick` module, mocks `input`, verifies selected URL return and no download when `download=False`. Real curses/Windows behavior is appropriately out of scope. |
| AC-6 Metadata formatting | Covered | `tests/test_metadata_characterization.py:4-27` covers title versions/classical work names, genre normalization, and current copyright marker replacement without media fixtures. |
| AC-7 Proof/docs | Covered | `just ci` passed locally. `docs/testing.md:97-101` documents fixture/mock conventions. No Phase 2 runtime dependency removal/replacement is visible in `pyproject.toml`; tests characterize retained dependencies. |

## Live behavior risk check

No Phase 2 test appears to perform live network or real media behavior:

- Last.fm: `requests.get` is monkeypatched in both tests (`tests/test_lastfm_characterization.py:27`, `:64-66`).
- Qobuz API: direct client construction is avoided through `Client.__new__` or a fake `requests.Session` (`tests/test_qopy_characterization.py:36-43`, `:115-118`).
- Bundle scraping: `qobuz_dl.bundle.Session` is monkeypatched before `Bundle()` construction (`tests/test_bundle_downloader_characterization.py:56-66`).
- Streamed download: `qobuz_dl.downloader.requests.get` and `tqdm` are monkeypatched (`tests/test_bundle_downloader_characterization.py:98-105`, `:116-125`).
- Terminal UI: `pick` is provided through `sys.modules` and `input` is monkeypatched (`tests/test_terminal_interactive_characterization.py:39-42`).

## Findings / smallest safe fixes

### Advisory: `docs/testing.md` overstates what `just ci` currently smokes

- Evidence: `docs/testing.md:103-105` says CI and local `just ci` build the package; earlier smoke docs list all command help checks at `docs/testing.md:68-83`. But `justfile` defines `ci: check`, and `check` runs only `uv run qobuz-dl --help` before build, not `just smoke`'s `dl/fun/lucky` help checks.
- Impact: Not a Phase 2 AC blocker; `just ci` still passes and Phase 2 dependency-characterization tests are covered. This is a small docs/tooling consistency issue.
- Smallest safe fix: Either change `check` to call `just smoke`, or adjust `docs/testing.md` to say `just smoke` checks all command help while `just ci` currently performs the top-level CLI smoke plus build.

### Advisory: Last.fm no-result-after-search behavior remains uncharacterized

- Evidence: `tests/test_lastfm_characterization.py:56-77` covers an unusable parsed track list, but no test covers a usable Last.fm row whose stubbed `search_by_type(..., lucky=True)` returns `[]`.
- Impact: Not required by AC-2 as written, but it is a nearby failure mode in `qobuz_dl/core.py:383-388`, where the code indexes `[0]` before `get_url_info`.
- Smallest safe fix: In a later hardening pass, add a focused characterization test for `download_lastfm_pl` when one parsed track has no Qobuz search result, documenting current behavior or desired follow-up.

## Docs assessment

`docs/testing.md` changes are warranted and minimal for the new durable fixture/mock conventions (`docs/testing.md:97-101`). No broader docs update appears necessary for Phase 2 because runtime behavior and dependency choices did not change.

## Validation sufficiency

The official validation set is sufficient for this phase: targeted pytest, `just test`, `just ci`, network-reference inspection, and diff-boundary inspection. I additionally ran `just ci` directly and inspected all `rg` hits. The only caveat is the advisory mismatch above: if maintainers expect all subcommand help smoke checks in `just ci`, wire `check` to `smoke`.
