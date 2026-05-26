# Installation

## Requirements

- Python 3.8 or newer
- An active Qobuz subscription

## Install with pip

### Linux and macOS

```sh
pip3 install --upgrade qobuz-dl
```

### Windows

Install `windows-curses` first, then install `qobuz-dl`:

```sh
pip3 install windows-curses
pip3 install --upgrade qobuz-dl
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
