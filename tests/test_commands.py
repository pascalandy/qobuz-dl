from qobuz_dl.cli import _redacted_config_text
from qobuz_dl.commands import qobuz_dl_args


def test_parser_accepts_top_level_flags():
    parser = qobuz_dl_args()

    args = parser.parse_args(["--reset", "--purge", "--show-config"])

    assert args.reset is True
    assert args.purge is True
    assert args.show_config is True
    assert args.command is None


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
    assert args.quality == "27"
    assert args.directory == "Music"
    assert args.no_db is True


def test_parser_accepts_interactive_command_limit():
    parser = qobuz_dl_args(default_limit=20)

    args = parser.parse_args(["fun", "--limit", "5"])

    assert args.command == "fun"
    assert args.limit == "5"


def test_parser_accepts_lucky_command_query_and_type():
    parser = qobuz_dl_args()

    args = parser.parse_args(
        ["lucky", "joy", "division", "--type", "artist", "--number", "2"]
    )

    assert args.command == "lucky"
    assert args.QUERY == ["joy", "division"]
    assert args.type == "artist"
    assert args.number == "2"


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
