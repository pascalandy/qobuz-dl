# uvx default implementation handoff

## Changed files

- `README.md`
- `docs/installation.md`
- `docs/examples.md`
- `docs/cli.md`
- `qobuz_dl/commands.py`
- `qobuz_dl/cli.py`
- `qobuz_dl/qopy.py`
- `tests/test_commands.py`
- `artifacts/uvx-default-implementation.md`

Note: `artifacts/uvx-default-explorer.md` is untracked but was not edited by this implementation pass.

## AC coverage

- AC-1: `README.md` Quick start now leads with `uvx qobuz-dl`, explicitly says no app install is required, and keeps `uv tool install qobuz-dl` as optional persistent install.
- AC-2: `docs/installation.md` now recommends `uvx qobuz-dl`, explains config/auth/database persistence in the user config dir across uvx and installed runs, and keeps optional install/upgrade/uninstall/reset guidance.
- AC-3: `docs/examples.md` and `docs/cli.md` examples now default to `uvx qobuz-dl ...`; both include a note that installed users may replace it with `qobuz-dl`, and local development remains `uv run qobuz-dl ...`.
- AC-4: CLI help examples in `qobuz_dl/commands.py` now use `uvx qobuz-dl ...` and include installed-user replacement guidance. Reset/auth/corrupt-config guidance now says `uvx qobuz-dl -r` first, with installed form optional.
- AC-5: `tests/test_commands.py` was updated for intentional CLI help text changes. No network/live Qobuz/API/download tests were added.
- AC-6: Historical `docs/feat/*` and local development/testing docs were left unchanged.

## Validation commands

- `uv run pytest tests/test_commands.py` — exit 0; 9 tests passed.
- `uv run qobuz-dl --help` — exit 0; top-level help showed uvx examples and installed-user replacement note.
- `uv run qobuz-dl dl --help` — exit 0; download help showed uvx examples and installed-user replacement note.
- `just ci` — exit 0; ruff format check, ruff check, 47 tests, CLI help smoke checks, and build passed.

## Risks / remaining issues

- Runtime argparse `usage:` still starts with `qobuz-dl` because that is the console script program name; examples and docs show the recommended `uvx qobuz-dl` wrapper.
- No live Qobuz auth/download validation was run, by design for the default test policy.
