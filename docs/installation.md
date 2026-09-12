# Installation

## Requirements

- `uv`
- Git
- Python 3.10 or newer, managed through `uv`
- An active Qobuz subscription

Use `uv` for user-facing, install, and local project commands. Do not use `pip` or direct `python` commands as the default workflow.

## Run the fork without installing the app

Use the full Git source so `uvx` selects this fork instead of a package with the same name from a public package index:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl
```

Git must be available on `PATH` because `uv` fetches the source repository. The repository URL follows the current default branch. A later run can therefore resolve to a newer commit.

The first run creates persistent qobuz-dl state under your user config directory. On Linux and macOS, the config is `~/.config/qobuz-dl/config.ini`. On Windows, it is `%APPDATA%\qobuz-dl\config.ini`. The downloaded-IDs database is `qobuz_dl.db` beside the config.

The config and database remain after the temporary `uvx` environment exits. Later one-shot runs and persistent installs reuse them. See [Account and authentication](use-cases.md#where-authconfig-and-the-database-live) for the stored fields, security notes, and portability steps.

If configuration fails or you need to start over, reset the config file:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -r
```

## Install the fork persistently

Install persistently only if you want a permanent `qobuz-dl` command on your `PATH`:

```sh
uv tool install git+https://github.com/pascalandy/qobuz-dl.git
qobuz-dl
```

On Windows, run `qobuz-dl.exe` after the same install command.

Reinstall from the current default branch to replace an existing tool environment:

```sh
uv tool install --reinstall git+https://github.com/pascalandy/qobuz-dl.git
```

To uninstall a persistent tool install:

```sh
uv tool uninstall qobuz-dl
```

Uninstalling or reinstalling the tool does not remove the application config or downloaded-IDs database. Installed users can reset the config with:

```sh
qobuz-dl -r
```

## Choose a moving source or an exact revision

The recommended commands use the repository URL without a revision. This moving source follows the current default branch and is suitable when you want the latest fork code.

For a reproducible install, append a full 40-character commit SHA to the source:

```sh
uvx --from git+https://github.com/pascalandy/qobuz-dl.git@FULL_40_CHARACTER_COMMIT_SHA qobuz-dl
uv tool install git+https://github.com/pascalandy/qobuz-dl.git@FULL_40_CHARACTER_COMMIT_SHA
```

A branch name such as `master` is still mutable. It does not make an install reproducible.

`qobuz-dl --version` reports the package version. Different commits can carry the same package version, so version output does not prove which source or revision is installed. Git provenance records the repository URL and resolved commit.

## Verify the install source

Maintainers can verify the floating source with temporary uv locations:

```sh
just verify-install
```

To verify one exact commit, pass its full 40-character SHA:

```sh
just verify-install-revision FULL_40_CHARACTER_COMMIT_SHA
```

The verifier requires network access. It checks the resolved Git provenance, package version, console entry points, and runtime dependencies. The actual qobuz-dl probes are limited to `--help` and `--version`. Startup tests prove that these commands do not initialize or write qobuz-dl config.

The verifier uses temporary uv cache, tool, bin, managed-Python, work, and temp locations. It disables uv config discovery and preserves `HOME`. It scopes `APPDATA`, `LOCALAPPDATA`, and XDG paths to temporary locations for software that honors them. On POSIX systems, the qobuz-dl config path remains under the preserved `HOME/.config`. The verifier makes no isolation claim for stateful qobuz-dl commands. See [Testing](testing.md#verify-the-public-git-install) for the full contract.

## Run from a local checkout

From a checkout of this repository, install and run through `uv`:

```sh
uv sync
uv run qobuz-dl --help
```

Use `uv run` for local commands so imports and dependencies resolve from the project environment. If you also have a global `qobuz-dl` install, see [Development](development.md) for the development-versus-production workflow and the `qdl-dev` alias.
