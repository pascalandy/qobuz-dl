# Dependency Hardening Phase 2 — Repair Delegate

## Changed files

- `tests/test_sanitization_characterization.py`
  - Added a compact `Download.download_track()` production-path characterization using `tmp_path` and monkeypatched downloader/tagger functions.
  - Verifies the sanitized generated album folder is created and the sanitized final track filename is passed to the FLAC tagger.
  - No network/media download occurs.
- `tests/test_qopy_characterization.py`
  - Froze `qobuz_dl.qopy.time.time()` for the invalid-app-secret `track/getFileUrl` path.
  - Asserts exact `request_ts` and deterministic current-algorithm `request_sig` along with the existing request params.

## Validation

- `uv run pytest tests/test_sanitization_characterization.py tests/test_qopy_characterization.py`
  - Result: passed — `10 passed in 0.11s`
- `just test`
  - Result: passed — `27 passed in 0.12s`

## Remaining issue

None found in the approved repair scope.
