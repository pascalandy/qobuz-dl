# UVX-default due diligence

## Verdict

Overall: **PASS**. No blocking issues found against the official AC.

## AC results

- **AC-1 — PASS**: README Quick start leads with `uvx qobuz-dl` and explicitly says no app install is required (`README.md:21-27`). Persistent install remains optional (`README.md:29-36`).
- **AC-2 — PASS**: Installation docs make `uvx qobuz-dl` the recommended no-install path (`docs/installation.md:11-19`), explain persisted config/auth/database reuse in the user config directory (`docs/installation.md:19`), and keep install/upgrade/uninstall/reset guidance (`docs/installation.md:27-75`).
- **AC-3 — PASS**: `docs/examples.md` and `docs/cli.md` default examples to `uvx qobuz-dl ...` and note installed users can replace it with `qobuz-dl` while local development stays `uv run qobuz-dl ...` (`docs/examples.md:3`, `docs/cli.md:3`).
- **AC-4 — PASS**: CLI help examples now prefer `uvx qobuz-dl` and include installed-user replacement guidance (`qobuz_dl/commands.py:202-210`, plus subcommand epilogs). Reset/auth guidance includes `uvx qobuz-dl -r` first with installed form optional (`qobuz_dl/cli.py:176-179`, `qobuz_dl/qopy.py:19`).
- **AC-5 — PASS**: Tests were updated for intentional help text changes (`tests/test_commands.py:70-95`). No new network/live Qobuz/API/download tests were introduced.
- **AC-6 — PASS**: Historical `docs/feat` material and local development/testing docs were not rewritten; local dev examples remain `uv run qobuz-dl ...`.

## Blockers / required fixes

None.

## Optional nits

- Runtime argparse usage still starts with `usage: qobuz-dl ...` because `prog="qobuz-dl"` is retained (`qobuz_dl/commands.py:196-197`). The examples and guidance are UVX-first, so this does not fail the AC, but if the desired first line of `--help` must also be UVX-first, adjust intentionally and update tests.
- Test coverage checks top-level and `dl` help for UVX text, but not `fun`/`lucky` help. I manually verified those help epilogs; adding assertions would make the AC-4 proof stronger.

## Validation performed

- `uv run pytest tests/test_commands.py` — **pass**, 9 tests.
- `uv run qobuz-dl --help` — **pass**, UVX-first examples and installed-user note present.
- `uv run qobuz-dl dl --help` — **pass**, UVX examples and installed-user note present.
- `uv run qobuz-dl fun --help` — **pass**, UVX examples and installed-user note present.
- `uv run qobuz-dl lucky --help` — **pass**, UVX examples and installed-user note present.

## Recommended final validation

- `just ci`
