# CLI reference

```text
usage: qobuz-dl [-h] [-r] {fun,dl,lucky} ...

The ultimate Qobuz music downloader.
See usage examples on https://github.com/vitiko98/qobuz-dl

optional arguments:
  -h, --help      show this help message and exit
  -r, --reset     create/reset config file
  -p, --purge     purge/delete downloaded-IDs database

commands:
  run qobuz-dl <command> --help for more info
  (e.g. qobuz-dl fun --help)

  {fun,dl,lucky}
    fun           interactive mode
    dl            input mode
    lucky         lucky mode
```

## Commands

- `fun` — interactive search and download mode
- `dl` — direct URL or text-file download mode
- `lucky` — search and download the first matching result or a limited result set

Run command-level help for detailed options:

```sh
qobuz-dl <command> --help
```
