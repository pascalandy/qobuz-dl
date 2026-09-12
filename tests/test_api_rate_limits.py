import hashlib
import sys
from datetime import datetime, timezone
from email.message import Message
from email.utils import format_datetime
from io import BytesIO
from urllib.error import HTTPError

import pytest

import qobuz_dl.cli as cli
from qobuz_dl import http
from qobuz_dl.core import QobuzDL, _CollectionDownloadPlan
from qobuz_dl.exceptions import ApiRateLimitError
from qobuz_dl.http import HttpRateLimitError, HttpRequestError, HttpResponse
from qobuz_dl.qopy import Client


class FakeClock:
    def __init__(self, wall_time=1_700_000_000.0):
        self.wall = wall_time
        self.sleeps = []

    def wall_time(self):
        return self.wall

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.wall += seconds


class SequenceOperation:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return next(self.responses)


class SequenceSession:
    def __init__(self, *outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None):
        self.calls.append((url, params))
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(status_code=200, *, headers=None, header_items=None, body=b"{}"):
    return HttpResponse(
        status_code,
        headers or {},
        body,
        tuple(header_items or ()),
    )


def make_client(session):
    client = Client.__new__(Client)
    client.id = "123456789"
    client.base = "https://www.qobuz.com/api.json/0.2/"
    client.session = session
    client.sec = "secret"
    client.uat = "user-token"
    return client


def run_with_clock(operation, clock):
    return http.retry_rate_limited(
        operation,
        wall_time=clock.wall_time,
        sleeper=clock.sleep,
    )


def test_retry_after_seconds_is_case_insensitive():
    clock = FakeClock()
    operation = SequenceOperation(
        response(429, headers={"rEtRy-AfTeR": " 2 "}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert operation.calls == 2
    assert clock.sleeps == [2]


def test_retry_after_http_date_uses_the_controlled_wall_clock():
    clock = FakeClock()
    retry_at = datetime.fromtimestamp(clock.wall + 7, timezone.utc)
    operation = SequenceOperation(
        response(429, headers={"Retry-After": format_datetime(retry_at, usegmt=True)}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert clock.sleeps == [7]


def test_obsolete_asctime_retry_after_uses_utc():
    clock = FakeClock()
    retry_at = datetime.fromtimestamp(clock.wall + 7, timezone.utc)
    asctime = retry_at.strftime("%a %b %d %H:%M:%S %Y").replace(" 0", "  ")
    operation = SequenceOperation(
        response(429, headers={"Retry-After": asctime}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert clock.sleeps == [7]


def test_obsolete_rfc850_retry_after_uses_utc():
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    clock = FakeClock(wall_time=now.timestamp())
    retry_at = datetime.fromtimestamp(clock.wall + 7, timezone.utc)
    rfc850 = retry_at.strftime("%A, %d-%b-%y %H:%M:%S GMT")
    operation = SequenceOperation(
        response(429, headers={"Retry-After": rfc850}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert clock.sleeps == [7]


def test_rfc850_two_digit_year_uses_the_fifty_year_rule():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    future = datetime(2076, 1, 1, tzinfo=timezone.utc)
    clock = FakeClock(wall_time=now.timestamp())
    retry_after = future.strftime("%A, %d-%b-76 %H:%M:%S GMT")
    operation = SequenceOperation(
        response(429, headers={"Retry-After": retry_after}),
        response(body=b'{"should_not": "run"}'),
    )

    with pytest.raises(HttpRateLimitError, match="API rate limit retry budget"):
        run_with_clock(operation, clock)

    assert operation.calls == 1
    assert clock.sleeps == []


def test_rfc850_date_over_fifty_years_ahead_uses_the_past_year():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    future = datetime(2076, 1, 2, tzinfo=timezone.utc)
    clock = FakeClock(wall_time=now.timestamp())
    retry_after = future.strftime("%A, %d-%b-76 %H:%M:%S GMT")
    operation = SequenceOperation(
        response(429, headers={"Retry-After": retry_after}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert operation.calls == 2
    assert clock.sleeps == [0]


@pytest.mark.parametrize("first_header", [{}, {"Retry-After": "1, 2"}])
def test_missing_or_invalid_retry_after_uses_one_then_two_seconds(first_header):
    clock = FakeClock()
    operation = SequenceOperation(
        response(429, headers=first_header),
        response(429, headers={}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert operation.calls == 3
    assert clock.sleeps == [1, 2]


@pytest.mark.parametrize(
    "invalid_date",
    [
        "Sun, 06 Nov 1994 08:49:37 GMT trailing",
        "Sun, 06 Nov 1994 08:49:37 +0000",
        "Sun, 06 Nov 1994 08:49:37",
    ],
)
def test_non_http_dates_use_the_fallback_wait(invalid_date):
    clock = FakeClock()
    operation = SequenceOperation(
        response(429, headers={"Retry-After": invalid_date}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert clock.sleeps == [1]


def test_duplicate_retry_after_lines_are_ambiguous_and_use_the_fallback():
    clock = FakeClock()
    operation = SequenceOperation(
        response(
            429,
            headers={"Retry-After": "30"},
            header_items=(("Retry-After", "30"), ("retry-after", "0")),
        ),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert clock.sleeps == [1]


def test_retry_wait_above_remaining_budget_stops_without_another_request():
    clock = FakeClock()
    operation = SequenceOperation(
        response(429, headers={"Retry-After": "20"}),
        response(429, headers={"Retry-After": "11"}),
        response(body=b'{"should_not": "run"}'),
    )

    with pytest.raises(HttpRateLimitError, match="API rate limit retry budget"):
        run_with_clock(operation, clock)

    assert operation.calls == 2
    assert clock.sleeps == [20]


def test_retry_wait_equal_to_remaining_budget_is_allowed():
    clock = FakeClock()
    operation = SequenceOperation(
        response(429, headers={"Retry-After": "20"}),
        response(429, headers={"Retry-After": "10"}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert operation.calls == 3
    assert clock.sleeps == [20, 10]


def test_budget_counts_requested_sleep_instead_of_scheduler_oversleep():
    class OversleepingClock(FakeClock):
        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.wall += seconds + 1

    clock = OversleepingClock()
    operation = SequenceOperation(
        response(429, headers={"Retry-After": "20"}),
        response(429, headers={"Retry-After": "10"}),
        response(body=b'{"ok": true}'),
    )

    result = run_with_clock(operation, clock)

    assert result.json() == {"ok": True}
    assert operation.calls == 3
    assert clock.sleeps == [20, 10]


def test_three_rate_limited_responses_raise_a_sanitized_error():
    sentinel = "token-and-signature-sentinel"
    clock = FakeClock()
    operation = SequenceOperation(
        response(429, headers={"X-Secret": sentinel}, body=sentinel.encode()),
        response(429, body=sentinel.encode()),
        response(429, body=sentinel.encode()),
    )

    with pytest.raises(HttpRateLimitError) as exc_info:
        run_with_clock(operation, clock)

    assert str(exc_info.value) == "Qobuz API rate limit retry attempts exhausted."
    assert sentinel not in str(exc_info.value)
    assert operation.calls == 3
    assert clock.sleeps == [1, 2]


def test_keyboard_interrupt_during_wait_is_not_caught():
    operation = SequenceOperation(response(429, headers={"Retry-After": "1"}))

    with pytest.raises(KeyboardInterrupt):
        http.retry_rate_limited(
            operation,
            wall_time=lambda: 0.0,
            sleeper=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt),
        )

    assert operation.calls == 1


def test_safe_signed_request_rebuilds_timestamp_and_signature(monkeypatch):
    session = SequenceSession(
        response(429, headers={"Retry-After": "0"}),
        response(body=b'{"url": "https://media.example.test/track.flac"}'),
    )
    client = make_client(session)
    timestamps = iter([1_712_345_678.25, 1_712_345_679.25])
    monkeypatch.setattr("qobuz_dl.qopy.time.time", lambda: next(timestamps))

    result = client.api_call("track/getFileUrl", id="5966783", fmt_id=5)

    assert result == {"url": "https://media.example.test/track.flac"}
    assert len(session.calls) == 2
    first_params = session.calls[0][1]
    second_params = session.calls[1][1]
    assert first_params["track_id"] == second_params["track_id"] == "5966783"
    assert first_params["format_id"] == second_params["format_id"] == 5
    assert first_params["intent"] == second_params["intent"] == "stream"
    assert first_params["request_ts"] == 1_712_345_678.25
    assert second_params["request_ts"] == 1_712_345_679.25
    assert (
        first_params["request_sig"]
        == hashlib.md5(
            b"trackgetFileUrlformat_id5intentstreamtrack_id59667831712345678.25secret"
        ).hexdigest()
    )
    assert (
        second_params["request_sig"]
        == hashlib.md5(
            b"trackgetFileUrlformat_id5intentstreamtrack_id59667831712345679.25secret"
        ).hexdigest()
    )


@pytest.mark.parametrize(
    ("endpoint", "kwargs"),
    [
        ("album/get", {"id": "album-1"}),
        ("album/search", {"query": "alpha", "limit": 1}),
        ("artist/get", {"id": "artist-1", "offset": 0}),
        ("artist/search", {"query": "alpha", "limit": 1}),
        (
            "favorite/getUserFavorites",
            {"type": "albums", "offset": 0, "limit": 1},
        ),
        ("label/get", {"id": "label-1", "offset": 0}),
        ("playlist/get", {"id": "playlist-1", "offset": 0}),
        ("playlist/getUserPlaylists", {"limit": 1}),
        ("playlist/search", {"query": "alpha", "limit": 1}),
        ("track/get", {"id": "track-1"}),
        ("track/search", {"query": "alpha", "limit": 1}),
    ],
)
def test_known_read_endpoints_retry_once(endpoint, kwargs):
    session = SequenceSession(
        response(429, headers={"Retry-After": "0"}),
        response(body=b'{"ok": true}'),
    )
    client = make_client(session)

    assert client.api_call(endpoint, **kwargs) == {"ok": True}
    assert len(session.calls) == 2


@pytest.mark.parametrize(
    ("endpoint", "kwargs"),
    [
        ("user/login", {"email": "user@example.com", "pwd": "secret"}),
        ("catalog/unknown", {"query": "test"}),
    ],
)
def test_login_and_unknown_endpoints_do_not_retry(endpoint, kwargs):
    session = SequenceSession(
        response(429, headers={"Retry-After": "0"}),
        response(body=b'{"should_not": "run"}'),
    )
    client = make_client(session)

    with pytest.raises(http.HttpStatusError) as exc_info:
        client.api_call(endpoint, **kwargs)

    assert exc_info.value.status_code == 429
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "outcome",
    [
        response(500, body=b"server error"),
        HttpRequestError("transport failed"),
        response(body=b"not json"),
    ],
)
def test_non_429_transport_and_json_failures_do_not_retry(outcome):
    session = SequenceSession(outcome, response(body=b'{"should_not": "run"}'))
    client = make_client(session)

    with pytest.raises((http.HttpStatusError, HttpRequestError, ValueError)):
        client.api_call("track/get", id="track-1")

    assert len(session.calls) == 1


def test_http_status_error_retains_response_headers():
    api_response = response(
        503,
        headers={"Retry-After": "9", "X-Request-Id": "request-1"},
        body=b"service unavailable",
    )

    with pytest.raises(http.HttpStatusError) as exc_info:
        api_response.raise_for_status()

    assert exc_info.value.headers == {
        "Retry-After": "9",
        "X-Request-Id": "request-1",
    }


def test_http_error_response_is_closed_after_headers_and_body_are_copied(monkeypatch):
    class TrackedBody(BytesIO):
        def __init__(self):
            super().__init__(b"rate limited")
            self.was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    body = TrackedBody()
    headers = Message()
    headers["Retry-After"] = "1"
    headers["Retry-After"] = "2"

    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            headers,
            body,
        )

    monkeypatch.setattr(http, "urlopen", fake_urlopen)

    api_response = http.get("https://api.example.test/track/get")

    assert api_response.status_code == 429
    assert api_response.content == b"rate limited"
    assert api_response.headers == {"Retry-After": "2"}
    assert api_response.header_items == (
        ("Retry-After", "1"),
        ("Retry-After", "2"),
    )
    assert body.was_closed is True


def test_rate_limit_exhaustion_aborts_collection_before_next_item(tmp_path):
    class RateLimitedClient:
        def __init__(self):
            self.calls = []

        def get_album_meta(self, item_id):
            self.calls.append(item_id)
            raise ApiRateLimitError("Qobuz API rate limit retries exhausted.")

    client = RateLimitedClient()
    qdl = QobuzDL(directory=tmp_path, no_cover=True)
    qdl.client = client
    plan = _CollectionDownloadPlan(
        url_type="artist",
        collection_name="Artist",
        item_ids=("album-1", "album-2"),
        album=True,
    )

    with pytest.raises(ApiRateLimitError):
        qdl._execute_url_download_plan(plan)

    assert client.calls == ["album-1"]


def test_cfg_setup_stops_before_trying_the_next_secret_after_rate_limit():
    sentinel = "rate-limit-response-secret"
    session = SequenceSession(
        response(429, headers={"Retry-After": "0"}, body=sentinel.encode()),
        response(429, headers={"Retry-After": "0"}, body=sentinel.encode()),
        response(429, headers={"Retry-After": "0"}, body=sentinel.encode()),
        response(body=b'{"should_not": "run"}'),
    )
    client = make_client(session)
    client.secrets = ["first-secret", "second-secret"]
    client.sec = None

    with pytest.raises(ApiRateLimitError) as exc_info:
        client.cfg_setup()

    assert str(exc_info.value) == "Qobuz API rate limit retries exhausted."
    assert sentinel not in str(exc_info.value)
    assert len(session.calls) == 3


def test_cli_initialization_exits_with_sanitized_rate_limit_message(
    tmp_path, monkeypatch
):
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "email = user@example.com",
                "password = password-sentinel",
                "default_folder = Qobuz Downloads",
                "default_limit = 20",
                "default_quality = 6",
                "no_m3u = false",
                "albums_only = false",
                "no_fallback = false",
                "og_cover = false",
                "embed_art = false",
                "no_cover = false",
                "no_database = true",
                "app_id = 123456",
                "smart_discography = false",
                "folder_format = {albumartist} - {album}",
                "track_format = {tracknumber}. {tracktitle}",
                "secrets = app-secret-sentinel",
            ]
        )
    )

    class RateLimitedQobuzDL:
        def __init__(self, *args, **kwargs):
            pass

        def initialize_client(self, email, password, app_id, secrets):
            raise ApiRateLimitError("Qobuz API rate limit retries exhausted.")

    monkeypatch.setattr(
        sys,
        "argv",
        ["qobuz-dl", "dl", "https://play.qobuz.com/album/album-1"],
    )
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(tmp_path / "downloads.db")),
    )
    monkeypatch.setattr(cli, "QobuzDL", RateLimitedQobuzDL)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    message = str(exc_info.value)
    assert "Qobuz API rate limit retries exhausted." in message
    assert "password-sentinel" not in message
    assert "app-secret-sentinel" not in message


def test_media_download_remains_single_attempt_on_429(tmp_path, monkeypatch):
    calls = []

    class RawResponse:
        status = 429
        headers = {"Retry-After": "0"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def getcode(self):
            return self.status

        def read(self, _size=-1):
            return b"rate limited"

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return RawResponse()

    monkeypatch.setattr(http, "urlopen", fake_urlopen)
    target = tmp_path / "track.flac"

    with pytest.raises(http.HttpStatusError) as exc_info:
        http.stream_download("https://media.example.test/track.flac", target)

    assert exc_info.value.status_code == 429
    assert calls == [("https://media.example.test/track.flac", 30)]
    assert not target.exists()
