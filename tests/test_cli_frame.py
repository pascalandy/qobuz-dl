import io
import logging
import os
import re
import signal
import subprocess
import sys

import pytest

import qobuz_dl.cli as cli
from qobuz_dl import http
from qobuz_dl.color import CYAN, YELLOW
from qobuz_dl.commands import qobuz_dl_args
from qobuz_dl.console import Terminated, prompt, subcommand_parsers
from qobuz_dl.core import RunItem
from qobuz_dl.downloader import DownloadResult
from qobuz_dl.exceptions import AuthenticationError

URL = "https://play.qobuz.com/album/abc1"
ANSI = "\x1b["


@pytest.fixture(autouse=True)
def plain_environment(monkeypatch):
    for name in ("NO_COLOR", "TERM", "QOBUZ_DL_DEBUG"):
        monkeypatch.delenv(name, raising=False)


def _config(tmp_path, **overrides):
    values = {
        "email": "user@example.com",
        "password": "hashed-password",
        "default_folder": "Qobuz Downloads",
        "default_limit": "20",
        "default_quality": "6",
        "no_m3u": "false",
        "albums_only": "false",
        "no_fallback": "false",
        "og_cover": "false",
        "embed_art": "false",
        "no_cover": "false",
        "no_database": "false",
        "app_id": "123456",
        "smart_discography": "false",
        "folder_format": "{albumartist} - {album}",
        "track_format": "{tracknumber}. {tracktitle}",
        "secrets": "secret-one,secret-two",
    }
    values.update(overrides)
    config_file = tmp_path / "config" / "config.ini"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        "[DEFAULT]\n" + "".join(f"{key} = {value}\n" for key, value in values.items())
    )
    return config_file


def _runtime(behavior=None, constructed=None):
    """A QobuzDL stand-in; ``behavior(runtime)`` runs as the download step."""

    class Runtime:
        def __init__(self, directory, quality, embed_art, **options):
            self.directory = directory
            if constructed is not None:
                constructed.append({"embed_art": embed_art, **options})

        def initialize_client(self, *args):
            pass

        def download_sources(self, sources):
            if behavior is not None:
                behavior(self)
            return self.run_result

        def interactive(self, download=True):
            if behavior is not None:
                behavior(self)
            return []

    return Runtime


def _use(monkeypatch, tmp_path, runtime, config_file=None):
    config_file = config_file or _config(tmp_path)
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(config_file.parent / "qobuz_dl.db")),
    )
    monkeypatch.setattr(cli, "QobuzDL", runtime)


def _finalize(path):
    def behavior(runtime):
        runtime.run_result.add_item(
            RunItem(
                URL, "track", "1", DownloadResult("finalized", "downloaded", (path,))
            )
        )

    return behavior


def _help_text(argv, capsys):
    try:
        code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code
    assert code == 0
    return capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["dl", "-q", "99", "-h"],
        ["dl", URL, "--bogus", "--help"],
        ["dl", "--directory", "-h"],
        ["-vh", "dl"],
    ],
)
def test_help_wins_over_every_other_argument(capsys, argv):
    output = _help_text(argv, capsys)

    assert output.startswith("usage: qobuz-dl ")


def test_help_after_double_dash_is_a_source(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["dl", "--", "-h"])

    assert exc.value.code == 2
    assert "not a supported Qobuz or Last.fm URL, and no such file: '-h'" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("command", ["dl", "fun", "lucky", "help"])
def test_help_command_matches_command_help_flags(capsys, command):
    by_command = _help_text(["help", command], capsys)
    long_flag = _help_text([command, "--help"], capsys)
    short_flag = _help_text([command, "-h"], capsys)

    assert by_command == long_flag == short_flag
    assert by_command.startswith(f"usage: qobuz-dl {command} ")


def test_bare_help_matches_top_level_help(capsys):
    assert _help_text(["help"], capsys) == _help_text(["--help"], capsys)


@pytest.mark.parametrize("argv", [[], ["dl"], ["fun"], ["lucky"], ["help"]])
def test_every_help_lists_exit_codes_and_two_to_five_examples(capsys, argv):
    output = _help_text([*argv, "--help"], capsys)

    examples = output.split("Examples:\n", 1)[1].split("\n\n", 1)[0]
    assert 2 <= len(examples.splitlines()) <= 5
    exit_codes = output.split("Exit codes:\n", 1)[1]
    assert re.search(r"^  0 +\S", exit_codes, re.MULTILINE)
    assert re.search(r"^  2 +\S", exit_codes, re.MULTILINE)
    if argv in ([], ["dl"], ["fun"], ["lucky"]):
        for code in (1, 75, 130, 143):
            assert re.search(rf"^  {code} +\S", exit_codes, re.MULTILINE)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["dll", URL], "unknown command 'dll'; did you mean 'dl'?"),
        (["lucy", "abc"], "unknown command 'lucy'; did you mean 'lucky'?"),
        (["zzz"], "unknown command 'zzz'; choose from fun, dl, lucky, help"),
    ],
)
def test_unknown_command_suggests_the_closest_one(capsys, argv, message):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert capsys.readouterr().err.endswith(
        f"qobuz-dl: error: {message}\nrun 'qobuz-dl --help' for usage\n"
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["dl", URL, "--dir", "Music"],
        ["--show"],
        ["dl", URL, "--emb"],
        ["-sc"],
        ["dl", URL, "-ff", "{album}"],
        ["dl", URL, "-tf", "{tracktitle}"],
        ["lucky", "--limit", "0", "some query"],
        ["lucky", "-l", "many", "some query"],
        ["fun", "--limit", "-1"],
    ],
)
def test_abbreviations_removed_short_forms_and_bad_counts_exit_2(capsys, argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert "run 'qobuz-dl" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["-v", "dl", URL],
        ["dl", URL, "-v"],
        ["--verbose", "--no-color", "dl", URL],
        ["dl", "--no-color", URL, "--verbose"],
    ],
)
def test_global_options_work_before_and_after_the_command(argv):
    arguments = qobuz_dl_args().parse_args(argv)

    assert arguments.verbose is True
    assert arguments.command == "dl"
    assert arguments.SOURCE == [URL]


def test_version_works_after_a_command(capsys):
    assert _help_text(["dl", "--version"], capsys).startswith("qobuz-dl ")


def test_every_short_option_has_a_long_form():
    parser = qobuz_dl_args()
    for candidate in [parser, *subcommand_parsers(parser).values()]:
        for action in candidate._actions:
            short = [o for o in action.option_strings if not o.startswith("--")]
            if short:
                assert any(o.startswith("--") for o in action.option_strings)


@pytest.mark.parametrize(
    ("config", "argv", "option", "expected"),
    [
        ({"embed_art": "true"}, ["--no-embed-art"], "embed_art", False),
        ({"embed_art": "false"}, ["--embed-art"], "embed_art", True),
        ({"no_cover": "true"}, ["--cover"], "no_cover", False),
        ({"no_cover": "false"}, ["--no-cover"], "no_cover", True),
        ({"no_m3u": "true"}, ["--m3u"], "no_m3u_for_playlists", False),
        ({"no_fallback": "true"}, ["--fallback"], "quality_fallback", True),
        ({"no_fallback": "false"}, ["--no-fallback"], "quality_fallback", False),
        ({"albums_only": "true"}, ["--no-albums-only"], "ignore_singles_eps", False),
        ({"og_cover": "true"}, ["--no-og-cover"], "cover_og_quality", False),
        (
            {"smart_discography": "true"},
            ["--no-smart-discography"],
            "smart_discography",
            False,
        ),
        ({"embed_art": "true"}, [], "embed_art", True),
    ],
)
def test_switches_override_saved_config_in_both_directions(
    monkeypatch, tmp_path, config, argv, option, expected
):
    constructed = []
    _use(
        monkeypatch,
        tmp_path,
        _runtime(constructed=constructed),
        _config(tmp_path, **config),
    )

    assert cli.main(["dl", URL, *argv]) == 0

    assert constructed[0][option] is expected


@pytest.mark.parametrize(
    ("no_database", "argv", "uses_database"),
    [("true", ["--db"], True), ("false", ["--no-db"], False), ("true", [], False)],
)
def test_database_switch_overrides_config(
    monkeypatch, tmp_path, no_database, argv, uses_database
):
    constructed = []
    config_file = _config(tmp_path, no_database=no_database)
    _use(monkeypatch, tmp_path, _runtime(constructed=constructed), config_file)

    assert cli.main(["dl", URL, *argv]) == 0

    assert (constructed[0]["downloads_db"] is not None) is uses_database


def test_import_configures_nothing_and_does_not_import_the_cli():
    probe = (
        "import logging, sys\n"
        "import qobuz_dl\n"
        "assert 'qobuz_dl.cli' not in sys.modules, 'cli imported'\n"
        "assert logging.getLogger().handlers == [], 'root logging configured'\n"
        "assert callable(qobuz_dl.main)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )

    assert (result.returncode, result.stderr) == (0, "")


@pytest.mark.parametrize("argv", [["--help"], ["dl", "--help"], ["--version"]])
def test_module_invocation_is_silent_on_stderr(argv):
    result = subprocess.run(
        [sys.executable, "-W", "error", "-m", "qobuz_dl.cli", *argv],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.startswith(("usage: qobuz-dl", "qobuz-dl "))


def _noisy(outcome):
    def behavior(runtime):
        log = logging.getLogger("qobuz_dl.core")
        log.debug("debug detail")
        log.info(f"{YELLOW}progress line")
        _finalize("Music/01. One.flac")(runtime)
        if outcome == "failure":
            runtime.run_result.add_item(
                RunItem(URL, "track", "2", DownloadResult("failed", "path_conflict"))
            )

    return behavior


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_verbosity_changes_only_stderr(monkeypatch, tmp_path, capsys, outcome):
    _use(monkeypatch, tmp_path, _runtime(_noisy(outcome)))
    runs = {}
    for flags in ([], ["-v"], ["--debug"]):
        code = cli.main(["dl", URL, *flags])
        runs[tuple(flags)] = (code, capsys.readouterr())

    codes = {code for code, _output in runs.values()}
    outs = {output.out for _code, output in runs.values()}
    assert codes == {0 if outcome == "success" else 1}
    assert outs == {"Music/01. One.flac\n"}
    assert runs[()][1].err == ""
    assert runs[("-v",)][1].err == "progress line\n"
    assert runs[("--debug",)][1].err == "debug detail\nprogress line\n"


def test_debug_environment_variable_enables_debug(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("QOBUZ_DL_DEBUG", "1")
    _use(monkeypatch, tmp_path, _runtime(_noisy("success")))

    assert cli.main(["dl", URL]) == 0

    assert "debug detail\n" in capsys.readouterr().err


class _TerminalStream(io.StringIO):
    def isatty(self):
        return True


@pytest.mark.parametrize(
    ("tty", "environment", "flags", "colored"),
    [
        (True, {}, [], True),
        (False, {}, [], False),
        (True, {"NO_COLOR": "1"}, [], False),
        (True, {"TERM": "dumb"}, [], False),
        (True, {}, ["--no-color"], False),
    ],
    ids=["terminal", "pipe", "no-color-env", "dumb-term", "no-color-flag"],
)
def test_color_matrix_covers_logs_and_prompts(
    monkeypatch, tmp_path, terminal_stdin, tty, environment, flags, colored
):
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    stderr = _TerminalStream() if tty else io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr("builtins.input", lambda *args: "answer")

    def behavior(runtime):
        logging.getLogger("qobuz_dl.core").warning(f"{YELLOW}a warning")
        prompt(f"{CYAN}Enter your search: ")

    _use(monkeypatch, tmp_path, _runtime(behavior))

    assert cli.main(["fun", *flags]) == 0

    written = stderr.getvalue()
    assert "a warning" in written
    assert "Enter your search: " in written
    assert (ANSI in written) is colored


def test_prompts_and_menus_never_touch_stdout(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *args: "reply")

    assert prompt("Question? ") == "reply"

    assert capsys.readouterr() == ("", "Question? ")


@pytest.mark.parametrize(
    ("argv", "tty"),
    [(["dl", URL], False), (["dl", URL, "--no-input"], True)],
    ids=["piped-stdin", "no-input"],
)
def test_missing_config_without_a_terminal_exits_2(
    monkeypatch, tmp_path, capsys, argv, tty
):
    config_file = tmp_path / "config" / "config.ini"
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(tmp_path / "config" / "qobuz_dl.db")),
    )
    monkeypatch.setattr(sys, "stdin", _TerminalStream() if tty else io.StringIO())
    monkeypatch.setattr(cli, "_reset_config", lambda path: pytest.fail("prompted"))

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert capsys.readouterr().err.endswith(
        f"qobuz-dl: error: no config file at {config_file}; create it in a "
        "terminal with 'qobuz-dl --reset'\nrun 'qobuz-dl --help' for usage\n"
    )
    assert not config_file.exists()


@pytest.mark.parametrize("argv", [["fun", "--no-input"], ["--reset", "--no-input"]])
def test_no_input_rejects_commands_that_prompt(
    monkeypatch, capsys, terminal_stdin, argv
):
    monkeypatch.setattr(
        cli, "_resolve_config_paths", lambda: pytest.fail("reached config")
    )

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert "terminal" in capsys.readouterr().err


def test_input_ending_mid_prompt_is_a_usage_error(
    monkeypatch, tmp_path, capsys, terminal_stdin
):
    def closed(*args):
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)
    _use(monkeypatch, tmp_path, _runtime(lambda runtime: prompt("Search: ")))

    assert cli.main(["fun"]) == 2

    assert capsys.readouterr().err.endswith(
        "qobuz-dl: input ended before the prompt was answered\n"
    )


SENTINELS = ("EMAIL_SENTINEL", "PASSWORD_SENTINEL", "TOKEN_SENTINEL", "SIG_SENTINEL")


def _leaky_login(monkeypatch, tmp_path):
    def initialize_client(self, *args):
        try:
            raise RuntimeError(
                "cause: user_auth_token=TOKEN_SENTINEL "
                "next=https%3A%2F%2Fx%3Frequest_sig%3DSIG_SENTINEL%26a%3D1"
            )
        except RuntimeError as cause:
            raise ValueError(
                "bad URL https://www.qobuz.com/api.json/0.2/user/login"
                "?email=EMAIL_SENTINEL&password=PASSWORD_SENTINEL&app_id=1"
            ) from cause

    runtime = _runtime()
    runtime.initialize_client = initialize_client
    _use(monkeypatch, tmp_path, runtime)


def test_unexpected_errors_are_redacted_and_traced_only_with_debug(
    monkeypatch, tmp_path, capsys
):
    _leaky_login(monkeypatch, tmp_path)

    assert cli.main(["dl", URL]) == 1
    quiet = capsys.readouterr()
    assert "Traceback" not in quiet.err
    assert quiet.err.endswith(f"rerun with a stack trace: qobuz-dl --debug dl {URL}\n")

    assert cli.main(["dl", URL, "--debug"]) == 1
    debug = capsys.readouterr()
    assert "Traceback (most recent call last)" in debug.err
    assert "The above exception was the direct cause" in debug.err
    assert "<redacted>" in debug.err
    for sentinel in SENTINELS:
        assert sentinel not in quiet.err + debug.err + quiet.out + debug.out


def test_log_record_tracebacks_are_redacted(monkeypatch, tmp_path, capsys):
    def behavior(runtime):
        try:
            raise ValueError("password=PASSWORD_SENTINEL")
        except ValueError:
            logging.getLogger("qobuz_dl.downloader").error(
                "tagging failed for email=EMAIL_SENTINEL", exc_info=True
            )

    _use(monkeypatch, tmp_path, _runtime(behavior))

    assert cli.main(["dl", URL, "--debug"]) == 0

    error = capsys.readouterr().err
    assert "Traceback" in error
    assert "PASSWORD_SENTINEL" not in error
    assert "EMAIL_SENTINEL" not in error


def test_tagging_tracebacks_appear_only_under_debug(tmp_path, monkeypatch, caplog):
    from qobuz_dl import downloader

    download = downloader.Download(
        object(),
        "1",
        str(tmp_path),
        6,
        no_cover=True,
        verified_destinations=False,
    )
    preparation = downloader._DownloadPreparation(str(tmp_path), False, "{tracktitle}")
    monkeypatch.setattr(
        downloader,
        "download_with_progress",
        lambda url, filename, *args, **kwargs: open(filename, "wb").close(),
    )

    def broken_tagger(*args, **kwargs):
        raise ValueError("tagging broke")

    monkeypatch.setattr(downloader.metadata, "tag_flac", broken_tagger)
    track = {
        "id": "1",
        "title": "Song",
        "track_number": 1,
        "maximum_bit_depth": 16,
        "maximum_sampling_rate": 44.1,
    }
    url = {"url": "https://media.example.test/1.flac"}

    for level, traced in ((logging.WARNING, False), (logging.DEBUG, True)):
        caplog.clear()
        caplog.set_level(level, logger="qobuz_dl.downloader")
        result = download._download_prepared_track(preparation, url, track, track, True)
        assert result.reason == "tagging_error"
        (record,) = [r for r in caplog.records if "Error tagging" in r.getMessage()]
        assert bool(record.exc_info) is traced


@pytest.mark.parametrize(
    ("error", "code", "hint"),
    [
        (AuthenticationError("Invalid credentials."), 1, None),
        (http.HttpTransportError("timed out"), 75, f"retry: qobuz-dl dl {URL}"),
        (http.HttpStatusError(503), 75, f"retry: qobuz-dl dl {URL}"),
        (http.HttpStatusError(404), 1, None),
    ],
)
def test_login_errors_map_to_exit_codes(
    monkeypatch, tmp_path, capsys, error, code, hint
):
    runtime = _runtime()

    def initialize_client(self, *args):
        raise error

    runtime.initialize_client = initialize_client
    _use(monkeypatch, tmp_path, runtime)

    assert cli.main(["dl", URL]) == code

    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == f"qobuz-dl: login failed: {error}"
    assert lines[1:] == ([hint] if hint else [])


def test_bundle_fetch_outage_during_setup_exits_75(
    monkeypatch, tmp_path, capsys, terminal_stdin
):
    config_file = tmp_path / "config" / "config.ini"
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(tmp_path / "qobuz_dl.db")),
    )
    monkeypatch.setattr("builtins.input", lambda *args: "user@example.com")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "password")

    def unavailable():
        raise http.HttpStatusError(502)

    monkeypatch.setattr(cli, "Bundle", unavailable)

    assert cli.main(["--reset"]) == 75

    assert capsys.readouterr().err.endswith(
        "qobuz-dl: Unable to read the Qobuz web bundle: HTTP status 502. "
        "Configuration was not saved.\nretry: qobuz-dl --reset\n"
    )
    assert not config_file.exists()


@pytest.mark.parametrize(
    ("interruption", "code"), [(KeyboardInterrupt, 130), (Terminated, 143)]
)
def test_interrupt_keeps_earlier_paths_and_exits_with_the_signal_code(
    monkeypatch, tmp_path, capsys, interruption, code
):
    def behavior(runtime):
        _finalize("Music/01. One.flac")(runtime)
        runtime.run_result.add_item(
            RunItem(URL, "track", "2", DownloadResult("failed", "path_conflict"))
        )
        raise interruption

    _use(monkeypatch, tmp_path, _runtime(behavior))

    assert cli.main(["dl", URL]) == code

    assert capsys.readouterr() == (
        "Music/01. One.flac\n",
        "qobuz-dl: interrupted; finished files were kept\n",
    )


SIGNAL_DRIVER = """
import signal
import sys
import time
from pathlib import Path

import qobuz_dl.cli as cli
from qobuz_dl.core import RunItem
from qobuz_dl.downloader import DownloadResult

signal.signal(signal.SIGINT, signal.default_int_handler)
workspace = Path(sys.argv[1])
config = workspace / "config.ini"
config.write_text(
    "[DEFAULT]\\nemail = a@b.c\\npassword = x\\ndefault_folder = M\\n"
    "default_limit = 20\\ndefault_quality = 6\\nno_m3u = false\\n"
    "albums_only = false\\nno_fallback = false\\nog_cover = false\\n"
    "embed_art = false\\nno_cover = false\\nno_database = true\\n"
    "app_id = 1\\nsmart_discography = false\\nfolder_format = {album}\\n"
    "track_format = {tracktitle}\\nsecrets = s\\n"
)


class Runtime:
    def __init__(self, *args, **kwargs):
        pass

    def initialize_client(self, *args):
        pass

    def download_sources(self, sources):
        self.run_result.add_item(
            RunItem("s", "track", "1", DownloadResult("finalized", "downloaded", ("M/one.flac",)))
        )
        (workspace / "ready").touch()
        while True:
            time.sleep(0.05)


cli._resolve_config_paths = lambda: (str(config), str(workspace / "db"))
cli.QobuzDL = Runtime
sys.exit(cli.main(["dl", "https://play.qobuz.com/album/abc1"]))
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal delivery")
@pytest.mark.parametrize(
    ("signal_number", "code"), [(signal.SIGINT, 130), (signal.SIGTERM, 143)]
)
def test_real_signal_exits_with_its_code_after_printing_finished_paths(
    signal_driver, signal_number, code
):
    status, out, err = signal_driver(SIGNAL_DRIVER, signal_number)

    assert (status, out, err) == (
        code,
        "M/one.flac\n",
        "qobuz-dl: interrupted; finished files were kept\n",
    )
