import argparse
import io
import os
import signal
import time

import pytest

from qobuz_dl import console
from qobuz_dl.console import (
    ExitCode,
    Parser,
    Terminated,
    color_enabled,
    env_flag,
    epilog,
    format_command,
    interruption_exit_code,
    parse_duration,
    read_secret,
    render,
    scan_options,
    sigterm_raises,
)


def _parser():
    parser = Parser(prog="tool", command="uv run tool")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-n", "--dry-run", action="store_true")
    parser.add_argument("-c", "--config", metavar="PATH")
    subcommands = parser.add_subparsers(dest="command")
    download = subcommands.add_parser("dl", help="download")
    download.add_argument("-d", "--directory", metavar="PATH")
    download.add_argument("SOURCE", nargs="*")
    subcommands.add_parser("fun", help="search")
    return parser


def test_exit_codes_match_the_contract():
    assert {code.name: int(code) for code in ExitCode} == {
        "OK": 0,
        "FAILURE": 1,
        "USAGE": 2,
        "TEMPORARY": 75,
        "INTERRUPTED": 130,
        "TERMINATED": 143,
    }


@pytest.mark.parametrize(
    ("argv", "found", "subcommand"),
    [
        (["-h"], {"-h"}, None),
        (["--help"], {"--help"}, None),
        (["dl", "-h"], {"-h"}, "dl"),
        (["-v", "dl", "--directory", "out", "--help"], {"--help"}, "dl"),
        (["-vh"], {"-h"}, None),
        (["dl", "--", "-h"], set(), "dl"),
        (["--config", "fun", "dl", "-h"], {"-h"}, "dl"),
        (["--config=fun", "dl", "-h"], {"-h"}, "dl"),
        (["-c", "fun", "dl"], set(), "dl"),
        (["-cfun", "dl", "-h"], {"-h"}, "dl"),
        (["dl", "-d", "-h"], {"-h"}, "dl"),
        (["dll", "fun", "-h"], {"-h"}, None),
        (["dl", "fun"], set(), "dl"),
    ],
)
def test_scan_finds_help_and_the_subcommand_like_argparse(argv, found, subcommand):
    scan = scan_options(_parser(), argv)

    assert scan.found == found
    assert scan.subcommand == subcommand


def test_scan_watches_extra_flags_and_stops_at_double_dash():
    parser = _parser()
    watched = console.HELP_FLAGS | {"--dry-run", "-n"}

    assert scan_options(parser, ["-vn", "dl", "x"], watched).found == {"-n"}
    assert scan_options(parser, ["dl", "--", "--dry-run"], watched).found == set()


def test_help_wins_over_invalid_arguments_and_names_the_subcommand(capsys):
    with pytest.raises(SystemExit) as help_exit:
        _parser().parse_args(["dl", "--unknown", "--directory", "-h"])

    assert help_exit.value.code == 0
    output = capsys.readouterr()
    assert output.out.startswith("usage: tool dl ")
    assert output.err == ""


def test_double_dash_makes_help_a_value():
    arguments = _parser().parse_args(["dl", "--", "-h"])

    assert arguments.SOURCE == ["-h"]


def test_usage_error_prints_usage_error_and_help_hint(capsys):
    with pytest.raises(SystemExit) as usage_exit:
        _parser().parse_args(["--bogus"])

    assert usage_exit.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("usage: tool ")
    assert output.err.endswith(
        "tool: error: unrecognized arguments: --bogus\n"
        "run 'uv run tool --help' for usage\n"
    )


def test_subcommand_usage_error_names_the_subcommand(capsys):
    with pytest.raises(SystemExit) as usage_exit:
        _parser().parse_args(["dl", "--directory"])

    assert usage_exit.value.code == 2
    assert capsys.readouterr().err.endswith(
        "tool dl: error: argument -d/--directory: expected one argument\n"
        "run 'tool dl --help' for usage\n"
    )


def test_equals_values_clusters_and_double_dash_follow_posix_rules():
    parser = _parser()

    assert parser.parse_args(["--config=a.ini"]) == parser.parse_args(
        ["--config", "a.ini"]
    )
    assert parser.parse_args(["-vn"]) == parser.parse_args(["-v", "-n"])
    assert parser.parse_args(["-ca.ini"]).config == "a.ini"
    assert parser.parse_args(["dl", "--", "--directory"]).SOURCE == ["--directory"]


def test_long_option_abbreviations_are_rejected(capsys):
    with pytest.raises(SystemExit) as usage_exit:
        _parser().parse_args(["--verb"])

    assert usage_exit.value.code == 2
    assert "unrecognized arguments: --verb" in capsys.readouterr().err


def test_usage_error_can_be_reported_without_exiting(capsys):
    assert _parser().usage_error("missing --config") == ExitCode.USAGE

    assert capsys.readouterr().err.endswith(
        "tool: error: missing --config\nrun 'uv run tool --help' for usage\n"
    )


def test_epilog_lists_examples_notes_and_exit_codes():
    text = epilog(
        ("tool run", "tool run --verbose"),
        (ExitCode.OK, ExitCode.USAGE, ExitCode.INTERRUPTED),
        notes=("A note.",),
    )

    assert text == (
        "Examples:\n"
        "  tool run\n"
        "  tool run --verbose\n"
        "\n"
        "A note.\n"
        "\n"
        "Exit codes:\n"
        "  0    success, including a run with nothing to do\n"
        "  2    usage error\n"
        "  130  interrupted (SIGINT)"
    )


def test_epilog_accepts_command_specific_meanings():
    assert epilog(("tool",), {ExitCode.FAILURE: "a gate failed"}).endswith(
        "Exit codes:\n  1    a gate failed"
    )


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("30", 30), ("30s", 30), ("1.5m", 90), ("500ms", 0.5), ("2h", 7200)],
)
def test_parse_duration_accepts_units(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "10x", "-5", "0", "0s"])
def test_parse_duration_rejects_invalid_values(text):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        (None, False),
        ("", False),
        ("0", False),
        ("false", False),
        ("off", False),
        ("1", True),
        ("yes", True),
    ],
)
def test_env_flag(value, enabled):
    environ = {} if value is None else {"TOOL_DEBUG": value}

    assert env_flag("TOOL_DEBUG", environ) is enabled


class _Stream:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


@pytest.mark.parametrize(
    ("tty", "environ", "enabled"),
    [
        (True, {}, True),
        (False, {}, False),
        (True, {"NO_COLOR": "1"}, False),
        (True, {"TERM": "dumb"}, False),
        (True, {"NO_COLOR": ""}, True),
    ],
)
def test_color_needs_a_terminal_without_no_color_or_dumb_term(tty, environ, enabled):
    assert color_enabled(_Stream(tty), environ) is enabled


def test_color_is_off_for_streams_without_isatty():
    assert color_enabled(object(), {}) is False


def test_render_strips_ansi_only_without_color():
    text = "\033[33mYellow\033[0m and \033[1;31mbold red\033[0m"

    assert render(text, True) == text
    assert render(text, False) == "Yellow and bold red"


def test_read_secret_takes_the_first_line_of_a_file_or_stdin(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("first line\r\nsecond line\n", encoding="utf-8")

    assert read_secret(str(secret_file), io.StringIO("unused")) == "first line"
    assert read_secret("-", io.StringIO("from stdin\nmore\n")) == "from stdin"


def test_read_secret_rejects_empty_and_missing_sources(tmp_path):
    with pytest.raises(ValueError):
        read_secret("-", io.StringIO("\nsecond\n"))
    with pytest.raises(OSError):
        read_secret(str(tmp_path / "missing.txt"), io.StringIO())


def test_format_command_quotes_for_the_current_shell(monkeypatch):
    argv = ("uv", "run", "tool", "two words", "it's")

    monkeypatch.setattr(console.os, "name", "posix")
    assert format_command(argv) == "uv run tool 'two words' 'it'\"'\"'s'"
    monkeypatch.setattr(console.os, "name", "nt")
    assert format_command(argv) == 'uv run tool "two words" it\'s'


def test_interruption_exit_code_distinguishes_signals():
    assert interruption_exit_code(KeyboardInterrupt()) == ExitCode.INTERRUPTED
    assert interruption_exit_code(Terminated()) == ExitCode.TERMINATED


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal delivery")
def test_sigterm_raises_terminated_and_restores_the_previous_handler():
    previous = signal.getsignal(signal.SIGTERM)

    with pytest.raises(Terminated):
        with sigterm_raises():
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(5)  # the handler raises before the sleep ends

    assert signal.getsignal(signal.SIGTERM) is previous


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "https://x/login?email=a%40b.c&password=abc123&app_id=1",
            "https://x/login?email=<redacted>&password=<redacted>&app_id=1",
        ),
        (
            "next=https%3A%2F%2Fx%3Frequest_sig%3Dsig%26a%3D1",
            "next=https%3A%2F%2Fx%3Frequest_sig%3D<redacted>%26a%3D1",
        ),
        ("user_auth_token=tok pwd=p", "user_auth_token=<redacted> pwd=<redacted>"),
        (
            '{"password": "p", "email": "e"}',
            '{"password": "<redacted>", "email": "<redacted>"}',
        ),
        ("PASSWORD=Upper", "PASSWORD=<redacted>"),
        ("app_id=1&track_id=2", "app_id=1&track_id=2"),
        ("newpassword=kept", "newpassword=kept"),
    ],
)
def test_redact_masks_credentials_in_every_encoding(text, expected):
    assert console.redact(text) == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["-v", "dl", "x", "--debug"], ["dl", "x"]),
        (["dl", "-vn", "x"], ["dl", "-n", "x"]),
        (["-vn", "dl", "x"], ["-n", "dl", "x"]),
        (["dl", "-d", "-v", "x"], ["dl", "-d", "x"]),
        (["dl", "-dv", "x"], ["dl", "-dv", "x"]),
        (["--no-color", "dl", "--", "-v"], ["dl", "--", "-v"]),
        (["dl", "--verbose=1"], ["dl", "--verbose=1"]),
    ],
)
def test_without_flags_drops_only_diagnostic_options(argv, expected):
    from qobuz_dl.commands import qobuz_dl_args

    parser = qobuz_dl_args()

    assert console.without_flags(parser, argv, console.DIAGNOSTIC_FLAGS) == expected
