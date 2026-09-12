import configparser
import os
import stat
import sys

import pytest

import qobuz_dl.cli as cli


@pytest.fixture
def config_file(monkeypatch, tmp_path):
    path = tmp_path / "qobuz-dl" / "config.ini"
    database = path.parent / "qobuz_dl.db"
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(path), str(database)),
    )
    answers = iter(["new@example.com", "My Music", "27"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "password")

    class FakeBundle:
        def get_app_id(self):
            return "987654321"

        def get_secrets(self):
            return {"america": "new-secret-one", "europe": "new-secret-two"}

    monkeypatch.setattr(cli, "Bundle", FakeBundle)
    return path


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits required")
@pytest.mark.parametrize("arguments", [[], ["--reset"]])
def test_new_config_is_private_with_permissive_umask(
    monkeypatch, config_file, arguments
):
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", *arguments])
    previous_umask = os.umask(0)
    try:
        with pytest.raises(SystemExit) as exc:
            cli.main()
    finally:
        os.umask(previous_umask)

    assert exc.value.code in (None, 0)
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(config_file.parent.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits required")
@pytest.mark.parametrize("arguments", [[], ["--show-config"]])
def test_startup_repairs_permissions_without_rewriting_config(
    monkeypatch, config_file, arguments
):
    config_file.parent.mkdir(mode=0o755)
    ancestor_mode = stat.S_IMODE(config_file.parent.parent.stat().st_mode)
    original = (
        b"# Preserve my formatting and custom options\n"
        b"[DEFAULT]\nemail=old@example.com\npassword=old-hash\n"
        b"default_folder=/my/music\ndefault_quality=7\ndefault_limit=43\n"
        b"no_m3u=true\nalbums_only=false\nno_fallback=true\n"
        b"og_cover=false\nembed_art=true\nno_cover=false\n"
        b"no_database=true\napp_id=123\nsmart_discography=true\n"
        b"folder_format={album}\ntrack_format={tracktitle}\n"
        b"secrets=old-secret\ncustom_option=keep this\n"
    )
    config_file.write_bytes(original)
    config_file.chmod(0o644)
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", *arguments])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code in (None, 0)
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(config_file.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(config_file.parent.parent.stat().st_mode) == ancestor_mode
    assert config_file.read_bytes() == original


@pytest.mark.parametrize(
    ("operation", "failure"),
    [
        ("write", OSError),
        ("write", ValueError),
        ("write", KeyboardInterrupt),
        ("fsync", OSError),
        ("replace", OSError),
        pytest.param(
            "chmod",
            PermissionError,
            marks=pytest.mark.skipif(os.name != "posix", reason="POSIX modes required"),
        ),
    ],
)
def test_failed_reset_preserves_previous_config_and_removes_partial_write(
    monkeypatch, config_file, capsys, caplog, operation, failure
):
    config_file.parent.mkdir(mode=0o700)
    original = b"[DEFAULT]\nemail=old@example.com\ncustom_option=keep this\n"
    config_file.write_bytes(original)
    config_file.chmod(0o600)
    write_modes = []
    original_write = configparser.ConfigParser.write

    def fail_operation(*args, **kwargs):
        if failure is KeyboardInterrupt:
            raise KeyboardInterrupt
        raise failure("Cannot write new-secret-one for new@example.com")

    def fail_during_write(config, stream, *args, **kwargs):
        write_modes.append(stat.S_IMODE(os.fstat(stream.fileno()).st_mode))
        if operation == "write":
            stream.write("[DEFAULT]\nsecrets = new-secret-one\n")
            stream.flush()
            fail_operation()
        original_write(config, stream, *args, **kwargs)

    monkeypatch.setattr(configparser.ConfigParser, "write", fail_during_write)
    if operation != "write":
        monkeypatch.setattr(cli.os, operation, fail_operation)
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--reset"])

    with pytest.raises(
        KeyboardInterrupt if failure is KeyboardInterrupt else SystemExit
    ) as exc:
        cli.main()

    assert config_file.read_bytes() == original
    assert sorted(path.name for path in config_file.parent.iterdir()) == ["config.ini"]
    if os.name == "posix":
        assert write_modes == ([] if operation == "chmod" else [0o600])
    output = capsys.readouterr()
    diagnostic = f"{exc.value}\n{output.out}\n{output.err}\n{caplog.text}"
    assert "new-secret-one" not in diagnostic
    assert "new@example.com" not in diagnostic
    if failure is not KeyboardInterrupt:
        assert exc.value.code not in (None, 0)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits required")
def test_bare_config_filename_does_not_change_working_directory_permissions(
    monkeypatch, config_file, tmp_path
):
    tmp_path.chmod(0o755)
    monkeypatch.chdir(tmp_path)

    cli._reset_config("config.ini")

    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o755
    assert stat.S_IMODE((tmp_path / "config.ini").stat().st_mode) == 0o600


def test_successful_reset_preserves_prompt_values_and_database(
    monkeypatch, config_file
):
    config_file.parent.mkdir()
    config_file.write_text("[DEFAULT]\nemail=old@example.com\n")
    database = config_file.parent / "qobuz_dl.db"
    database.write_bytes(b"existing duplicate tracking state")
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", "--reset"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code in (None, 0)
    config = configparser.ConfigParser()
    config.read(config_file)
    values = config["DEFAULT"]
    assert values["email"] == "new@example.com"
    assert values["password"] == "5f4dcc3b5aa765d61d8327deb882cf99"
    assert values["default_folder"] == "My Music"
    assert values["default_quality"] == "27"
    assert values["app_id"] == "987654321"
    assert values["secrets"] == "new-secret-one,new-secret-two"
    assert database.read_bytes() == b"existing duplicate tracking state"
