import configparser
import hashlib
import io
import json
import os
import stat
import sys

import pytest

import qobuz_dl.cli as cli
from qobuz_dl import bundle, downloader, http, qopy
from qobuz_dl.core import QobuzDL, Source

URL = "https://play.qobuz.com/album/abc1"
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def _write_config(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[DEFAULT]\nemail = user@example.com\npassword = hashed\n"
        "default_folder = Music\ndefault_limit = 20\ndefault_quality = 6\n"
        "no_m3u = false\nalbums_only = false\nno_fallback = false\n"
        "og_cover = false\nembed_art = false\nno_cover = false\n"
        "no_database = false\napp_id = 1\nsmart_discography = false\n"
        "folder_format = {album}\ntrack_format = {tracktitle}\nsecrets = s\n"
    )
    return path


@pytest.fixture
def home(monkeypatch, tmp_path):
    """A private home; on Windows, APPDATA points inside it too."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData"))
    return home


def _default_config(home):
    """Where the default lookup finds config on this platform."""
    if os.name == "nt":
        return home / "AppData" / "qobuz-dl" / "config.ini"
    return home / ".config" / "qobuz-dl" / "config.ini"


class FakeBundle:
    def get_app_id(self):
        return "123456789"

    def get_secrets(self):
        return {"america": "secret-one"}


class Runtime:
    def __init__(self, *args, **kwargs):
        pass

    def initialize_client(self, *args):
        pass

    def download_sources(self, sources):
        Runtime.sources = list(sources)
        return self.run_result


def _show_config(capsys, argv):
    assert cli.main([*argv, "--show-config", "--json"]) == 0
    return json.loads(capsys.readouterr().out)["data"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX lookup order")
def test_default_lookup_prefers_xdg_then_legacy_then_creates_at_xdg(
    monkeypatch, home, tmp_path
):
    xdg = tmp_path / "xdg"
    legacy = home / ".config" / "qobuz-dl" / "config.ini"
    xdg_config = xdg / "qobuz-dl" / "config.ini"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert cli._resolve_config_paths() == (
        str(xdg_config),
        str(xdg / "qobuz-dl" / "qobuz_dl.db"),
    )

    _write_config(legacy)
    assert cli._resolve_config_paths()[0] == str(legacy)

    _write_config(xdg_config)
    assert cli._resolve_config_paths()[0] == str(xdg_config)

    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")
    assert cli._resolve_config_paths()[0] == str(legacy)

    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert cli._resolve_config_paths() == (
        str(legacy),
        str(legacy.parent / "qobuz_dl.db"),
    )


def test_flag_beats_environment_beats_default(monkeypatch, home, tmp_path, capsys):
    default = _write_config(_default_config(home))
    from_env = _write_config(tmp_path / "env" / "config.ini")
    from_flag = _write_config(tmp_path / "flag" / "config.ini")

    assert _show_config(capsys, [])["config_path"] == str(default)

    monkeypatch.setenv("QOBUZ_DL_CONFIG", str(from_env))
    data = _show_config(capsys, [])
    assert data["config_path"] == str(from_env)
    assert data["database_path"] == str(from_env.parent / "qobuz_dl.db")

    data = _show_config(capsys, ["--config", str(from_flag)])
    assert data["config_path"] == str(from_flag)
    assert data["database_path"] == str(from_flag.parent / "qobuz_dl.db")


@pytest.mark.parametrize("source", ["flag", "environment"])
def test_missing_explicit_config_exits_2_and_never_touches_the_default(
    monkeypatch, home, tmp_path, capsys, terminal_stdin, source
):
    default = _write_config(_default_config(home))
    before = (default.read_bytes(), _mode(default), _mode(default.parent))
    missing = tmp_path / "missing" / "config.ini"
    argv = ["dl", URL]
    if source == "flag":
        argv += ["--config", str(missing)]
    else:
        monkeypatch.setenv("QOBUZ_DL_CONFIG", str(missing))
    monkeypatch.setattr(cli, "_reset_config", lambda *a, **k: pytest.fail("setup"))

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert capsys.readouterr().err.endswith(
        f"qobuz-dl: error: no config file at {missing}; create it: "
        f"qobuz-dl --reset --config {missing}\nrun 'qobuz-dl --help' for usage\n"
    )
    assert (default.read_bytes(), _mode(default), _mode(default.parent)) == before
    assert not missing.parent.exists()


def test_config_dash_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", "-", "dl", URL])

    assert exc.value.code == 2
    assert "--config needs a file path" in capsys.readouterr().err


def _password_file(tmp_path, text="plain password\n"):
    path = tmp_path / "password.txt"
    path.write_text(text)
    return path


@posix_only
def test_unattended_reset_writes_a_private_config_with_defaults(
    monkeypatch, home, tmp_path, capsys
):
    monkeypatch.setattr(cli, "Bundle", FakeBundle)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("prompted"))
    config = home / ".config" / "qobuz-dl" / "config.ini"

    code = cli.main(
        [
            "--reset",
            "--email",
            "me@example.com",
            "--password-file",
            str(_password_file(tmp_path)),
        ]
    )

    assert code == 0
    assert capsys.readouterr() == ("", "")
    assert _mode(config) == 0o600
    assert _mode(config.parent) == 0o700
    values = configparser.ConfigParser()
    values.read(config)
    assert values["DEFAULT"]["email"] == "me@example.com"
    assert values["DEFAULT"]["password"] == hashlib.md5(b"plain password").hexdigest()
    assert values["DEFAULT"]["default_folder"] == "Qobuz Downloads"
    assert values["DEFAULT"]["default_quality"] == "6"
    assert "plain password" not in config.read_text()


def test_unattended_reset_reads_the_password_from_stdin_and_reports_json(
    monkeypatch, home, tmp_path, capsys
):
    monkeypatch.setattr(cli, "Bundle", FakeBundle)
    monkeypatch.setattr(sys, "stdin", io.StringIO("from stdin\n"))
    config = tmp_path / "chosen" / "config.ini"

    code = cli.main(
        [
            "--reset",
            "--config",
            str(config),
            "--email",
            "me@example.com",
            "--password-file",
            "-",
            "--json",
        ]
    )

    assert code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["operation"] == "reset"
    assert document["status"] == "ok"
    assert document["data"] == {"config_path": str(config), "created": True}
    values = configparser.ConfigParser()
    values.read(config)
    assert values["DEFAULT"]["password"] == hashlib.md5(b"from stdin").hexdigest()
    assert not (home / ".config").exists()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--reset"], "--reset without a terminal needs --email and --password-file"),
        (
            ["--reset", "--email", "a@b.c"],
            "--reset without a terminal needs --password-file",
        ),
        (
            ["--reset", "--password-file", "p"],
            "--reset without a terminal needs --email",
        ),
        (
            ["--email", "a@b.c", "dl", URL],
            "--email and --password-file work only with --reset",
        ),
        (["--password-file", "p", "--purge"], "work only with --reset"),
    ],
)
def test_setup_flags_are_checked_before_any_work(monkeypatch, capsys, argv, message):
    monkeypatch.setattr(cli, "_reset_config", lambda *a, **k: pytest.fail("setup"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("content", [None, "\nsecond line\n"])
def test_unreadable_password_file_is_a_usage_error(
    monkeypatch, home, tmp_path, capsys, content
):
    monkeypatch.setattr(cli, "Bundle", FakeBundle)
    password = tmp_path / "password.txt"
    if content is not None:
        password.write_text(content)

    with pytest.raises(SystemExit) as exc:
        cli.main(["--reset", "--email", "a@b.c", "--password-file", str(password)])

    assert exc.value.code == 2
    assert "--password-file" in capsys.readouterr().err
    assert not _default_config(home).exists()


@posix_only
def test_reset_with_explicit_config_never_touches_the_default(
    monkeypatch, home, tmp_path
):
    monkeypatch.setattr(cli, "Bundle", FakeBundle)
    default = _write_config(home / ".config" / "qobuz-dl" / "config.ini")
    default.chmod(0o644)
    default.parent.chmod(0o755)
    before = (default.read_bytes(), _mode(default), _mode(default.parent))
    chosen = tmp_path / "chosen.ini"

    code = cli.main(
        [
            "--reset",
            "--config",
            str(chosen),
            "--email",
            "me@example.com",
            "--password-file",
            str(_password_file(tmp_path)),
        ]
    )

    assert code == 0
    assert (default.read_bytes(), _mode(default), _mode(default.parent)) == before
    assert _mode(chosen) == 0o600


@posix_only
@pytest.mark.parametrize(
    ("explicit", "folder_exists", "folder_mode"),
    [
        (False, False, 0o700),
        (False, True, 0o700),
        (True, True, 0o755),
        (True, False, 0o700),
    ],
    ids=[
        "default-new-folder",
        "default-existing-folder-hardened",
        "explicit-existing-folder-kept",
        "explicit-new-folder",
    ],
)
def test_permission_matrix(
    monkeypatch, home, tmp_path, explicit, folder_exists, folder_mode
):
    monkeypatch.setattr(cli, "Bundle", FakeBundle)
    folder = tmp_path / "user-folder" if explicit else home / ".config" / "qobuz-dl"
    if folder_exists:
        folder.mkdir(parents=True)
        folder.chmod(0o755)
    config = folder / "config.ini"
    argv = [
        "--reset",
        "--email",
        "me@example.com",
        "--password-file",
        str(_password_file(tmp_path)),
    ]
    if explicit:
        argv += ["--config", str(config)]

    assert cli.main(argv) == 0

    assert _mode(config) == 0o600
    assert _mode(folder) == folder_mode


@posix_only
def test_startup_does_not_chmod_the_folder_of_an_explicit_config(monkeypatch, tmp_path):
    folder = tmp_path / "shared"
    config = _write_config(folder / "config.ini")
    config.chmod(0o644)
    folder.chmod(0o755)
    monkeypatch.setattr(cli, "QobuzDL", Runtime)

    assert cli.main(["dl", URL, "--config", str(config)]) == 0

    assert _mode(config) == 0o600
    assert _mode(folder) == 0o755


class _TimeoutSpy:
    def __init__(self, responses):
        self.calls = []
        self.responses = responses

    def __call__(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        for prefix, body in self.responses:
            if request.full_url.startswith(prefix):
                return _Response(body)
        return _Response(b"{}")


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body
        self.headers = {"content-length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        body, self.body = self.body, b""
        return body


LOGIN = json.dumps(
    {
        "user": {"credential": {"parameters": {"short_label": "x"}}},
        "user_auth_token": "t",
    }
).encode()
BUNDLE_PAGE = b'<script src="/resources/1.2.3-a123/bundle.js"></script>'


def test_each_http_entry_point_uses_the_run_timeout(monkeypatch, tmp_path):
    spy = _TimeoutSpy(
        [
            ("https://www.qobuz.com/api.json/0.2/user/login", LOGIN),
            ("https://play.qobuz.com/login", BUNDLE_PAGE),
            ("https://media.example.test/", b"audio"),
            ("https://www.last.fm/", b"<html></html>"),
        ]
    )
    monkeypatch.setattr(http, "urlopen", spy)

    with http.request_timeout(7):
        qopy.Client("a@b.c", "hash", "1", ["secret"], secret_test_track_id="1")
        bundle.Bundle()
        downloader.download_with_progress(
            "https://media.example.test/a.flac", tmp_path / "a.flac", "a"
        )
        qobuz = QobuzDL(directory=tmp_path / "music")
        qobuz.download_lastfm_pl("https://www.last.fm/user/x/playlists/1")

    kinds = {
        "api": "api.json",
        "bundle": "play.qobuz.com/",
        "media": "media.example.test",
        "lastfm": "last.fm",
    }
    for kind, marker in kinds.items():
        timeouts = {timeout for url, timeout in spy.calls if marker in url}
        assert timeouts == {7}, kind
    assert http.current_timeout() == http.DEFAULT_TIMEOUT


def test_cli_timeout_reaches_requests_and_is_restored(monkeypatch, tmp_path):
    config = _write_config(tmp_path / "config.ini")
    spy = _TimeoutSpy([("https://www.qobuz.com/api.json/0.2/user/login", LOGIN)])
    monkeypatch.setattr(http, "urlopen", spy)

    class LoggingIn(Runtime):
        def initialize_client(self, *args):
            qopy.Client(*args, secret_test_track_id="1")

    monkeypatch.setattr(cli, "QobuzDL", LoggingIn)

    assert cli.main(["--timeout", "2m", "dl", URL, "--config", str(config)]) == 0

    assert {timeout for _url, timeout in spy.calls} == {120}
    assert http.current_timeout() == http.DEFAULT_TIMEOUT


@pytest.mark.parametrize("value", ["0", "-1", "soon"])
def test_invalid_timeout_is_a_usage_error(capsys, value):
    with pytest.raises(SystemExit) as exc:
        cli.main(["dl", URL, f"--timeout={value}"])

    assert exc.value.code == 2
    assert "--timeout" in capsys.readouterr().err


def test_dl_reads_sources_from_stdin_with_locations(monkeypatch, tmp_path):
    config = _write_config(tmp_path / "config.ini")
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "# queued\n\nhttps://play.qobuz.com/track/7\n"
            "https://www.last.fm/user/x/playlists/2\n"
        ),
    )
    monkeypatch.setattr(cli, "QobuzDL", Runtime)

    code = cli.main(["dl", URL, "-", "--config", str(config)])

    assert code == 0
    assert Runtime.sources == [
        Source("qobuz", URL, None, "album", "abc1"),
        Source("qobuz", "https://play.qobuz.com/track/7", "<stdin>:3", "track", "7"),
        Source("lastfm", "https://www.last.fm/user/x/playlists/2", "<stdin>:4"),
    ]


@pytest.mark.parametrize(
    ("argv", "stdin", "message"),
    [
        (["dl", "-", "-"], "", "'-' may appear only once"),
        (["dl", "-"], "https://play.qobuz.com/track/1\nnope\n", "<stdin>:2: "),
    ],
)
def test_dl_stdin_errors_are_usage_errors(monkeypatch, capsys, argv, stdin, message):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err


def test_dl_stdin_with_missing_config_exits_2_even_in_a_terminal(
    monkeypatch, home, capsys
):
    class TerminalWithSources(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(
        sys, "stdin", TerminalWithSources("https://play.qobuz.com/track/1\n")
    )
    monkeypatch.setattr(cli, "_reset_config", lambda *a, **k: pytest.fail("setup"))

    with pytest.raises(SystemExit) as exc:
        cli.main(["dl", "-"])

    assert exc.value.code == 2
    assert "no config file at" in capsys.readouterr().err


def test_purge_with_a_missing_explicit_config_deletes_nothing(tmp_path, capsys):
    folder = tmp_path / "shared"
    folder.mkdir()
    database = folder / "qobuz_dl.db"
    database.write_bytes(b"someone else's history")
    typo = folder / "confg.ini"

    with pytest.raises(SystemExit) as exc:
        cli.main(["--purge", "--config", str(typo)])

    assert exc.value.code == 2
    assert f"no config file at {typo}" in capsys.readouterr().err
    assert database.read_bytes() == b"someone else's history"


def test_purge_with_an_explicit_config_deletes_the_database_beside_it(tmp_path):
    config = _write_config(tmp_path / "chosen" / "config.ini")
    database = config.parent / "qobuz_dl.db"
    database.write_bytes(b"history")

    assert cli.main(["--purge", "--config", str(config)]) == 0

    assert not database.exists()


@pytest.mark.parametrize("json_output", [False, True])
def test_retry_hints_never_repeat_the_email(
    monkeypatch, home, tmp_path, capsys, json_output
):
    def unavailable():
        raise http.HttpStatusError(503)

    monkeypatch.setattr(cli, "Bundle", unavailable)
    password = _password_file(tmp_path)
    argv = [
        "--reset",
        "--email",
        "private@example.test",
        "--password-file",
        str(password),
    ]

    code = cli.main([*argv, "--json"] if json_output else argv)

    assert code == 75
    output = capsys.readouterr()
    assert "private@example.test" not in output.out + output.err
    assert output.err.endswith(
        "retry with the same --email: "
        f"qobuz-dl --reset --password-file {password}"
        + (" --json" if json_output else "")
        + "\n"
    )
    if json_output:
        (problem,) = json.loads(output.out)["problems"]
        assert problem["hint"] == (
            f"qobuz-dl --reset --password-file {password} --json"
        )
