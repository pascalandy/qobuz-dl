# Development

This repository uses `uv` for local development. Keep development commands isolated from any globally installed `qobuz-dl` command.

## Development versus production CLI

If `qobuz-dl` is already installed globally, `qobuz-dl` resolves to that installed command:

```sh
which qobuz-dl
```

Example global install path:

```text
/Users/andy16/.local/bin/qobuz-dl
```

From this checkout, use `uv run` to run the fork under development:

```sh
uv run qobuz-dl --help
```

This uses the project environment and source checkout instead of the global command.

To confirm which source is imported, run:

```sh
uv run python -c "import qobuz_dl; print(qobuz_dl.__file__)"
```

The path should point inside this repository, for example:

```text
/Users/andy16/Documents/github_local/qobuz-dl/qobuz_dl/__init__.py
```

## `qdl-dev` shell alias

The development alias is managed in the Chezmoi source file:

```text
/Users/andy16/.local/share/chezmoi/dot_zshrc
```

Alias:

```sh
alias qdl-dev='cd "$HOME/Documents/github_local/qobuz-dl" && uv run qobuz-dl'
```

Use it from any shell location:

```sh
qdl-dev --help
qdl-dev dl --help
```

This keeps the production/global `qobuz-dl` command separate from the local development fork.

## Dotfiles and Chezmoi

Personal shell configuration is managed through dotfiles with [Chezmoi](https://www.chezmoi.io/).

Do not edit applied home-directory files such as `~/.zshrc` directly when they are Chezmoi-managed. Edit the Chezmoi source instead:

```text
/Users/andy16/.local/share/chezmoi/dot_zshrc
```

Then apply changes with Chezmoi when ready:

```sh
chezmoi apply -v
```
