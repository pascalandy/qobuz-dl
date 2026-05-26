FAIL

Blocker:
- `just ci` fails on Ruff import sorting in `tests/test_sanitization_characterization.py`.
  - Error: `I001 Import block is un-sorted or un-formatted`
  - This blocks AC-7.

Post-repair AC-1 / AC-3 review:
- `Download.download_track` sanitization test is offline, production-path oriented, and aligned with AC-1.
- `qopy.Client.api_call("track/getFileUrl")` signature test is offline, deterministic, and aligned with AC-3.
- Targeted tests pass: `10 passed`.

Note: I did not write the requested artifact file because the task also said “Do not modify files”; I treated no-modify as controlling.