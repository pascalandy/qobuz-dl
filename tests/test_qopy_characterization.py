import hashlib
import json
import traceback

import pytest

from qobuz_dl.color import GREEN
from qobuz_dl.exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
)
from qobuz_dl.http import HttpResponse, HttpStatusError
from qobuz_dl.qopy import Client


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"ok": True}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("raise_for_status should not hide mapped errors")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.headers = {}

    def get(self, url, params=None):
        self.calls.append((url, params))
        return self.response


def make_client(session):
    client = Client.__new__(Client)
    client.id = "123456789"
    client.base = "https://www.qobuz.com/api.json/0.2/"
    client.session = session
    client.sec = "secret"
    client.uat = "user-token"
    return client


def make_auth_client(response):
    session = FakeSession(response)
    session.headers = {"X-App-Id": "123456789"}
    client = Client.__new__(Client)
    client.id = "123456789"
    client.base = "https://www.qobuz.com/api.json/0.2/"
    client.session = session
    client.sec = None
    return client


def response(status_code, payload):
    if isinstance(payload, bytes):
        content = payload
    else:
        content = json.dumps(payload).encode()
    return HttpResponse(status_code=status_code, headers={}, content=content)


def assert_auth_state_unmodified(client):
    assert not hasattr(client, "uat")
    assert not hasattr(client, "label")
    assert client.session.headers == {"X-App-Id": "123456789"}


def test_api_call_success_uses_expected_endpoint_and_params():
    session = FakeSession(FakeResponse(payload={"track": {"id": "track-1"}}))
    client = make_client(session)

    assert client.api_call("track/get", id="track-1") == {"track": {"id": "track-1"}}

    assert session.calls == [
        (
            "https://www.qobuz.com/api.json/0.2/track/get",
            {"track_id": "track-1"},
        )
    ]


@pytest.mark.parametrize(
    ("endpoint", "kwargs", "expected_params"),
    [
        (
            "user/login",
            {"email": "user@example.com", "pwd": "password"},
            {
                "email": "user@example.com",
                "password": "password",
                "app_id": "123456789",
            },
        ),
        ("album/get", {"id": "album-1"}, {"album_id": "album-1"}),
        (
            "playlist/get",
            {"id": "playlist-1", "offset": 500},
            {
                "extra": "tracks",
                "playlist_id": "playlist-1",
                "limit": 500,
                "offset": 500,
            },
        ),
        (
            "artist/get",
            {"id": "artist-1", "offset": 1000},
            {
                "app_id": "123456789",
                "artist_id": "artist-1",
                "limit": 500,
                "offset": 1000,
                "extra": "albums",
            },
        ),
        (
            "label/get",
            {"id": "label-1", "offset": 1500},
            {
                "label_id": "label-1",
                "limit": 500,
                "offset": 1500,
                "extra": "albums",
            },
        ),
        (
            "album/search",
            {"query": "alpha beta", "limit": 3},
            {"query": "alpha beta", "limit": 3},
        ),
        (
            "artist/search",
            {"query": "alpha beta", "limit": 3},
            {"query": "alpha beta", "limit": 3},
        ),
        (
            "playlist/search",
            {"query": "alpha beta", "limit": 3},
            {"query": "alpha beta", "limit": 3},
        ),
        (
            "track/search",
            {"query": "alpha beta", "limit": 3},
            {"query": "alpha beta", "limit": 3},
        ),
        ("playlist/getUserPlaylists", {"limit": 25}, {"limit": 25}),
    ],
)
def test_api_call_endpoint_param_shapes(endpoint, kwargs, expected_params):
    session = FakeSession(FakeResponse(payload={"ok": True}))
    client = make_client(session)

    assert client.api_call(endpoint, **kwargs) == {"ok": True}

    assert session.calls == [
        ("https://www.qobuz.com/api.json/0.2/" + endpoint, expected_params)
    ]


def test_login_status_mapping_for_invalid_credentials_and_app_id():
    with pytest.raises(AuthenticationError, match="Invalid credentials") as exc:
        make_client(FakeSession(FakeResponse(status_code=401))).api_call(
            "user/login", email="bad@example.com", pwd="bad"
        )
    assert (
        "Reset your credentials with 'uvx --from "
        "git+https://github.com/pascalandy/qobuz-dl.git qobuz-dl -r'" in str(exc.value)
    )

    with pytest.raises(InvalidAppIdError, match="Invalid app id"):
        make_client(FakeSession(FakeResponse(status_code=400))).api_call(
            "user/login", email="ok@example.com", pwd="ok"
        )


@pytest.mark.parametrize("status_code", [429, 500])
def test_login_unmapped_http_failure_retains_response_without_success_or_state(
    status_code, caplog
):
    secret_body = b'{"message":"signed-url-secret"}'
    client = make_auth_client(response(status_code, secret_body))

    with caplog.at_level("INFO", logger="qobuz_dl.qopy"):
        with pytest.raises(HttpStatusError) as exc_info:
            client.auth("user@example.com", "password-secret")

    assert exc_info.value.status_code == status_code
    assert exc_info.value.body == secret_body
    assert "Logged: OK" not in caplog.text
    assert_auth_state_unmodified(client)


@pytest.mark.parametrize(
    ("status_code", "error_type", "expected_message"),
    [
        (400, InvalidAppIdError, "Invalid app id."),
        (401, AuthenticationError, "Invalid credentials."),
    ],
)
def test_login_mapped_errors_are_distinct_and_do_not_reflect_response_secrets(
    status_code, error_type, expected_message, caplog
):
    sentinel = "login-token-and-password-sentinel"
    client = make_auth_client(response(status_code, {"message": sentinel}))

    with caplog.at_level("INFO", logger="qobuz_dl.qopy"):
        with pytest.raises(error_type) as exc_info:
            client.auth("user@example.com", "password-secret")

    rendered_traceback = "".join(
        traceback.format_exception(exc_info.type, exc_info.value, exc_info.tb)
    )
    assert str(exc_info.value).startswith(expected_message)
    assert sentinel not in str(exc_info.value)
    assert sentinel not in rendered_traceback
    assert sentinel not in caplog.text
    assert "Logged: OK" not in caplog.text
    assert_auth_state_unmodified(client)


@pytest.mark.parametrize(
    ("endpoint", "kwargs"),
    [
        ("track/getFileUrl", {"id": "5966783", "fmt_id": 5, "sec": "bad"}),
        (
            "favorite/getUserFavorites",
            {"type": "albums", "offset": 0, "limit": 50, "sec": "bad"},
        ),
    ],
)
@pytest.mark.parametrize(
    "body",
    [
        b'{"message":"signed-url-secret-sentinel"}',
        b"signed-url-secret-sentinel is not JSON",
    ],
)
def test_app_secret_mappings_never_parse_or_reflect_response_body(
    endpoint, kwargs, body, caplog
):
    client = make_client(FakeSession(response(400, body)))

    with caplog.at_level("INFO", logger="qobuz_dl.qopy"):
        with pytest.raises(InvalidAppSecretError) as exc_info:
            client.api_call(endpoint, **kwargs)

    rendered_traceback = "".join(
        traceback.format_exception(exc_info.type, exc_info.value, exc_info.tb)
    )
    assert str(exc_info.value).startswith("Invalid app secret.")
    assert "signed-url-secret-sentinel" not in str(exc_info.value)
    assert "signed-url-secret-sentinel" not in rendered_traceback
    assert "signed-url-secret-sentinel" not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"user": "malformed-user-sentinel", "user_auth_token": "token-sentinel"},
        {
            "user": {"credential": {"parameters": []}},
            "user_auth_token": "token-sentinel",
        },
        {
            "user": {"credential": {"parameters": {"short_label": "Studio"}}},
            "user_auth_token": "",
        },
        {
            "user": {"credential": {"parameters": {"short_label": "Studio"}}},
            "user_auth_token": 123,
        },
        {
            "user": {"credential": {"parameters": {"other": "label-sentinel"}}},
            "user_auth_token": "token-sentinel",
        },
        {
            "user": {"credential": {"parameters": {"short_label": None}}},
            "user_auth_token": "token-sentinel",
        },
    ],
)
def test_malformed_login_payload_is_fixed_error_without_partial_state_or_secrets(
    payload, caplog
):
    client = make_auth_client(response(200, payload))

    with caplog.at_level("INFO", logger="qobuz_dl.qopy"):
        with pytest.raises(AuthenticationError) as exc_info:
            client.auth("user@example.com", "password-secret")

    rendered_traceback = "".join(
        traceback.format_exception(exc_info.type, exc_info.value, exc_info.tb)
    )
    assert str(exc_info.value) == "Invalid login response."
    assert "sentinel" not in rendered_traceback
    assert "sentinel" not in caplog.text
    assert "Logged: OK" not in caplog.text
    assert_auth_state_unmodified(client)


def test_malformed_login_json_is_fixed_error_without_exception_chain_or_state(caplog):
    sentinel = "unterminated-secret-sentinel"
    client = make_auth_client(response(200, ('{"' + sentinel).encode()))

    with caplog.at_level("INFO", logger="qobuz_dl.qopy"):
        with pytest.raises(AuthenticationError) as exc_info:
            client.auth("user@example.com", "password-secret")

    rendered_traceback = "".join(
        traceback.format_exception(exc_info.type, exc_info.value, exc_info.tb)
    )
    assert str(exc_info.value) == "Invalid login response."
    assert sentinel not in rendered_traceback
    assert "JSONDecodeError" not in rendered_traceback
    assert "Logged: OK" not in caplog.text
    assert_auth_state_unmodified(client)


@pytest.mark.parametrize("parameters", [None, {}])
def test_recognized_free_account_login_remains_ineligible(parameters, caplog):
    client = make_auth_client(
        response(200, {"user": {"credential": {"parameters": parameters}}})
    )

    with caplog.at_level("INFO", logger="qobuz_dl.qopy"):
        with pytest.raises(
            IneligibleError, match="Free accounts are not eligible to download tracks"
        ):
            client.auth("user@example.com", "password-secret")

    assert "Logged: OK" not in caplog.text
    assert_auth_state_unmodified(client)


def test_valid_auth_installs_state_before_one_fixed_success_log(monkeypatch):
    hostile_label = "Studio hostile-label-sentinel"
    client = make_auth_client(
        response(
            200,
            {
                "user": {"credential": {"parameters": {"short_label": hostile_label}}},
                "user_auth_token": "token-123",
            },
        )
    )
    observed_logs = []

    def observe_log(message):
        observed_logs.append(
            (
                message,
                client.uat,
                client.session.headers.get("X-User-Auth-Token"),
                client.label,
            )
        )

    monkeypatch.setattr("qobuz_dl.qopy.logger.info", observe_log)

    client.auth("user@example.com", "password-secret")

    assert observed_logs == [
        (f"{GREEN}Logged: OK", "token-123", "token-123", hostile_label)
    ]
    assert hostile_label not in observed_logs[0][0]


def test_track_file_url_invalid_app_secret_mapping(monkeypatch):
    session = FakeSession(
        FakeResponse(status_code=400, payload={"message": "bad secret"})
    )
    client = make_client(session)
    fixed_time = 1712345678.25
    monkeypatch.setattr("qobuz_dl.qopy.time.time", lambda: fixed_time)

    with pytest.raises(InvalidAppSecretError, match="Invalid app secret"):
        client.api_call("track/getFileUrl", id="5966783", fmt_id=5, sec="bad")

    expected_sig_payload = (
        f"trackgetFileUrlformat_id5intentstreamtrack_id5966783{fixed_time}bad"
    )
    expected_sig = hashlib.md5(expected_sig_payload.encode("utf-8")).hexdigest()

    assert session.calls[0][0].endswith("track/getFileUrl")
    assert session.calls[0][1] == {
        "request_ts": fixed_time,
        "request_sig": expected_sig,
        "track_id": "5966783",
        "format_id": 5,
        "intent": "stream",
    }


def test_track_file_url_invalid_quality_rejected_before_http_call():
    session = FakeSession(FakeResponse())
    client = make_client(session)

    with pytest.raises(InvalidQuality, match="Invalid quality id"):
        client.api_call("track/getFileUrl", id="track-1", fmt_id=999)

    assert session.calls == []


@pytest.mark.parametrize(
    ("method_name", "favorite_type"),
    [
        ("get_favorite_albums", "albums"),
        ("get_favorite_tracks", "tracks"),
        ("get_favorite_artists", "artists"),
    ],
)
def test_favorite_wrappers_preserve_type_offset_and_limit(
    method_name, favorite_type, monkeypatch
):
    session = FakeSession(FakeResponse(payload={"items": []}))
    client = make_client(session)
    fixed_time = 1712345678.25
    monkeypatch.setattr("qobuz_dl.qopy.time.time", lambda: fixed_time)

    assert getattr(client, method_name)(offset=50, limit=25) == {"items": []}

    expected_sig_payload = f"favoritegetUserFavorites{fixed_time}secret"
    expected_sig = hashlib.md5(expected_sig_payload.encode("utf-8")).hexdigest()
    assert session.calls == [
        (
            "https://www.qobuz.com/api.json/0.2/favorite/getUserFavorites",
            {
                "app_id": "123456789",
                "user_auth_token": "user-token",
                "type": favorite_type,
                "offset": 50,
                "limit": 25,
                "request_ts": fixed_time,
                "request_sig": expected_sig,
            },
        )
    ]


def test_favorite_request_signing_accepts_secret_override(monkeypatch):
    session = FakeSession(FakeResponse(payload={"items": []}))
    client = make_client(session)
    fixed_time = 1712345678.25
    monkeypatch.setattr("qobuz_dl.qopy.time.time", lambda: fixed_time)

    assert client.api_call(
        "favorite/getUserFavorites",
        type="albums",
        offset=0,
        limit=50,
        sec="override",
    ) == {"items": []}

    expected_sig_payload = f"favoritegetUserFavorites{fixed_time}override"
    expected_sig = hashlib.md5(expected_sig_payload.encode("utf-8")).hexdigest()
    assert session.calls == [
        (
            "https://www.qobuz.com/api.json/0.2/favorite/getUserFavorites",
            {
                "app_id": "123456789",
                "user_auth_token": "user-token",
                "type": "albums",
                "offset": 0,
                "limit": 50,
                "request_ts": fixed_time,
                "request_sig": expected_sig,
            },
        )
    ]


def test_client_init_updates_required_headers_when_auth_and_secret_tests_are_faked(
    monkeypatch,
):
    captured_sessions = []

    class HeaderSession:
        def __init__(self):
            self.headers = {}
            captured_sessions.append(self)

        def get(self, url, params=None):
            return FakeResponse(
                payload={
                    "user": {"credential": {"parameters": {"short_label": "Studio"}}},
                    "user_auth_token": "token-123",
                }
            )

    monkeypatch.setattr("qobuz_dl.qopy.HttpClient", HeaderSession)
    monkeypatch.setattr(Client, "cfg_setup", lambda self: setattr(self, "sec", "ok"))

    client = Client("user@example.com", "password", "123456789", ["secret"])

    assert client.session is captured_sessions[0]
    assert client.session.headers["X-App-Id"] == "123456789"
    assert client.session.headers["Content-Type"] == "application/json;charset=UTF-8"
    assert client.session.headers["X-User-Auth-Token"] == "token-123"
    assert client.label == "Studio"


def test_client_init_can_scope_secret_probe_to_an_authorized_track(monkeypatch):
    captured_sessions = []

    class AuthorizedTrackSession:
        def __init__(self):
            self.headers = {}
            self.calls = []
            captured_sessions.append(self)

        def get(self, url, params=None):
            self.calls.append((url, params))
            if url.endswith("user/login"):
                return FakeResponse(
                    payload={
                        "user": {
                            "credential": {"parameters": {"short_label": "Studio"}}
                        },
                        "user_auth_token": "token-123",
                    }
                )
            return FakeResponse(payload={"url": "https://media.example.test/track"})

    monkeypatch.setattr("qobuz_dl.qopy.HttpClient", AuthorizedTrackSession)

    Client(
        "user@example.com",
        "password",
        "123456789",
        ["secret"],
        secret_test_track_id="authorized-track-id",
    )

    assert captured_sessions[0].calls[1][1]["track_id"] == "authorized-track-id"
