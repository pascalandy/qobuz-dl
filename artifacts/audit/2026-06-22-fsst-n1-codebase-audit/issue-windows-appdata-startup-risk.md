# Vision: Windows APPDATA Startup Risk

Mode: `pa-vision` / AlignmentDraft
Severity: Medium
Status: proved

## Request Or Decision

Decide how the CLI should locate its config directory on Windows when `%APPDATA%` is absent or unusable.

Verification caveat: Windows runtime reproduction remains blocked because this audit environment is not Windows.

## Current State

`pyproject.toml` declares `Operating System :: OS Independent` (`pyproject.toml:18-29`). On Windows, module import sets `OS_CONFIG = os.environ.get("APPDATA")` (`qobuz_dl/cli.py:22-23`). Immediately afterward, import-time constants call `os.path.join(OS_CONFIG, "qobuz-dl")`, `os.path.join(CONFIG_PATH, "config.ini")`, and `os.path.join(CONFIG_PATH, "qobuz_dl.db")` (`qobuz_dl/cli.py:27-29`).

If `%APPDATA%` is missing, `OS_CONFIG` is `None`; `os.path.join(None, "qobuz-dl")` raises before argument parsing can show help, reset config, or produce a user-friendly diagnostic. The audit environment is not Windows, so I did not reproduce the startup failure on Windows. The issue is logged from the direct import-time code path.

## Observed Constraints

- Config path constants are module-level and are imported by CLI flows and tests.
- The project already has tests around startup/config behavior, so this can be characterized without live Qobuz calls.
- Windows path and environment behavior should be verified on an actual Windows runner or a targeted mocked import test.

## Desired End State

Windows startup should either choose a safe fallback config directory when `%APPDATA%` is unavailable or fail with a clear, recoverable message after argument parsing. Help, version, reset, and show-config flows should not crash at import time.

## Proposed Interaction Or Behavior

- Move OS config discovery behind a small function that validates the environment.
- Prefer an explicit fallback such as a user home config path only if it is intentional and documented.
- Add tests that simulate `os.name == "nt"` with missing `%APPDATA%` and verify the chosen behavior.

## Design Decisions

- Keep config path behavior centralized in `qobuz_dl/cli.py`.
- Do not read or print real user config values while testing this path.
- Preserve the existing config file names unless there is a deliberate migration plan.

## Patterns To Follow

- Defer environment-dependent path resolution until it can be tested and diagnosed.
- Keep Windows support claims tied to covered startup paths.
- Use mocked environment tests for default CI and a real Windows check when available.

## Patterns To Avoid

- Do not let import-time constants raise before CLI help can run.
- Do not silently write secrets into an unexpected fallback directory.
- Do not claim Windows runtime proof from this non-Windows audit environment.

## Success Signals

- Missing `%APPDATA%` has an explicit test and behavior decision.
- `uv run qobuz-dl --help` and reset/show-config flows can be reasoned about on Windows without import-time crashes.
- Docs or code comments explain the Windows config directory choice.

## Open Questions And Risks

- A fallback path could surprise existing Windows users if it differs from `%APPDATA%`.
- Real Windows CI may reveal additional path or permission edge cases beyond this import-time issue.

## What Needs Human Review

The maintainer should decide whether missing `%APPDATA%` should use a documented fallback or produce a clear configuration error.

## Recommended Next Phase

`pa-tdd` for a focused Windows config path characterization and repair slice.
