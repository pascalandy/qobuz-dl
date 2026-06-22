# Vision: Local Secret File Permissions

Mode: `pa-vision` / AlignmentDraft
Severity: High
Status: proved

## Request Or Decision

Decide how `qobuz-dl` should enforce local file permissions for config and duplicate-tracking state that contain credential-equivalent material.

## Current State

The config file stores `email`, `password`, `app_id`, and `secrets` (`qobuz_dl/cli.py:73-93`). `_reset_config()` creates the config directory with `os.makedirs(..., exist_ok=True)` and writes `config.ini` using plain `open(config_file, "w")` (`qobuz_dl/cli.py:111-148`). There is no explicit `chmod`, secure open mode, umask handling, or post-write permission check.

Docs correctly warn that the config file is secret and recommend `chmod 700 ~/.config/qobuz-dl` plus `chmod 600 ~/.config/qobuz-dl/config.ini` when moving config files (`docs/use-cases.md:71`, `docs/use-cases.md:87-95`). The implementation does not enforce the same safety on first-run creation.

The downloaded-ID database is created through `sqlite3.connect(db_path)` (`qobuz_dl/db.py:10-25`) without explicit permissions. The database stores item IDs rather than auth credentials, so it is lower sensitivity than `config.ini`, but docs still recommend mode `600` for moved DB files.

## Observed Constraints

- Windows ACL handling differs from POSIX file modes.
- The code currently supports Linux, macOS, and Windows paths.
- Existing users may already have permissive config files.

## Desired End State

Fresh config directories and files should be private by default on POSIX platforms, and existing permissive files should produce a clear warning or one-shot repair path. Windows should get an explicit ACL-aware strategy or a documented limitation.

## Proposed Interaction Or Behavior

- On POSIX: create config dir as `0700` and config file as `0600`.
- On startup: detect too-permissive config file modes and warn or repair.
- On Windows: document and, if feasible, enforce current-user-only ACLs.

## Design Decisions

- Treat config secrets as credential-equivalent because the stored password hash is used for login.
- Keep permission logic in `cli.py` or a small config helper, not in download code.
- Keep `--show-config` redaction, but do not mistake redaction for storage protection.

## Patterns To Follow

- Apply least privilege at file creation time.
- Add tests that monkeypatch file mode behavior without reading real user secrets.
- Keep migration behavior non-destructive.

## Patterns To Avoid

- Do not rely on documentation-only chmod instructions for first-run security.
- Do not inspect or print real user config contents while repairing permissions.
- Do not make Windows claims without Windows-specific verification.

## Success Signals

- New POSIX config files are created as private to the user.
- Tests prove config creation does not depend on ambient umask for secrecy.
- Existing permissive config files are detected and handled without exposing contents.

## Open Questions And Risks

- Windows ACL enforcement needs a separate verification environment.
- Tightening permissions could surprise users who intentionally sync config across accounts, though that pattern is already risky.

## What Needs Human Review

The maintainer should decide whether startup should auto-repair permissive permissions or only warn with a command users can run.

## Recommended Next Phase

`pa-plan-slicer` for a small security hardening slice with tests around POSIX permissions and a documented Windows follow-up.
