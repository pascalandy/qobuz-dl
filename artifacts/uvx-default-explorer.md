I did not write `/Users/andy16/Documents/github_local/qobuz-dl/artifacts/uvx-default-explorer.md` because the task also said “Do not modify files”; review-only/no-edit wins.

## Change surface

- Primary docs:
  - `README.md`: Quick start currently defaults to `uv tool install qobuz-dl` then `qobuz-dl`; Windows says `qobuz-dl.exe`.
  - `docs/installation.md`: install/upgrade sections are persistent-install-first.
  - `docs/cli.md`: opens with `uv tool install qobuz-dl`.
  - `docs/examples.md`: says examples assume persistent install.
- CLI/user-facing strings:
  - `qobuz_dl/commands.py`: help epilog examples all use `qobuz-dl ...`; could remain as executable syntax, or add uvx-prefixed examples if default usage must appear in `--help`.
  - `qobuz_dl/cli.py:178`: corrupted config message says `Run 'qobuz-dl -r'`.
  - `qobuz_dl/qopy.py:19`: auth reset message says `Reset your credentials with 'qobuz-dl -r'`.
- Packaging:
  - `pyproject.toml`: already supports `uvx qobuz-dl` via `[project.scripts] qobuz-dl = "qobuz_dl:main"`. No obvious packaging change.
  - `setup.py`, `requirements.txt`: no likely change.
- Dev/local workflow:
  - `AGENTS.md`, `docs/development.md`, `justfile`, `.github/workflows/ci.yml`: should likely keep `uv run qobuz-dl ...` for checkout/dev/CI smoke tests.

## Acceptance criteria suggestions

- User-facing default install/run path is:
  - `uvx qobuz-dl`
  - `uvx qobuz-dl <command> ...`
  - `uvx qobuz-dl -r`
- Persistent install remains documented as optional:
  - `uv tool install qobuz-dl`
  - `qobuz-dl`
  - `uv tool upgrade qobuz-dl`
- Windows docs no longer imply `.exe` is required for default use; default should be `uvx qobuz-dl`.
- Local development docs continue to use `uv run qobuz-dl ...`, not `uvx`.
- No `pip`/bare `python` defaults introduced.
- Config/reset docs explain uvx still uses the same persistent config under OS config dir:
  - macOS/Linux: `$HOME/.config/qobuz-dl`
  - Windows: `%APPDATA%/qobuz-dl`

## Files likely needing edits

- Definitely:
  - `README.md`
  - `docs/installation.md`
  - `docs/cli.md`
  - `docs/examples.md`
- Possibly, if `--help` should show uvx-first guidance:
  - `qobuz_dl/commands.py`
  - `qobuz_dl/cli.py`
  - `qobuz_dl/qopy.py`
  - `tests/test_commands.py`
- Probably not:
  - `pyproject.toml`
  - `setup.py`
  - `requirements.txt`
  - `justfile`
  - `docs/development.md`
  - `docs/packaging.md`
  - `docs/testing.md`

## Validation commands

```sh
rg "uv tool install|uv tool upgrade|qobuz-dl\.exe|Run 'qobuz-dl -r'|Reset your credentials" README.md docs qobuz_dl tests
uv run qobuz-dl --help
uv run qobuz-dl dl --help
uv run qobuz-dl fun --help
uv run qobuz-dl lucky --help
just ci
```

Optional package-run smoke, if network/cache allows:

```sh
uvx --from . qobuz-dl --help
uvx --from . qobuz-dl dl --help
```

## Risks / ambiguities

- `uvx qobuz-dl` installs/runs an ephemeral tool env but persists app config in `~/.config/qobuz-dl`; docs should avoid implying config is ephemeral.
- Help output cannot naturally show `uvx qobuz-dl` in argparse usage because the actual console script name is `qobuz-dl`; adding uvx examples is possible but may make help noisier.
- Existing examples are shorter as `qobuz-dl ...`; decide whether all examples become `uvx qobuz-dl ...` or docs state “examples omit persistent-install vs uvx prefix.”
- `qdl` script exists in `pyproject.toml`; docs currently do not emphasize it. Avoid accidentally making `uvx qdl` seem supported unless intended.