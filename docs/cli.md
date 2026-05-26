# CLI reference

Install the CLI with `uv tool install qobuz-dl`. From a local checkout, run CLI commands with `uv run`.

## Usage

```text
qobuz-dl [-h] [-r] [-p] [-sc] {fun,dl,lucky} ...
```

## Global options

| Option | Description |
|---|---|
| `-h`, `--help` | Show help and exit |
| `-r`, `--reset` | Create or reset the config file |
| `-p`, `--purge` | Purge or delete the downloaded-IDs database |
| `-sc`, `--show-config` | Show configuration paths and redacted configuration values |

## Commands

| Command | Description |
|---|---|
| `fun` | Interactive search and download mode using built-in numbered prompts |
| `dl` | Direct URL or text-file download mode |
| `lucky` | Search and download the first matching result or a limited result set |

Run command-level help for detailed options:

```sh
qobuz-dl <command> --help
```
