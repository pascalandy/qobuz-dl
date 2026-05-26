# Dependency Hardening Repair Pass

## Summary

Completed the minimal in-scope repair pass for the P3/partial due-diligence gaps.

## Changed files

- `tests/test_http.py`
  - Added direct offline coverage for `qobuz_dl/http.py`:
    - `get()` query-param appending and header/timeout propagation to `urlopen(Request(...))`
    - `HTTPError` conversion to `HttpResponse`, plus `raise_for_status()` raising `HttpStatusError`
    - `URLError` conversion to `HttpRequestError`
    - `stream_download()` chunk writes, progress callback calls, and byte-count return
    - `stream_download()` `ConnectionError` on content-length mismatch
- `docs/testing.md`
  - Replaced stale `pick` guidance with built-in prompt/input fake wording.
- `docs/examples.md`
  - Updated the interactive transcript to include the initial numbered search-type prompt before `Enter your search`.
- `tests/test_bundle_downloader_characterization.py`
  - Removed the unused requests-shaped `iter_content` fake from the local `FakeHTTPResponse` helper.

## Validation

- `uv run pytest tests/test_http.py tests/test_bundle_downloader_characterization.py tests/test_terminal_interactive_characterization.py -q`
  - Exit code: 0
  - Result: `12 passed in 0.03s`
- `just ci`
  - Exit code: 0
  - Result: Ruff format check passed, Ruff lint passed, full pytest suite passed (`35 passed`), CLI smoke checks passed, and `uv build` completed successfully.

## Remaining risks

- No product, scope, or architecture changes were required.
- Existing working-tree changes outside this repair pass were treated as intentional baseline and were not reverted.
