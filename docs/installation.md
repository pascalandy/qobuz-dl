# Installation

## Requirements

- `uv`
- Python 3.10 or newer, managed through `uv`
- An active Qobuz subscription

Use `uv` for user-facing, install, and local project commands. Do not use `pip` or direct `python` commands as the default workflow.

## Recommended: run without installing the app

Use `uvx` to run `qobuz-dl` without a persistent app install:

```sh
uvx qobuz-dl
```

`uvx` downloads and runs the published CLI in an isolated environment. The first run still creates the same persistent qobuz-dl config under your user config directory (`~/.config/qobuz-dl/config.ini` on Linux/macOS, `%APPDATA%\qobuz-dl\config.ini` on Windows). The downloaded-IDs database lives beside it as `qobuz_dl.db`. Your Qobuz auth/config and downloaded-IDs database are reused across later `uvx qobuz-dl ...` runs and are also reused if you later choose a persistent tool install. See [Account and authentication](use-cases.md#where-authconfig-and-the-database-live) for exact fields, caveats, and portability steps.

If configuration fails or you need to start over, reset the config file:

```sh
uvx qobuz-dl -r
```

## Optional: persistent tool install

Install persistently only if you want a permanent `qobuz-dl` command on your PATH.

### Linux and macOS

```sh
uv tool install qobuz-dl
qobuz-dl
```

To upgrade an existing tool install:

```sh
uv tool upgrade qobuz-dl
```

To uninstall a persistent tool install:

```sh
uv tool uninstall qobuz-dl
```

### Windows

Install `qobuz-dl` with the same `uv` tool workflow:

```sh
uv tool install qobuz-dl
qobuz-dl.exe
```

To upgrade an existing Windows tool install:

```sh
uv tool upgrade qobuz-dl
```

To uninstall a persistent Windows tool install:

```sh
uv tool uninstall qobuz-dl
```

Installed users can use the installed reset command instead:

```sh
qobuz-dl -r
```

## Local development install

From a checkout of this repository, install and run through `uv`:

```sh
uv sync
uv run qobuz-dl --help
```

Use `uv run` for local commands so imports and dependencies resolve from the project environment. If you also have a global `qobuz-dl` install, see [Development](development.md) for the development-versus-production workflow and the `qdl-dev` alias.
