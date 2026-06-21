import sys
from pathlib import Path

import pytest

import qobuz_dl.cli as cli
from qobuz_dl.cli import _quality_fallback_enabled, _redacted_config_text
from qobuz_dl.commands import qobuz_dl_args


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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))

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
    assert "uvx qobuz-dl dl https://play.qobuz.com/album" in output
    assert "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'" in output
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
    assert "uvx qobuz-dl dl https://play.qobuz.com/album" in output
    assert "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'" in output


def test_interactive_and_lucky_help_use_uvx_examples(capsys):
    parser = qobuz_dl_args()

    with pytest.raises(SystemExit) as fun_exc:
        parser.parse_args(["fun", "--help"])
    fun_output = capsys.readouterr().out

    with pytest.raises(SystemExit) as lucky_exc:
        parser.parse_args(["lucky", "--help"])
    lucky_output = capsys.readouterr().out

    assert fun_exc.value.code == 0
    assert lucky_exc.value.code == 0
    assert "uvx qobuz-dl fun" in fun_output
    assert "uvx qobuz-dl lucky" in lucky_output
    assert "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'" in fun_output
    assert "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'" in lucky_output


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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cli, "QOBUZ_DB", str(database_file))
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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cli, "QOBUZ_DB", str(database_file))
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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cli, "QOBUZ_DB", str(database_file))
    monkeypatch.setattr(cli, "_reset_config", fake_reset)
    monkeypatch.setattr(cli, "QobuzDL", FakeQobuzDL)
    monkeypatch.setattr(cli, "_remove_leftovers", lambda directory: None)

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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    message = str(exc.value)
    assert "Your config file is corrupted:" in message
    assert "Run 'uvx qobuz-dl -r' to fix this" in message
    assert "(or 'qobuz-dl -r' if installed)." in message


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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cli, "QOBUZ_DB", str(database_file))
    monkeypatch.setattr(cli, "QobuzDL", FakeQobuzDL)
    monkeypatch.setattr(cli, "_remove_leftovers", lambda directory: None)

    cli.main()

    assert initialized[0] is None
    assert initialized[1] == (
        "user@example.com",
        "hashed-password",
        "123456",
        ["secret-one", "secret-two"],
    )
    assert downloaded == [["https://play.qobuz.com/album/album-1"]]


@pytest.mark.parametrize("database_exists", [True, False])
def test_purge_only_removes_database_and_exits(monkeypatch, tmp_path, database_exists):
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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cli, "QOBUZ_DB", str(database_file))
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert not database_file.exists()
    assert "The database was deleted." in str(exc.value)


def test_first_run_purge_does_not_initialize_config(monkeypatch, tmp_path):
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
    monkeypatch.setattr(cli, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(config_file))
    monkeypatch.setattr(cli, "QOBUZ_DB", str(database_file))
    monkeypatch.setattr(cli, "_reset_config", fail_if_reset)
    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert not database_file.exists()
    assert "The database was deleted." in str(exc.value)
