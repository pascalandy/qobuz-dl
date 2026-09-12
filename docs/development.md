# Development

This repository uses `uv` for local development. Keep development commands isolated from any globally installed `qobuz-dl` command.

## Identify the checkout and current work

Run these read-only checks in the worktree you intend to change:

```sh
git status --short
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git remote -v
```

After local environment setup, verify the project command and imported source:

```sh
uv run qobuz-dl --version
uv run python -c 'import sys, qobuz_dl; print(sys.executable); print(qobuz_dl.__file__)'
```

The imported path must be inside the intended worktree. A version string alone cannot distinguish this fork, another worktree, and an installed distribution. `uv run` can create the local environment during setup. The [architecture](architecture.md) explains application effects after startup.

For GitHub work, refresh the remote state instead of treating a dated plan or local tracking ref as current:

```sh
gh repo view --json nameWithOwner,defaultBranchRef
gh issue view 20
gh pr list --state open --limit 100 --json number,title,url,baseRefName,headRefName,headRefOid,updatedAt
```

Inspect relevant PR bodies, checks, and exact commits before depending on them. A child PR's base may be another unmerged branch. The [agent operation plan](feat/2026-09-12-agent-ergonomics/impl-plan-agent-ergonomics.md) records the observed overlap with current design work, not a live queue.

For safe offline investigation, use `uv run qobuz-dl --help` and the focused tests in the architecture's ownership map. A bare invocation or `--show-config` can create missing config and prompt. `QobuzDL` construction creates the output root and can initialize history. Use test fixtures with temporary paths for experiments; a different `--directory` does not isolate CLI credentials or history.

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

The alias selects one personal checkout. Use `uv run` directly inside another worktree so tests exercise the intended branch. These macOS paths describe the personal alias, not a required repository location.

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
