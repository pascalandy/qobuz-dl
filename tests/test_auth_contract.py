import configparser
import json
import socket
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

import qobuz_dl.cli as cli
from qobuz_dl import http, qopy
from qobuz_dl.core import QobuzDL

CLI_PLAINTEXT = "fixture-Pässword-37"
CLI_DIGEST = "42b2ae8f56097a52b02739e7110bd799"
LIBRARY_DIGEST = "570e2b95ddcc02d8d237f17fad12a2be"
FIXED_TIME = 1712345678.25
SYNTHETIC_TOKEN = "synthetic-user-token"


class FakeResponse:
    def __init__(self, payload):
        self.status = 200
        self.headers = {}
        self.content = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.content


def _install_fake_http(monkeypatch):
    requests = []

    def reject_socket(*args, **kwargs):
        pytest.fail("credential characterization must not open sockets")

    def fake_urlopen(request, timeout):
        parsed = urlsplit(request.full_url)
        requests.append(
            {
                "method": request.get_method(),
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "headers": {
                    key.lower(): value for key, value in request.header_items()
                },
            }
        )
        if parsed.path.endswith("/user/login"):
            payload = {
                "user": {"credential": {"parameters": {"short_label": "Synthetic"}}},
                "user_auth_token": SYNTHETIC_TOKEN,
            }
        elif parsed.path.endswith("/favorite/getUserFavorites"):
            payload = {"items": []}
        else:
            payload = {}
        return FakeResponse(payload)

    monkeypatch.setattr(socket, "socket", reject_socket)
    monkeypatch.setattr(http, "urlopen", fake_urlopen)
    monkeypatch.setattr(qopy.time, "time", lambda: FIXED_TIME)
    return requests


def _request_for(requests, endpoint):
    return next(
        request for request in requests if request["path"].endswith(f"/{endpoint}")
    )


def _assert_login_and_favorites_contract(requests, *, email, password_digest, app_id):
    login = _request_for(requests, "user/login")
    assert login == {
        "method": "GET",
        "path": "/api.json/0.2/user/login",
        "query": {
            "email": [email],
            "password": [password_digest],
            "app_id": [app_id],
        },
        "headers": {
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) "
                "Gecko/20100101 Firefox/83.0"
            ),
            "x-app-id": app_id,
            "content-type": "application/json;charset=UTF-8",
        },
    }

    favorite = _request_for(requests, "favorite/getUserFavorites")
    assert favorite["method"] == "GET"
    assert favorite["query"] == {
        "app_id": [app_id],
        "user_auth_token": [SYNTHETIC_TOKEN],
        "type": ["albums"],
        "offset": ["0"],
        "limit": ["1"],
        "request_ts": [str(FIXED_TIME)],
        "request_sig": ["daa077b6d62af3cdb48078b744c502a6"],
    }
    assert favorite["headers"]["x-user-auth-token"] == SYNTHETIC_TOKEN


def test_cli_setup_persists_one_utf8_md5_and_forwards_it_unchanged(
    monkeypatch, tmp_path, capsys
):
    config_file = tmp_path / "qobuz-dl" / "config.ini"
    database_file = config_file.parent / "qobuz_dl.db"
    answers = iter(["cli@example.invalid", "Synthetic Music", "6"])

    class FakeBundle:
        def get_app_id(self):
            return "123456789"

        def get_secrets(self):
            return {"fixture": "synthetic-api-secret"}

    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: CLI_PLAINTEXT)
    monkeypatch.setattr(cli, "Bundle", FakeBundle)
    requests = _install_fake_http(monkeypatch)

    cli._reset_config(str(config_file))

    persisted = configparser.ConfigParser()
    persisted.read(config_file, encoding="utf-8")
    assert persisted["DEFAULT"]["password"] == CLI_DIGEST
    assert CLI_PLAINTEXT not in config_file.read_text(encoding="utf-8")

    initialized_passwords = []
    clients = []
    original_initialize_client = QobuzDL.initialize_client

    def initialize_client(self, email, pwd, app_id, secrets):
        initialized_passwords.append(pwd)
        original_initialize_client(self, email, pwd, app_id, secrets)

    def exercise_favorites(qobuz, arguments):
        clients.append(qobuz.client)
        assert qobuz.client.get_favorite_albums(offset=0, limit=1) == {"items": []}

    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(database_file)),
    )
    monkeypatch.setattr(QobuzDL, "initialize_client", initialize_client)
    monkeypatch.setattr(cli, "_handle_commands", exercise_favorites)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/synthetic",
            "--no-db",
        ],
    )

    cli.main()

    assert initialized_passwords == [CLI_DIGEST]
    assert clients[0].session.headers["X-User-Auth-Token"] == SYNTHETIC_TOKEN
    _assert_login_and_favorites_contract(
        requests,
        email="cli@example.invalid",
        password_digest=CLI_DIGEST,
        app_id="123456789",
    )
    output = capsys.readouterr()
    assert CLI_PLAINTEXT not in output.out
    assert CLI_PLAINTEXT not in output.err


def test_documented_library_digest_reaches_login_and_authenticated_favorites(
    monkeypatch, tmp_path
):
    requests = _install_fake_http(monkeypatch)
    qobuz = QobuzDL(directory=tmp_path)

    qobuz.initialize_client(
        "library@example.invalid",
        LIBRARY_DIGEST,
        "123456789",
        ["synthetic-api-secret"],
    )
    assert qobuz.client.get_favorite_albums(offset=0, limit=1) == {"items": []}

    assert qobuz.client.session.headers["X-User-Auth-Token"] == SYNTHETIC_TOKEN
    _assert_login_and_favorites_contract(
        requests,
        email="library@example.invalid",
        password_digest=LIBRARY_DIGEST,
        app_id="123456789",
    )
