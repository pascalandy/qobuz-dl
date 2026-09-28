"""Command-line conventions shared by qobuz-dl and the repository scripts."""

from __future__ import annotations

import argparse
import difflib
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    FAILURE = 1
    USAGE = 2
    TEMPORARY = 75
    INTERRUPTED = 130
    TERMINATED = 143


EXIT_CODE_MEANINGS = {
    ExitCode.OK: "success, including a run with nothing to do",
    ExitCode.FAILURE: "runtime failure",
    ExitCode.USAGE: "usage error",
    ExitCode.TEMPORARY: "temporary failure; safe to retry",
    ExitCode.INTERRUPTED: "interrupted (SIGINT)",
    ExitCode.TERMINATED: "terminated (SIGTERM)",
}

HELP_FLAGS = frozenset({"-h", "--help"})


class Terminated(KeyboardInterrupt):
    """Raised by the SIGTERM handler.

    Subclassing KeyboardInterrupt lets every existing interrupt cleanup path run
    for SIGTERM too, while callers can still tell the two signals apart.
    """


def _raise_terminated(signum, frame):
    raise Terminated


@contextmanager
def sigterm_raises() -> Iterator[None]:
    """Turn SIGTERM into a ``Terminated`` exception for the duration."""
    previous = signal.signal(signal.SIGTERM, _raise_terminated)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def interruption_exit_code(error: KeyboardInterrupt) -> ExitCode:
    if isinstance(error, Terminated):
        return ExitCode.TERMINATED
    return ExitCode.INTERRUPTED


def epilog(
    examples: Sequence[str],
    exit_codes: Sequence[ExitCode] | Mapping[ExitCode, str],
    notes: Sequence[str] = (),
) -> str:
    """Build help text with examples, notes, and the exit codes a command uses.

    ``exit_codes`` is a sequence of codes, or a mapping from code to a
    command-specific meaning.
    """
    meanings = (
        dict(exit_codes)
        if isinstance(exit_codes, Mapping)
        else {code: EXIT_CODE_MEANINGS[code] for code in exit_codes}
    )
    lines = ["Examples:", *(f"  {example}" for example in examples), ""]
    if notes:
        lines.extend([*notes, ""])
    lines.append("Exit codes:")
    lines.extend(f"  {int(code):<4} {meaning}" for code, meaning in meanings.items())
    return "\n".join(lines)


@dataclass
class OptionScan:
    """What a command line asks for, found before argparse validates it."""

    parser: argparse.ArgumentParser
    subcommand: str | None = None
    found: set[str] = field(default_factory=set)
    unknown_command: str | None = None


def subcommand_parsers(parser) -> dict[str, argparse.ArgumentParser]:
    """Map each subcommand name to its parser."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _takes_value(parser, option: str) -> bool | None:
    action = parser._option_string_actions.get(option)
    if action is None:
        return None
    return action.nargs != 0


_NEGATIVE_NUMBER = re.compile(r"-\d+(?:\.\d+)?")


def _looks_like_option(argument: str) -> bool:
    """Whether argparse would read ``argument`` as an option, never as a value."""
    return (
        argument.startswith("-")
        and argument != "-"
        and _NEGATIVE_NUMBER.fullmatch(argument) is None
    )


def scan_options(
    parser: argparse.ArgumentParser,
    argv: Sequence[str],
    watched: frozenset[str] = HELP_FLAGS,
) -> OptionScan:
    """Find ``watched`` flags and the subcommand the way argparse would.

    The scan stops at ``--``, skips the values of options that take one,
    reads clustered short flags such as ``-vh``, and follows the first
    subcommand name so each flag is looked up in the parser that owns it.
    """
    scan = OptionScan(parser)
    current = parser
    subcommands = subcommand_parsers(parser)
    skip_value = False
    for argument in argv:
        if skip_value:
            skip_value = False
            if not _looks_like_option(argument):
                continue
        if argument == "--":
            break
        if argument.startswith("--"):
            name, has_value, _value = argument.partition("=")
            if name in watched:
                scan.found.add(name)
            skip_value = bool(_takes_value(current, name)) and not has_value
        elif argument.startswith("-") and len(argument) > 1:
            for index, letter in enumerate(argument[1:], start=2):
                option = f"-{letter}"
                if option in watched:
                    scan.found.add(option)
                takes_value = _takes_value(current, option)
                if takes_value is None:
                    break
                if takes_value:
                    skip_value = index == len(argument)
                    break
        elif scan.subcommand is None and argument in subcommands:
            scan.subcommand = argument
            current = subcommands[argument]
            scan.parser = current
        elif scan.subcommand is None and subcommands:
            # An unknown command name: nothing after it can select a subcommand.
            scan.unknown_command = argument
            subcommands = {}
    return scan


class Parser(argparse.ArgumentParser):
    """ArgumentParser with the shared usage-error format and no abbreviations.

    ``command`` is the invocation printed in hints, such as
    ``uv run --frozen python scripts/check.py``; it defaults to ``prog``.
    """

    def __init__(self, *args, command: str | None = None, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(*args, **kwargs)
        self.command = command or self.prog

    def usage_error(self, message: str) -> ExitCode:
        """Print the usage-error format to stderr and return the usage code."""
        # A rejected argument, such as a URL, can carry a credential.
        message = redact(message)
        self.print_usage(sys.stderr)
        sys.stderr.write(
            f"{self.prog}: error: {message}\nrun '{self.command} --help' for usage\n"
        )
        return ExitCode.USAGE

    def error(self, message):
        sys.exit(self.usage_error(message))

    def parse_args(self, args=None, namespace=None):
        argv = list(sys.argv[1:] if args is None else args)
        scan = scan_options(self, argv)
        if scan.found:
            scan.parser.print_help()
            self.exit(ExitCode.OK)
        if scan.unknown_command is not None:
            self.error(self._unknown_command_message(scan.unknown_command))
        return super().parse_args(argv, namespace)

    def _unknown_command_message(self, name: str) -> str:
        choices = list(subcommand_parsers(self))
        message = f"unknown command {name!r}"
        close = difflib.get_close_matches(name, choices, n=1)
        if close:
            return f"{message}; did you mean {close[0]!r}?"
        return f"{message}; choose from {', '.join(choices)}"


_DURATION = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h)?")
_DURATION_UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, None: 1}


def parse_duration(text: str) -> float:
    """Parse ``30``, ``30s``, ``1.5m``, ``500ms``, or ``1h`` into seconds."""
    match = _DURATION.fullmatch(text.strip())
    if match is None:
        raise argparse.ArgumentTypeError(
            f"invalid duration {text!r}; use seconds or a unit, "
            "for example 30, 30s, 2m, or 1h"
        )
    seconds = float(match["value"]) * _DURATION_UNITS[match["unit"]]
    if seconds <= 0:
        raise argparse.ArgumentTypeError("the duration must be greater than zero")
    return seconds


def env_flag(name: str, environ: Mapping[str, str] | None = None) -> bool:
    value = (os.environ if environ is None else environ).get(name, "")
    return value.strip().lower() not in ("", "0", "false", "no", "off")


def color_enabled(stream, environ: Mapping[str, str] | None = None) -> bool:
    """Color only for a terminal, and never with NO_COLOR or TERM=dumb."""
    environ = os.environ if environ is None else environ
    if environ.get("NO_COLOR"):
        return False
    if environ.get("TERM") == "dumb":
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def render(text: str, color: bool) -> str:
    """Return ``text`` unchanged with color on, or without ANSI codes."""
    return text if color else ANSI_ESCAPE.sub("", text)


def read_secret(source: str, stdin) -> str:
    """Return the first line of the file at ``source``, or of stdin for ``-``.

    Raises ``OSError`` or ``UnicodeError`` when the source cannot be read and
    ``ValueError`` when its first line is empty.
    """
    if source == "-":
        line = stdin.readline()
    else:
        with open(source, encoding="utf-8") as stream:
            line = stream.readline()
    secret = line.rstrip("\r\n")
    if not secret:
        raise ValueError("the first line is empty")
    return secret


def configure_stderr_logging(
    logger: logging.Logger, level: int, formatter: logging.Formatter | None = None
) -> logging.Handler:
    """Send ``logger`` records at ``level`` and above to stderr, and only there."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter or logging.Formatter("%(message)s"))
    logger.handlers[:] = [handler]
    logger.setLevel(level)
    logger.propagate = False
    return handler


def format_command(argv: Sequence[str]) -> str:
    """Quote ``argv`` so the printed command runs in this platform's shell."""
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


# Credentials that can surface in URLs, request parameters, or exception text.
_SECRET_NAMES = r"email|password|pwd|user_auth_token|request_sig"
# A name counts after a non-word character or an encoded one, as in %3Fpassword.
_SECRET_START = r"(?:(?<![a-z0-9_])|(?<=%[0-9a-f]{2}))"
_SECRET_PARAMETER = re.compile(
    rf"(?i){_SECRET_START}({_SECRET_NAMES})(=|%3D)((?:(?!%26)[^&\s'\"<>])+)"
)
_SECRET_FIELD = re.compile(
    rf"(?i)([\"']?\b(?:{_SECRET_NAMES})\b[\"']?\s*:\s*[\"'])([^\"']*)([\"'])"
)
REDACTED = "<redacted>"


def redact(text: str) -> str:
    """Mask credentials in query strings, encoded URLs, and quoted fields."""
    text = _SECRET_PARAMETER.sub(rf"\1\2{REDACTED}", text)
    return _SECRET_FIELD.sub(rf"\1{REDACTED}\3", text)


class ConsoleFormatter(logging.Formatter):
    """Format log records, including tracebacks, redacted and colored or not."""

    def __init__(self, color: bool):
        super().__init__("%(message)s")
        self.color = color

    def format(self, record):
        return render(redact(super().format(record)), self.color)


@contextmanager
def stderr_logging(logger: logging.Logger, level: int, color: bool):
    """Send ``logger`` records to stderr for the duration, then restore it."""
    saved = (logger.handlers[:], logger.level, logger.propagate)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ConsoleFormatter(color))
    logger.handlers[:] = [handler]
    logger.setLevel(level)
    logger.propagate = False
    try:
        yield handler
    finally:
        logger.handlers[:], level, logger.propagate = saved
        logger.setLevel(level)


class _Prompts:
    color = False


def configure_prompts(*, color: bool) -> None:
    """Choose whether prompts and menus keep their ANSI color."""
    _Prompts.color = color


def say(text: str) -> None:
    """Write one line of interactive output, such as a menu entry, to stderr."""
    sys.stderr.write(render(text, _Prompts.color) + "\n")
    sys.stderr.flush()


def prompt(text: str) -> str:
    """Write ``text`` to stderr, then read one line of input.

    ``input()`` gets no prompt of its own, so stdout keeps only results.
    """
    sys.stderr.write(render(text, _Prompts.color))
    sys.stderr.flush()
    return input()
