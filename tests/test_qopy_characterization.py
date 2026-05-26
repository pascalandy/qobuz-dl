import hashlib

import pytest

from qobuz_dl.exceptions import (
    AuthenticationError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
)
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


def test_login_status_mapping_for_invalid_credentials_and_app_id():
    with pytest.raises(AuthenticationError, match="Invalid credentials"):
        make_client(FakeSession(FakeResponse(status_code=401))).api_call(
            "user/login", email="bad@example.com", pwd="bad"
        )

    with pytest.raises(InvalidAppIdError, match="Invalid app id"):
        make_client(FakeSession(FakeResponse(status_code=400))).api_call(
            "user/login", email="ok@example.com", pwd="ok"
        )


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
