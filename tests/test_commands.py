import os
import subprocess
import sys
from pathlib import Path

import pytest

import qobuz_dl.cli as cli
from qobuz_dl import http
from qobuz_dl.cli import _quality_fallback_enabled, _redacted_config_text
from qobuz_dl.commands import QUALITY_CHOICES, qobuz_dl_args
from qobuz_dl.core import RunItem
from qobuz_dl.downloader import DownloadResult
from qobuz_dl.exceptions import ApiRateLimitError


def _write_valid_config(config_file):
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "email = user@example.com",
                "password = hashed-password",
                "default_folder = Qobuz Downloads",
                "default_limit = 20",
                "default_quality = 6",
                "no_m3u = false",
                "albums_only = false",
                "no_fallback = false",
                "og_cover = false",
                "embed_art = false",
                "no_cover = false",
                "no_database = false",
                "app_id = 123456",
                "smart_discography = false",
                "folder_format = {albumartist} - {album}",
                "track_format = {tracknumber}. {tracktitle}",
                "secrets = secret-one,secret-two",
            ]
        )
    )


def _stub_config_paths(monkeypatch, config_file, database_file=None):
    if database_file is None:
        database_file = config_file.parent / "qobuz_dl.db"
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(database_file)),
    )


def _replace_config_value(config_file, key, value):
    contents = config_file.read_text()
    prefix = f"{key} = "
    lines = [
        f"{prefix}{value}" if line.startswith(prefix) else line
        for line in contents.splitlines()
    ]
    config_file.write_text("\n".join(lines))


def _configure_cli_main(monkeypatch, config_file, argv, client):
    class UnexpectedBundle:
        def __init__(self, *args, **kwargs):
            pytest.fail("existing config must not construct Bundle")

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", *argv])
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "Bundle", UnexpectedBundle)
    monkeypatch.setattr(cli, "QobuzDL", client)


class _UnexpectedRuntime:
    def __init__(self, *args, **kwargs):
        pytest.fail("invalid config must stop before runtime construction")


def _run_config_failure(monkeypatch, capsys, caplog, config_file, argv):
    _configure_cli_main(
        monkeypatch,
        config_file,
        argv,
        _UnexpectedRuntime,
    )

    assert cli.main() == 1

    output = capsys.readouterr()
    return f"{output.out}\n{output.err}\n{caplog.text}"


def test_parser_accepts_top_level_flags():
    parser = qobuz_dl_args()

    args = parser.parse_args(["--reset", "--purge", "--show-config"])

    assert args.reset is True
    assert args.purge is True
    assert args.show_config is True
    assert args.command is None


@pytest.mark.parametrize(
    ("argv", "needs_config", "needs_auth"),
    [
        (["--reset"], False, False),
        (["--purge"], False, False),
        (["--show-config"], True, False),
        (["--show-config", "--purge"], False, False),
        ([], True, False),
        (["dl", "https://play.qobuz.com/album/example"], True, True),
        (["fun"], True, True),
        (["lucky", "joy", "division"], True, True),
    ],
)
def test_startup_classification_uses_parsed_arguments(argv, needs_config, needs_auth):
    arguments = qobuz_dl_args().parse_args(argv)

    startup = cli._classify_startup(arguments)

    assert startup.needs_config is needs_config
    assert startup.needs_auth is needs_auth


@pytest.mark.parametrize(
    "argv",
    [
        ["qobuz-dl", "--help"],
        ["qobuz-dl", "--version"],
        ["qobuz-dl", "dl", "--help"],
        ["qobuz-dl", "fun", "--help"],
        ["qobuz-dl", "lucky", "--help"],
    ],
)
def test_help_and_version_do_not_initialize_config(monkeypatch, tmp_path, argv):
    config_path = tmp_path / "missing-config-dir"
    config_file = tmp_path / "missing-config.ini"

    monkeypatch.setattr(sys, "argv", argv)

    def fail_if_resolved():
        pytest.fail("help/version must not resolve config paths")

    monkeypatch.setattr(cli, "_resolve_config_paths", fail_if_resolved)

    def fail_if_reset(config_file):
        pytest.fail(f"unexpected config reset for {config_file}")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("help/version must not initialize the Qobuz client")

    monkeypatch.setattr(cli, "_reset_config", fail_if_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    assert not config_path.exists()
    assert not config_file.exists()


@pytest.mark.parametrize("argv", [[], ["-v"], ["--no-color", "--debug"]])
def test_bare_invocation_exits_2_with_a_first_run_hint(
    monkeypatch, capsys, terminal_stdin, argv
):
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", *argv])
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: pytest.fail("a bare invocation must not resolve config"),
    )
    monkeypatch.setattr(cli, "_reset_config", lambda target: pytest.fail("reset"))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    output = capsys.readouterr()
    assert exc.value.code == 2
    assert output.out == ""
    assert output.err.startswith("usage: qobuz-dl ")
    assert output.err.endswith(
        "qobuz-dl: error: choose a command, such as 'qobuz-dl dl URL'; "
        "for first-time setup, run 'qobuz-dl --reset'\n"
        "run 'qobuz-dl --help' for usage\n"
    )


def test_parser_accepts_download_command_with_common_options():
    parser = qobuz_dl_args(default_folder="Downloads", default_quality=7)

    args = parser.parse_args(
        [
            "dl",
            "https://play.qobuz.com/album/example",
            "--quality",
            "27",
            "--directory",
            "Music",
            "--no-db",
        ]
    )

    assert args.command == "dl"
    assert args.SOURCE == ["https://play.qobuz.com/album/example"]
    assert args.quality == 27
    assert args.directory == "Music"
    assert args.db is False


def test_parser_accepts_interactive_command_limit():
    parser = qobuz_dl_args(default_limit=20)

    args = parser.parse_args(["fun", "--limit", "5"])

    assert args.command == "fun"
    assert args.limit == 5


def test_parser_accepts_lucky_command_query_and_type():
    parser = qobuz_dl_args()

    args = parser.parse_args(
        ["lucky", "joy", "division", "--type", "artist", "--limit", "2"]
    )

    assert args.command == "lucky"
    assert args.QUERY == ["joy", "division"]
    assert args.type == "artist"
    assert args.limit == 2
    assert parser.parse_args(["lucky", "joy", "--number", "3"]).limit == 3


def test_top_level_help_is_complete_and_agent_readable(capsys):
    parser = qobuz_dl_args()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Download and organize Qobuz music" in output
    assert "Docs: https://github.com/pascalandy/qobuz-dl" in output
    assert "Docs: https://github.com/vitiko98/qobuz-dl" not in output
    assert "download Qobuz/Last.fm URLs or URLs from a text file" in output
    assert "interactively search Qobuz and queue downloads" in output
    assert "search Qobuz and download the first matching results" in output
    assert "--version" in output
    assert "--show-config" in output


def test_subcommand_help_documents_supported_inputs_and_flags(capsys):
    parser = qobuz_dl_args()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["dl", "--help"])

    output = " ".join(capsys.readouterr().out.split())
    assert exc.value.code == 0
    assert "Qobuz album/track/artist/label/playlist URLs" in output
    assert "Last.fm playlist URLs" in output
    assert "local text files containing one URL per line" in output
    assert "audio quality: 5=MP3 320" in output
    assert "disables duplicate tracking for this run" in output
    assert "folder naming pattern" in output


@pytest.mark.parametrize(
    ("argv", "expected_command"),
    [
        (
            ["--help"],
            "uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl",
        ),
        (
            ["dl", "--help"],
            "uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl dl",
        ),
        (
            ["fun", "--help"],
            "uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl fun",
        ),
        (
            ["lucky", "--help"],
            "uvx --from git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl lucky",
        ),
    ],
    ids=["root", "dl", "fun", "lucky"],
)
def test_help_uses_source_qualified_fork_command(capsys, argv, expected_command):
    parser = qobuz_dl_args()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(argv)

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert expected_command in output


def test_version_flag_exits_successfully(capsys):
    parser = qobuz_dl_args()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert output.startswith("qobuz-dl ")


def test_quality_fallback_flag_overrides_config_either_way():
    assert _quality_fallback_enabled(None, False) is True
    assert _quality_fallback_enabled(None, True) is False
    assert _quality_fallback_enabled(False, False) is False
    assert _quality_fallback_enabled(True, True) is True


def test_show_config_redacts_sensitive_values(tmp_path):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "email = user@example.com",
                "password = hashed-password",
                "app_id = 123456789",
                "secrets = secret-one,secret-two",
                "default_quality = 6",
            ]
        )
    )

    output = _redacted_config_text(config_file)

    assert "user@example.com" not in output
    assert "hashed-password" not in output
    assert "123456789" not in output
    assert "secret-one" not in output
    assert "email = <redacted>" in output
    assert "password = <redacted>" in output
    assert "app_id = <redacted>" in output
    assert "secrets = <redacted>" in output
    assert "default_quality = 6" in output


def test_reset_config_creates_parent_directory(monkeypatch, tmp_path):
    config_file = tmp_path / "missing" / "config.ini"
    answers = iter(["user@example.com", "Music", "6"])

    class FakeBundle:
        def get_app_id(self):
            return "123456789"

        def get_secrets(self):
            return {"america": "secret-one", "europe": "secret-two"}

    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "hidden-password")
    monkeypatch.setattr(cli, "Bundle", FakeBundle)

    cli._reset_config(str(config_file))

    output = _redacted_config_text(config_file)
    assert config_file.is_file()
    assert "email = <redacted>" in output
    assert "password = <redacted>" in output
    assert "app_id = <redacted>" in output
    assert "secrets = <redacted>" in output
    assert "default_folder = Music" in output


def test_reset_config_leaves_duplicate_database_in_place(monkeypatch, tmp_path):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    database_file.parent.mkdir(parents=True, exist_ok=True)
    database_file.write_bytes(b"existing duplicate state")
    answers = iter(["user@example.com", "Music", "6"])

    class FakeBundle:
        def get_app_id(self):
            return "123456789"

        def get_secrets(self):
            return {"america": "secret-one", "europe": "secret-two"}

    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "hidden-password")
    monkeypatch.setattr(cli, "Bundle", FakeBundle)

    cli._reset_config(str(config_file))

    assert database_file.read_bytes() == b"existing duplicate state"


def test_reset_exits_before_client_initialization(
    monkeypatch, tmp_path, terminal_stdin
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    _write_valid_config(config_file)
    reset_calls = []

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("reset must not initialize the Qobuz client")

    def fake_reset(target, **options):
        reset_calls.append(target)
        return "reset-complete"

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--reset"])
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    assert cli.main() == 0

    assert reset_calls == [str(config_file)]


def test_first_run_reset_only_resets_once(monkeypatch, tmp_path, terminal_stdin):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    reset_calls = []

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("reset must not initialize the Qobuz client")

    def fake_reset(target, **options):
        reset_calls.append(target)
        return "reset-complete"

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--reset"])
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    assert cli.main() == 0

    assert reset_calls == [str(config_file)]


def test_show_config_exits_before_client_initialization(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    _write_valid_config(config_file)

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("show-config must not initialize the Qobuz client")

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--show-config"])
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    assert cli.main() == 0

    output = capsys.readouterr().out
    assert f"Configuration: {config_file}" in output
    assert f"Database: {database_file}" in output
    assert "user@example.com" not in output
    assert "hashed-password" not in output
    assert "secret-one" not in output
    assert "email = <redacted>" in output
    assert "password = <redacted>" in output
    assert "secrets = <redacted>" in output


@pytest.mark.parametrize(
    "argv",
    [
        ["--show-config", "--purge"],
        ["--reset", "--purge"],
        ["--purge", "dl", "https://play.qobuz.com/album/a1"],
        ["--show-config", "lucky", "some query"],
    ],
)
def test_conflicting_actions_exit_2_without_touching_config(
    monkeypatch, tmp_path, capsys, argv
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    config_path.mkdir()
    database_file.write_text("local duplicate tracking state")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("maintenance flags must not initialize the Qobuz client")

    def fail_if_reset(target):
        pytest.fail(f"purge must not reset config: {target}")

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", *argv])
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "_reset_config", fail_if_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    output = capsys.readouterr()
    assert exc.value.code == 2
    assert output.out == ""
    assert " cannot be combined with " in output.err
    assert not config_file.exists()
    assert database_file.exists()


def test_download_first_run_creates_config_once_then_initializes_client(
    monkeypatch, tmp_path, terminal_stdin
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    reset_calls = []
    initialized = []
    downloaded = []

    class FakeQobuzDL:
        def __init__(self, *args, downloads_db, **kwargs):
            self.directory = str(tmp_path / "downloads")
            initialized.append((args, downloads_db, kwargs))

        def initialize_client(self, email, password, app_id, secrets):
            initialized.append((email, password, app_id, secrets))

        def download_sources(self, sources):
            downloaded.append([source.url for source in sources])

    def fake_reset(target, **options):
        reset_calls.append(target)
        _write_valid_config(Path(target))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/album1",
        ],
    )
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", FakeQobuzDL)

    assert cli.main() == 0

    assert reset_calls == [str(config_file)]
    assert initialized[0] == (
        ("Qobuz Downloads", 6, False),
        str(database_file),
        {
            "cover_og_quality": False,
            "folder_format": "{albumartist} - {album}",
            "ignore_singles_eps": False,
            "no_cover": False,
            "no_m3u_for_playlists": False,
            "quality_fallback": True,
            "smart_discography": False,
            "track_format": "{tracknumber}. {tracktitle}",
        },
    )
    assert initialized[1] == (
        "user@example.com",
        "hashed-password",
        "123456",
        ["secret-one", "secret-two"],
    )
    assert downloaded == [["https://play.qobuz.com/album/album1"]]


def test_download_corrupted_config_reports_recovery_without_client(
    monkeypatch, tmp_path, capsys
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("[DEFAULT]\nemail = user@example.com\n")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("corrupted config must not initialize the Qobuz client")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/album1",
        ],
    )
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    assert cli.main() == 1

    message = capsys.readouterr().err
    assert message.startswith("qobuz-dl: Your config file is corrupted:")
    assert (
        "Run 'uvx --from git+https://github.com/pascalandy/qobuz-dl.git "
        "qobuz-dl -r' to fix this"
    ) in message
    assert "(or 'qobuz-dl -r' if installed)." in message


@pytest.mark.parametrize(
    "key",
    [
        "no_m3u",
        "albums_only",
        "no_fallback",
        "og_cover",
        "embed_art",
        "no_cover",
        "no_database",
        "smart_discography",
    ],
)
def test_invalid_config_boolean_is_safe_and_stops_before_runtime(
    monkeypatch, tmp_path, capsys, caplog, key
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, key, "SECRET_SENTINEL")

    diagnostic = _run_config_failure(
        monkeypatch,
        capsys,
        caplog,
        config_file,
        ["dl", "https://play.qobuz.com/album/album1"],
    )

    assert f"'{key}' must be a Boolean" in diagnostic
    assert "Your config file is corrupted:" in diagnostic
    assert "SECRET_SENTINEL" not in diagnostic


@pytest.mark.parametrize("quality", ["99", "SECRET_SENTINEL"])
def test_invalid_config_quality_is_safe_and_stops_before_runtime(
    monkeypatch, tmp_path, capsys, caplog, quality
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "default_quality", quality)

    diagnostic = _run_config_failure(
        monkeypatch,
        capsys,
        caplog,
        config_file,
        ["dl", "https://play.qobuz.com/album/album1"],
    )

    assert "'default_quality' must be one of 5, 6, 7, 27" in diagnostic
    assert "SECRET_SENTINEL" not in diagnostic


def test_invalid_config_limit_is_safe_and_stops_before_runtime(
    monkeypatch, tmp_path, capsys, caplog, terminal_stdin
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "default_limit", "SECRET_SENTINEL")

    diagnostic = _run_config_failure(monkeypatch, capsys, caplog, config_file, ["fun"])
    assert "'default_limit' must be an integer" in diagnostic
    assert "SECRET_SENTINEL" not in diagnostic


@pytest.mark.parametrize(
    ("corrupt_config", "argv"),
    [
        (
            "password = hashed-password\nSECRET_SENTINEL",
            ["dl", "https://play.qobuz.com/album/album1"],
        ),
        (
            "password = %(SECRET_SENTINEL)s",
            ["dl", "https://play.qobuz.com/album/album1"],
        ),
        (
            "password = hashed-password\npassword = SECRET_SENTINEL",
            ["dl", "https://play.qobuz.com/album/album1"],
        ),
        ("password = hashed-password\nSECRET_SENTINEL", ["--show-config"]),
    ],
    ids=[
        "malformed-line",
        "interpolation",
        "duplicate-option",
        "show-config-malformed-line",
    ],
)
def test_secret_bearing_config_failures_are_sanitized(
    monkeypatch, tmp_path, capsys, caplog, corrupt_config, argv
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "password", corrupt_config)

    diagnostic = _run_config_failure(
        monkeypatch,
        capsys,
        caplog,
        config_file,
        argv,
    )

    assert "Your config file is corrupted:" in diagnostic
    assert "SECRET_SENTINEL" not in diagnostic


@pytest.mark.parametrize(
    "failure",
    [
        lambda: OSError("SECRET_SENTINEL"),
        lambda: UnicodeDecodeError("utf-8", b"\xff", 0, 1, "SECRET_SENTINEL"),
    ],
    ids=["read-error", "decoding-error"],
)
def test_show_config_second_read_failure_is_sanitized(
    monkeypatch, tmp_path, capsys, caplog, failure
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)

    original_open = open
    read_count = 0

    def fail_second_read(*args, **kwargs):
        nonlocal read_count
        read_count += 1
        if read_count == 2:
            raise failure()
        return original_open(*args, **kwargs)

    monkeypatch.setattr(cli, "open", fail_second_read, raising=False)
    diagnostic = _run_config_failure(
        monkeypatch, capsys, caplog, config_file, ["--show-config"]
    )

    assert "The configuration file could not be read safely" in diagnostic
    assert "user@example.com" not in diagnostic
    assert "hashed-password" not in diagnostic
    assert "secret-one" not in diagnostic
    assert "SECRET_SENTINEL" not in diagnostic


@pytest.mark.parametrize("quality", QUALITY_CHOICES)
def test_valid_config_quality_reaches_client(monkeypatch, tmp_path, quality):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "default_quality", str(quality))
    initialized = []

    class FakeQobuzDL:
        def __init__(self, directory, selected_quality, *args, **kwargs):
            self.directory = directory
            initialized.append(selected_quality)

        def initialize_client(self, *args):
            pass

        def download_sources(self, sources):
            pass

    _configure_cli_main(
        monkeypatch,
        config_file,
        ["dl", "https://play.qobuz.com/album/album1"],
        FakeQobuzDL,
    )

    cli.main()

    assert initialized == [quality]


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("1", True),
        ("yes", True),
        ("true", True),
        ("on", True),
        ("0", False),
        ("no", False),
        ("false", False),
        ("off", False),
    ],
)
def test_configparser_boolean_vocabulary_is_accepted(
    monkeypatch, tmp_path, configured, expected
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    boolean_keys = (
        "no_m3u",
        "albums_only",
        "no_fallback",
        "og_cover",
        "embed_art",
        "no_cover",
        "no_database",
        "smart_discography",
    )
    for key in boolean_keys:
        _replace_config_value(config_file, key, configured)
    if expected:
        _replace_config_value(config_file, "no_cover", "false")
    initialized = []

    class FakeQobuzDL:
        def __init__(self, directory, quality, embed_art, **kwargs):
            self.directory = directory
            initialized.append((embed_art, kwargs))

        def initialize_client(self, *args):
            pass

        def download_sources(self, sources):
            pass

    _configure_cli_main(
        monkeypatch,
        config_file,
        ["dl", "https://play.qobuz.com/album/album1"],
        FakeQobuzDL,
    )

    cli.main()

    embed_art, options = initialized[0]
    assert embed_art is expected
    assert options["ignore_singles_eps"] is expected
    assert options["no_m3u_for_playlists"] is expected
    assert options["quality_fallback"] is (not expected)
    assert options["cover_og_quality"] is expected
    assert options["no_cover"] is False
    assert (options["downloads_db"] is None) is expected
    assert options["smart_discography"] is expected


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("1", True),
        ("yes", True),
        ("true", True),
        ("on", True),
        ("0", False),
        ("no", False),
        ("false", False),
        ("off", False),
    ],
)
def test_no_cover_configparser_boolean_vocabulary_is_accepted(
    tmp_path, configured, expected
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "no_cover", configured)

    values = cli._load_config_values(config_file)

    assert values["no_cover"] is expected


@pytest.mark.parametrize("limit", [0, -5])
def test_zero_and_negative_config_limits_are_preserved(
    monkeypatch, tmp_path, terminal_stdin, limit
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "default_limit", str(limit))
    observed_limits = []

    class FakeQobuzDL:
        def __init__(self, directory, *args, **kwargs):
            self.directory = directory

        def initialize_client(self, *args):
            pass

        def interactive(self, download=True):
            observed_limits.append(self.interactive_limit)

    _configure_cli_main(monkeypatch, config_file, ["fun"], FakeQobuzDL)

    cli.main()

    assert observed_limits == [limit]


def test_explicit_cli_values_override_valid_config_defaults(monkeypatch, tmp_path):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "default_folder", "Configured Music")
    _replace_config_value(config_file, "default_quality", "5")
    initialized = []

    class FakeQobuzDL:
        def __init__(self, directory, quality, embed_art, **kwargs):
            self.directory = directory
            initialized.append((directory, quality, embed_art))

        def initialize_client(self, *args):
            pass

        def download_sources(self, sources):
            pass

    _configure_cli_main(
        monkeypatch,
        config_file,
        [
            "dl",
            "https://play.qobuz.com/album/album1",
            "--directory",
            "CLI Music",
            "--quality",
            "27",
            "--embed-art",
        ],
        FakeQobuzDL,
    )

    cli.main()

    assert initialized == [("CLI Music", 27, True)]


def test_no_db_flag_wires_duplicate_tracking_off_without_blocking_download(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    _write_valid_config(config_file)
    initialized = []
    downloaded = []

    class FakeQobuzDL:
        def __init__(self, *args, downloads_db, **kwargs):
            self.directory = str(tmp_path / "downloads")
            initialized.append(downloads_db)

        def initialize_client(self, email, password, app_id, secrets):
            initialized.append((email, password, app_id, secrets))

        def download_sources(self, sources):
            downloaded.append([source.url for source in sources])

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/album1",
            "--no-db",
        ],
    )
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "QobuzDL", FakeQobuzDL)

    cli.main()

    assert initialized[0] is None
    assert initialized[1] == (
        "user@example.com",
        "hashed-password",
        "123456",
        ["secret-one", "secret-two"],
    )
    assert downloaded == [["https://play.qobuz.com/album/album1"]]


@pytest.mark.parametrize(
    ("database_exists", "message"),
    [
        (True, "The database was deleted."),
        (False, "The database is already absent."),
    ],
)
def test_purge_only_removes_database_and_exits_successfully(
    monkeypatch, tmp_path, capsys, database_exists, message
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    media_file = tmp_path / "music" / "kept.flac"
    _write_valid_config(config_file)
    media_file.parent.mkdir()
    media_file.write_bytes(b"local media")
    if database_exists:
        database_file.write_text("local duplicate tracking state")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("purge must not initialize the Qobuz client")

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--purge", "--verbose"])
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    assert cli.main() == 0

    assert not database_file.exists()
    assert media_file.read_bytes() == b"local media"
    assert capsys.readouterr() == ("", f"{message}\n")


def test_first_run_purge_does_not_initialize_config(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    config_path.mkdir()
    database_file.write_text("local duplicate tracking state")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("purge must not initialize the Qobuz client")

    def fail_if_reset(target):
        pytest.fail(f"purge must not reset config: {target}")

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--purge"])
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "_reset_config", fail_if_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    assert cli.main() == 0

    assert not config_file.exists()
    assert not database_file.exists()
    assert capsys.readouterr() == ("", "")


def test_real_console_script_purge_is_idempotent_success_without_config(tmp_path):
    script_suffix = ".exe" if os.name == "nt" else ""
    console_script = Path(sys.executable).with_name(f"qobuz-dl{script_suffix}")
    assert console_script.is_file()

    if os.name == "nt":
        config_root = tmp_path / "appdata"
        environment = {**os.environ, "APPDATA": str(config_root)}
    else:
        config_root = tmp_path / ".config"
        environment = {
            **os.environ,
            "HOME": str(tmp_path),
            "XDG_CONFIG_HOME": str(config_root),
        }

    config_path = config_root / "qobuz-dl"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    database_file.parent.mkdir(parents=True)
    database_file.write_text("local duplicate tracking state")

    present = subprocess.run(
        [str(console_script), "--purge"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert present.returncode == 0
    assert present.stdout == ""
    assert present.stderr == ""
    assert not database_file.exists()
    assert not config_file.exists()

    absent = subprocess.run(
        [str(console_script), "--purge", "--verbose"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert absent.returncode == 0
    assert absent.stdout == ""
    assert absent.stderr == "The database is already absent.\n"
    assert not database_file.exists()
    assert not config_file.exists()


def test_purge_deletion_error_exits_nonzero_without_initialization(
    monkeypatch, tmp_path, capsys
):
    config_path = tmp_path / "missing-config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    raw_error = "synthetic private operating-system detail"

    class UnexpectedBundle:
        def __init__(self):
            pytest.fail("purge must not initialize Bundle")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("purge must not initialize the Qobuz client")

    def fail_if_reset(target):
        pytest.fail(f"purge must not reset config: {target}")

    def deny_removal(target):
        assert target == str(database_file)
        raise PermissionError(raw_error)

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--purge"])
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "_reset_config", fail_if_reset)
    monkeypatch.setattr(cli, "Bundle", UnexpectedBundle)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)
    monkeypatch.setattr(cli.os, "remove", deny_removal)

    assert cli.main() == 1

    error = capsys.readouterr().err
    assert error == (
        f"qobuz-dl: Unable to delete database at {database_file}. "
        "Check its permissions.\n"
    )
    assert raw_error not in error
    assert not config_path.exists()
    assert not config_file.exists()


@pytest.mark.parametrize(
    "outcome",
    ["normal-completion", "runtime-error", "keyboard-interrupt"],
)
def test_command_dispatch_preserves_unrelated_hidden_temporaries(tmp_path, outcome):
    root_sentinel = tmp_path / ".unrelated-root.tmp"
    nested_directory = tmp_path / "nested"
    nested_sentinel = nested_directory / ".unrelated-nested.tmp"
    nested_directory.mkdir()
    root_sentinel.write_bytes(b"root sentinel bytes")
    nested_sentinel.write_bytes(b"nested sentinel bytes")
    runtime_error = RuntimeError("download failed")

    class FakeQobuz:
        directory = tmp_path

        def download_sources(self, sources):
            assert sources == ["source"]
            if outcome == "runtime-error":
                raise runtime_error
            if outcome == "keyboard-interrupt":
                raise KeyboardInterrupt

    arguments = qobuz_dl_args().parse_args(["dl", "source"])

    if outcome == "runtime-error":
        with pytest.raises(RuntimeError) as exc_info:
            cli._handle_commands(FakeQobuz(), arguments, ["source"])
        assert exc_info.value is runtime_error
    elif outcome == "keyboard-interrupt":
        # The CLI no longer swallows an interrupt; main() turns it into 130.
        with pytest.raises(KeyboardInterrupt):
            cli._handle_commands(FakeQobuz(), arguments, ["source"])
    else:
        cli._handle_commands(FakeQobuz(), arguments, ["source"])

    assert root_sentinel.read_bytes() == b"root sentinel bytes"
    assert nested_sentinel.read_bytes() == b"nested sentinel bytes"


def _scripted_runtime(outcomes, observed=None):
    """A QobuzDL stand-in that feeds scripted outcomes to the CLI's run."""

    class ScriptedQobuzDL:
        def __init__(self, directory, *args, **kwargs):
            self.directory = directory

        def initialize_client(self, *args):
            pass

        def download_sources(self, sources):
            if observed is not None:
                observed.append(list(sources))
            for entry in outcomes:
                if isinstance(entry, BaseException):
                    raise entry
                if isinstance(entry, RunItem):
                    self.run_result.add_item(entry)
                else:
                    self.run_result.add_problem(entry)
            return self.run_result

        def lucky_mode(self, query, download=True):
            assert download is False
            return observed.pop() if observed else []

        def interactive(self, download=True):
            assert download is False
            return ["https://play.qobuz.com/track/7", "https://play.qobuz.com/album/a8"]

    return ScriptedQobuzDL


def _finalized(path, reason="downloaded"):
    return RunItem(
        "https://play.qobuz.com/album/a1",
        "track",
        "1",
        DownloadResult("finalized", reason, (path,)),
    )


def test_download_prints_finalized_paths_on_stdout_and_exits_0(
    monkeypatch, tmp_path, capsys
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    outcomes = [
        _finalized("Music/Album/01. One.flac"),
        _finalized("Music/Album/02. Two.flac", "verified_artifact"),
        _finalized("Music/Album/01. One.flac", "verified_artifact"),
        RunItem("s", "album", "a2", DownloadResult("ignored", "type_filter")),
    ]
    _configure_cli_main(
        monkeypatch,
        config_file,
        ["dl", "https://play.qobuz.com/album/a1"],
        _scripted_runtime(outcomes),
    )

    assert cli.main() == 0

    assert capsys.readouterr().out == (
        "Music/Album/01. One.flac\nMusic/Album/02. Two.flac\n"
    )


@pytest.mark.parametrize(
    ("outcomes", "code"),
    [
        (
            [
                _finalized("a.flac"),
                RunItem("s", "track", "2", DownloadResult("failed", "path_conflict")),
            ],
            1,
        ),
        (
            [
                _finalized("a.flac"),
                RunItem(
                    "s",
                    "track",
                    "2",
                    DownloadResult("failed", "request_error", retryable=True),
                ),
            ],
            75,
        ),
        (
            [
                RunItem("s", "track", "2", DownloadResult("failed", "missing_url")),
                ApiRateLimitError("Qobuz API rate limit retries exhausted."),
            ],
            1,
        ),
        ([ApiRateLimitError("Qobuz API rate limit retries exhausted.")], 75),
        ([http.HttpTransportError("timed out")], 75),
        ([http.HttpStatusError(404)], 1),
    ],
    ids=[
        "permanent-failure",
        "only-temporary",
        "rate-limit-after-permanent",
        "rate-limit-alone",
        "transport-error",
        "permanent-status",
    ],
)
def test_download_exit_code_follows_the_run_outcomes(
    monkeypatch, tmp_path, capsys, outcomes, code
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _configure_cli_main(
        monkeypatch,
        config_file,
        ["dl", "https://play.qobuz.com/album/a1"],
        _scripted_runtime(outcomes),
    )

    assert cli.main() == code


@pytest.mark.parametrize(
    "source",
    [
        "https://evil.invalid/track/123",
        "https://play.qobuz.com.evil.invalid/album/abc123",
        "http://play.qobuz.com/album/abc123",
        "not-a-file.txt",
    ],
)
def test_invalid_sources_exit_2_before_config_or_client(monkeypatch, capsys, source):
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "dl", source])
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: pytest.fail("an invalid source must stop before config"),
    )
    monkeypatch.setattr(cli, "QobuzDL", _UnexpectedRuntime)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert error.startswith("usage: qobuz-dl dl ")
    assert "qobuz-dl dl: error: not a supported Qobuz or Last.fm URL" in error
    assert repr(source) in error


def test_text_file_errors_name_the_file_and_line(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    Path("urls.txt").write_text(
        "https://play.qobuz.com/album/abc1\nurls.txt\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "dl", "urls.txt"])
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: pytest.fail("an invalid file must stop before config"),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "qobuz-dl dl: error: urls.txt:2: 'urls.txt' includes itself\n" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize("query", [["ab"], ["x"], ["  "]])
def test_short_lucky_query_exits_2_before_config(monkeypatch, capsys, query):
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "lucky", *query])
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: pytest.fail("a short query must stop before config"),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert (
        "qobuz-dl lucky: error: the search query needs at least 3 characters"
        in capsys.readouterr().err
    )


def test_lucky_without_results_exits_1(monkeypatch, tmp_path):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _configure_cli_main(
        monkeypatch, config_file, ["lucky", "no such record"], _scripted_runtime([])
    )

    assert cli.main() == 1


def test_lucky_downloads_its_results_through_validated_sources(monkeypatch, tmp_path):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    observed = [["https://play.qobuz.com/album/r1", "https://play.qobuz.com/album/r2"]]
    _configure_cli_main(
        monkeypatch,
        config_file,
        ["lucky", "artist", "record"],
        _scripted_runtime([_finalized("a.flac")], observed),
    )

    assert cli.main() == 0

    assert [[source.item_id for source in sources] for sources in observed] == [
        ["r1", "r2"]
    ]


def test_fun_downloads_the_interactive_queue_through_the_result_path(
    monkeypatch, tmp_path, capsys, terminal_stdin
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    observed = []
    _configure_cli_main(
        monkeypatch,
        config_file,
        ["fun"],
        _scripted_runtime([_finalized("fun.flac")], observed),
    )

    assert cli.main() == 0

    assert [(s.url_type, s.item_id) for s in observed[0]] == [
        ("track", "7"),
        ("album", "a8"),
    ]
    assert capsys.readouterr().out == "fun.flac\n"
