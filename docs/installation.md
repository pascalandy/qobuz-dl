# Installation

## Requirements

- `uv`
- Python 3.10 or newer, managed through `uv`
- An active Qobuz subscription

Use `uv` for installs and local project commands. Do not use `pip` or direct `python` commands as the default workflow.

## Install with uv

### Linux and macOS

```sh
uv tool install qobuz-dl
```

To upgrade an existing tool install:

```sh
uv tool upgrade qobuz-dl
```

### Windows

Install `qobuz-dl` with the same `uv` tool workflow:

```sh
uv tool install qobuz-dl
```

To upgrade an existing Windows tool install:

```sh
uv tool upgrade qobuz-dl
```

## First run

Start the CLI and enter your Qobuz credentials when prompted:

### Linux and macOS

```sh
qobuz-dl
```

### Windows

```sh
qobuz-dl.exe
```

If configuration fails or you need to start over, reset the config file:

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
