import os
import subprocess
import sys
import traceback
from pathlib import Path

import pytest

import qobuz_dl.cli as cli
from qobuz_dl.cli import _quality_fallback_enabled, _redacted_config_text
from qobuz_dl.color import GREEN, RESET
from qobuz_dl.commands import QUALITY_CHOICES, qobuz_dl_args


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


def _append_config_value(config_file, key, value):
    config_file.write_text(f"{config_file.read_text()}\n{key} = {value}\n")


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
    with pytest.raises(SystemExit) as exc:
        cli.main()

    output = capsys.readouterr()
    formatted_exception = "".join(
        traceback.format_exception(exc.type, exc.value, exc.tb)
    )
    return f"{formatted_exception}\n{output.out}\n{output.err}\n{caplog.text}"


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


def test_no_argument_first_run_creates_config_then_prints_help(
    monkeypatch, tmp_path, capsys
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    reset_calls = []

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("no-argument startup must not initialize the Qobuz client")

    def fake_reset(target):
        reset_calls.append(target)
        _write_valid_config(Path(target))

    monkeypatch.setattr(sys, "argv", ["qobuz-dl"])
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert reset_calls == [str(config_file)]
    assert config_file.is_file()
    assert "Download and organize Qobuz music" in output


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
    assert args.no_db is True


def test_parser_accepts_interactive_command_limit():
    parser = qobuz_dl_args(default_limit=20)

    args = parser.parse_args(["fun", "--limit", "5"])

    assert args.command == "fun"
    assert args.limit == 5


def test_parser_accepts_lucky_command_query_and_type():
    parser = qobuz_dl_args()

    args = parser.parse_args(
        ["lucky", "joy", "division", "--type", "artist", "--number", "2"]
    )

    assert args.command == "lucky"
    assert args.QUERY == ["joy", "division"]
    assert args.type == "artist"
    assert args.number == 2


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

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Qobuz album/track/artist/label/playlist URLs" in output
    assert "Last.fm playlist URLs" in output
    assert "local text files containing one URL per line" in output
    assert "audio quality: 5=MP3 320" in output
    assert "disable duplicate tracking for this run" in output
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


def test_quality_fallback_is_disabled_by_flag_or_config():
    assert _quality_fallback_enabled(False, False) is True
    assert _quality_fallback_enabled(True, False) is False
    assert _quality_fallback_enabled(False, True) is False
    assert _quality_fallback_enabled(True, True) is False


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

    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
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
    assert "bandwidth_limit = off" in output


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

    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "hidden-password")
    monkeypatch.setattr(cli, "Bundle", FakeBundle)

    cli._reset_config(str(config_file))

    assert database_file.read_bytes() == b"existing duplicate state"


def test_reset_exits_before_client_initialization(monkeypatch, tmp_path):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    _write_valid_config(config_file)
    reset_calls = []

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("reset must not initialize the Qobuz client")

    def fake_reset(target):
        reset_calls.append(target)
        return "reset-complete"

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--reset"])
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == "reset-complete"
    assert reset_calls == [str(config_file)]


def test_first_run_reset_only_resets_once(monkeypatch, tmp_path):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    reset_calls = []

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("reset must not initialize the Qobuz client")

    def fake_reset(target):
        reset_calls.append(target)
        return "reset-complete"

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--reset"])
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == "reset-complete"
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

    with pytest.raises(SystemExit) as exc:
        cli.main()

    output = capsys.readouterr().out
    assert exc.value.code is None
    assert f"Configuration: {config_file}" in output
    assert f"Database: {database_file}" in output
    assert "user@example.com" not in output
    assert "hashed-password" not in output
    assert "secret-one" not in output
    assert "email = <redacted>" in output
    assert "password = <redacted>" in output
    assert "secrets = <redacted>" in output


def test_show_config_with_purge_does_not_initialize_first_run_config(
    monkeypatch, tmp_path, capsys
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

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--show-config", "--purge"])
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "_reset_config", fail_if_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    output = capsys.readouterr().out
    assert exc.value.code is None
    assert not config_file.exists()
    assert database_file.exists()
    assert f"Configuration: {config_file}" in output
    assert f"Database: {database_file}" in output


def test_download_first_run_creates_config_once_then_initializes_client(
    monkeypatch, tmp_path
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

        def download_list_of_urls(self, urls):
            downloaded.append(list(urls))

    def fake_reset(target):
        reset_calls.append(target)
        _write_valid_config(Path(target))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/album-1",
        ],
    )
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", FakeQobuzDL)

    cli.main()

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
            "bandwidth_limit": None,
        },
    )
    assert initialized[1] == (
        "user@example.com",
        "hashed-password",
        "123456",
        ["secret-one", "secret-two"],
    )
    assert downloaded == [["https://play.qobuz.com/album/album-1"]]


def test_download_corrupted_config_reports_recovery_without_client(
    monkeypatch, tmp_path
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
            "https://play.qobuz.com/album/album-1",
        ],
    )
    _stub_config_paths(monkeypatch, config_file)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    message = str(exc.value)
    assert "Your config file is corrupted:" in message
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
        ["dl", "https://play.qobuz.com/album/album-1"],
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
        ["dl", "https://play.qobuz.com/album/album-1"],
    )

    assert "'default_quality' must be one of 5, 6, 7, 27" in diagnostic
    assert "SECRET_SENTINEL" not in diagnostic


def test_invalid_config_limit_is_safe_and_stops_before_runtime(
    monkeypatch, tmp_path, capsys, caplog
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
            ["dl", "https://play.qobuz.com/album/album-1"],
        ),
        (
            "password = %(SECRET_SENTINEL)s",
            ["dl", "https://play.qobuz.com/album/album-1"],
        ),
        (
            "password = hashed-password\npassword = SECRET_SENTINEL",
            ["dl", "https://play.qobuz.com/album/album-1"],
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

        def download_list_of_urls(self, urls):
            pass

    _configure_cli_main(
        monkeypatch,
        config_file,
        ["dl", "https://play.qobuz.com/album/album-1"],
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

        def download_list_of_urls(self, urls):
            pass

    _configure_cli_main(
        monkeypatch,
        config_file,
        ["dl", "https://play.qobuz.com/album/album-1"],
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
def test_zero_and_negative_config_limits_are_preserved(monkeypatch, tmp_path, limit):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _replace_config_value(config_file, "default_limit", str(limit))
    observed_limits = []

    class FakeQobuzDL:
        def __init__(self, directory, *args, **kwargs):
            self.directory = directory

        def initialize_client(self, *args):
            pass

        def interactive(self):
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

        def download_list_of_urls(self, urls):
            pass

    _configure_cli_main(
        monkeypatch,
        config_file,
        [
            "dl",
            "https://play.qobuz.com/album/album-1",
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


@pytest.mark.parametrize(
    ("configured", "cli_value", "expected"),
    [
        ("1KiB/s", None, 1024),
        ("1KiB/s", "off", None),
        ("SECRET_SENTINEL", "2MiB/s", 2 * 1024 * 1024),
    ],
)
def test_effective_bandwidth_limit_reaches_client(
    monkeypatch, tmp_path, configured, cli_value, expected
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _append_config_value(config_file, "bandwidth_limit", configured)
    initialized = []

    class FakeQobuzDL:
        def __init__(self, directory, quality, embed_art, **kwargs):
            self.directory = directory
            initialized.append(kwargs["bandwidth_limit"])

        def initialize_client(self, *args):
            pass

        def download_list_of_urls(self, urls):
            pass

    argv = ["dl", "https://play.qobuz.com/album/album-1"]
    if cli_value is not None:
        argv.extend(("--bandwidth-limit", cli_value))
    _configure_cli_main(monkeypatch, config_file, argv, FakeQobuzDL)

    cli.main()

    assert initialized == [expected]


def test_old_config_without_bandwidth_limit_remains_unlimited(tmp_path):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)

    values = cli._load_config_values(config_file)

    assert values["bandwidth_limit"] is None


def test_invalid_effective_config_bandwidth_stops_before_auth_without_echo(
    monkeypatch, tmp_path, capsys, caplog
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    _append_config_value(config_file, "bandwidth_limit", "SECRET_SENTINEL")

    diagnostic = _run_config_failure(
        monkeypatch,
        capsys,
        caplog,
        config_file,
        ["dl", "https://play.qobuz.com/album/album-1"],
    )

    assert "'bandwidth_limit' must be 'off', NKiB/s, or NMiB/s" in diagnostic
    assert "SECRET_SENTINEL" not in diagnostic


def test_config_bandwidth_over_integer_digit_limit_uses_fixed_safe_error(
    monkeypatch, tmp_path, capsys, caplog
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(config_file)
    value = f"{'9' * 5000}KiB/s"
    _append_config_value(config_file, "bandwidth_limit", value)

    diagnostic = _run_config_failure(
        monkeypatch,
        capsys,
        caplog,
        config_file,
        ["dl", "https://play.qobuz.com/album/album-1"],
    )

    assert "'bandwidth_limit' must be 'off', NKiB/s, or NMiB/s" in diagnostic
    assert value not in diagnostic


def test_invalid_cli_bandwidth_stops_before_config_or_auth(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/album-1",
            "--bandwidth-limit",
            "1MB/s",
        ],
    )

    def unexpected_config_access():
        pytest.fail("invalid CLI bandwidth must stop before config access")

    monkeypatch.setattr(cli, "_resolve_config_paths", unexpected_config_access)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    output = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "--bandwidth-limit" in output.err


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

        def download_list_of_urls(self, urls):
            downloaded.append(list(urls))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/album-1",
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
    assert downloaded == [["https://play.qobuz.com/album/album-1"]]


@pytest.mark.parametrize(
    ("database_exists", "message"),
    [
        (True, "The database was deleted."),
        (False, "The database is already absent."),
    ],
)
def test_purge_only_removes_database_and_exits_successfully(
    monkeypatch, tmp_path, caplog, database_exists, message
):
    config_path = tmp_path / "config"
    config_file = config_path / "config.ini"
    database_file = config_path / "qobuz_dl.db"
    _write_valid_config(config_file)
    if database_exists:
        database_file.write_text("local duplicate tracking state")

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("purge must not initialize the Qobuz client")

    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--purge"])
    _stub_config_paths(monkeypatch, config_file, database_file)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    result = cli.main()

    assert result is None
    assert not database_file.exists()
    assert caplog.messages == [f"{GREEN}{message}{RESET}"]


def test_first_run_purge_does_not_initialize_config(monkeypatch, tmp_path, caplog):
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

    result = cli.main()

    assert result is None
    assert not config_file.exists()
    assert not database_file.exists()
    assert caplog.messages == [f"{GREEN}The database was deleted.{RESET}"]


def test_real_console_script_purge_is_idempotent_success_without_config(tmp_path):
    script_suffix = ".exe" if os.name == "nt" else ""
    console_script = Path(sys.executable).with_name(f"qobuz-dl{script_suffix}")
    assert console_script.is_file()

    if os.name == "nt":
        config_root = tmp_path / "appdata"
        environment = {**os.environ, "APPDATA": str(config_root)}
    else:
        config_root = tmp_path / ".config"
        environment = {**os.environ, "HOME": str(tmp_path)}

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
    assert "The database was deleted." in present.stderr
    assert not database_file.exists()
    assert not config_file.exists()

    absent = subprocess.run(
        [str(console_script), "--purge"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert absent.returncode == 0
    assert absent.stdout == ""
    assert "The database is already absent." in absent.stderr
    assert not database_file.exists()
    assert not config_file.exists()


def test_purge_deletion_error_exits_nonzero_without_initialization(
    monkeypatch, tmp_path
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

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == (
        f"Unable to delete database at {database_file}. Check its permissions."
    )
    assert exc.value.code != 0
    assert raw_error not in str(exc.value)
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

        def download_list_of_urls(self, sources):
            assert sources == ["source"]
            if outcome == "runtime-error":
                raise runtime_error
            if outcome == "keyboard-interrupt":
                raise KeyboardInterrupt

    arguments = qobuz_dl_args().parse_args(["dl", "source"])

    if outcome == "runtime-error":
        with pytest.raises(RuntimeError) as exc_info:
            cli._handle_commands(FakeQobuz(), arguments)
        assert exc_info.value is runtime_error
    else:
        cli._handle_commands(FakeQobuz(), arguments)

    assert root_sentinel.read_bytes() == b"root sentinel bytes"
    assert nested_sentinel.read_bytes() == b"nested sentinel bytes"
