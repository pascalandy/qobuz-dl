I did **not** write `/artifacts/subagents/dependency-hardening-second-pass-docs.md` because the task also said **read-only only; do not edit**. Review-only won.

## P0 findings

### P0 — `--show-config` exposes secrets verbatim
**Evidence**
- `qobuz_dl/cli.py:153-156` prints the entire config file:
  - `print(f"Configuation: {CONFIG_FILE}\nDatabase: {QOBUZ_DB}\n---")`
  - `print(f.read())`
- Running `uv run qobuz-dl --show-config` printed live credential/config material, including password/token-like fields. I am intentionally not reproducing values here.
- `docs/cli.md:18` documents the flag only as “Show configuration”, with no warning/redaction behavior.

**Minimal recommended fix**
- Redact sensitive config keys before printing: at least `password`, `secrets`, `private_key`, `user_auth_token`, and probably email/user identifiers if not needed.
- Fix typo: `Configuation` → `Configuration`.
- Add a small test proving sensitive keys are redacted.
- Update `docs/cli.md` to say it shows config paths and redacted config values.

**pa-doc-update-style docs update needed?** Yes.

## P1 findings

### P1 — New stdlib download boundary falsely fails downloads with missing `Content-Length`
**Evidence**
- `qobuz_dl/http.py:115-116` defaults missing `content-length` to `0`.
- `qobuz_dl/http.py:133-134` raises whenever `total != downloaded`.
- Therefore any successful streamed response without `Content-Length` but with bytes downloaded raises `ConnectionError`.
- Existing tests cover a matching length and short length, but not missing length: `tests/test_http.py:107-158`.

**Minimal recommended fix**
- Treat absent/invalid `Content-Length` as unknown, not zero.
- Only enforce mismatch when `total is not None`.
- Add a test for missing `content-length` that writes chunks and succeeds.

## P2 findings

### P2 — Accidental editor artifact is untracked and should not ship
**Evidence**
- `git ls-files --others --exclude-standard` includes `.vscode/settings.json`.
- File content is only:
  ```json
  {
    "folder-color.pathColors": []
  }
  ```

**Minimal recommended fix**
- Remove `.vscode/settings.json` from the final change, or intentionally ignore `.vscode/` if local-only editor settings are not part of the repo policy.

### P2 — Packaging docs local-artifacts list is incomplete versus `.gitignore`
**Evidence**
- `.gitignore:14-17` also ignores `.cache/`, `.pytest_cache/`, `.coverage`, `htmlcov/`.
- `docs/packaging.md:43-50` lists local artifacts but stops at `.venv/`.

**Minimal recommended fix**
- Add `.cache/`, `.pytest_cache/`, `.coverage`, and `htmlcov/` to `docs/packaging.md`.

**pa-doc-update-style docs update needed?** Yes, minor docs consistency update.

## P3 findings

### P3 — Duplicate regex assignment is embarrassing polish debt
**Evidence**
- `qobuz_dl/bundle.py:20-26` defines `_BUNDLE_URL_REGEX` twice with the same pattern.

**Minimal recommended fix**
- Remove the duplicate definition.

## Checks run

- `git status --short`
- `git ls-files --others --exclude-standard`
- `git diff --check -- .` — no whitespace output observed
- `uv run qobuz-dl --help`
- `uv run qobuz-dl --show-config` — revealed P0 secret-printing issue

## Overall docs status

A **pa-doc-update-style docs update appears needed** because `--show-config` behavior/docs must change after redaction, and packaging local-artifact docs should be aligned with `.gitignore`.