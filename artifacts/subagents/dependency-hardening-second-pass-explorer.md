I did **not** write `/Users/andy16/Documents/github_local/qobuz-dl/artifacts/subagents/dependency-hardening-second-pass-explorer.md` because the task also says **read-only only; do not edit**. Review-only wins.

# Fresh-eyes second-pass review — dependency hardening phases 3-6

## Blockers

### P0 — `--show-config` prints secrets verbatim

**Evidence**
- `qobuz_dl/cli.py:153-156`:
  - prints config path/database path
  - then opens `CONFIG_FILE` and prints the full file contents
- Config includes sensitive fields set in `_reset_config`: `password`, `app_id`, `secrets` (`qobuz_dl/cli.py:26-56`).
- `docs/cli.md` describes `--show-config` only as “Show configuration”, with no redaction warning.

**Why this matters**
This is embarrassing and security-sensitive: a support paste/screenshot can expose credential-derived material and Qobuz app secrets.

**Minimal recommended fix**
- Redact sensitive keys before printing, at least: `password`, `secrets`, `app_id`; optionally `email`.
- Add a regression test for redaction.
- Fix typo `Configuation` → `Configuration`.
- Update `docs/cli.md`.

---

## P1 findings

### P1 — Stream downloads falsely fail when `Content-Length` is missing

**Evidence**
- `qobuz_dl/http.py:115-116` treats missing `content-length` as `"0"`.
- `qobuz_dl/http.py:133-134` raises `ConnectionError` when `total != downloaded`.
- Therefore a valid chunked/unknown-length response that writes bytes but lacks `Content-Length` always fails after download.
- Tests cover matching length and short length, but not missing length: `tests/test_http.py`.

**Minimal recommended fix**
- Parse `Content-Length` as optional:
  - `total = None` if absent/invalid.
  - enforce mismatch only when `total is not None`.
- Add a test proving missing `Content-Length` writes chunks and succeeds.

---

## P2 findings

### P2 — Accidental editor artifact is untracked

**Evidence**
- `git ls-files --others --exclude-standard` includes `.vscode/settings.json`.
- File content is only:
  ```json
  {
    "folder-color.pathColors": []
  }
  ```

**Minimal recommended fix**
- Remove it from final change, or intentionally add `.vscode/` to `.gitignore`.

---

## P3 findings

### P3 — Duplicate regex assignment in bundle module

**Evidence**
- `qobuz_dl/bundle.py:20-26` defines `_BUNDLE_URL_REGEX` twice with the same pattern.

**Minimal recommended fix**
- Delete the duplicate assignment.

---

## Positive validation

- `just test` passed: **35 passed**.
- `just lint` passed.
- `just ci` passed through format, lint, tests, CLI smoke, and build.
- `uv tree --no-dev` shows only:
  - `qobuz-dl`
  - `mutagen v1.47.0`
- Removed runtime dependencies are absent from default runtime dependency tree.

## Notes

- No accidental live network in default tests found.
- No dependency leakage into default runtime found.
- There **is** a P0 blocker before client-facing release due secret disclosure in `--show-config`.