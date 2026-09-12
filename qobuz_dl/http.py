import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT = 30


class HttpError(Exception):
    """Base error raised by qobuz-dl's internal HTTP boundary."""


class HttpStatusError(HttpError):
    def __init__(
        self,
        status_code: int,
        body: bytes = b"",
        headers: Mapping[str, str] | None = None,
        header_items: tuple[tuple[str, str], ...] = (),
    ):
        super().__init__(f"HTTP status {status_code}")
        self.status_code = status_code
        self.body = body
        self.headers = dict(headers or {})
        self.header_items = header_items or tuple(self.headers.items())


class HttpRateLimitError(HttpError):
    pass


class HttpRequestError(HttpError):
    pass


@dataclass
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    header_items: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if not self.header_items:
            self.header_items = tuple(self.headers.items())

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HttpStatusError(
                self.status_code,
                self.content,
                self.headers,
                self.header_items,
            )


@dataclass(frozen=True)
class _RateLimitPolicy:
    max_attempts: int
    max_wait_seconds: float
    fallback_waits: tuple[float, ...]


_QOBUZ_RATE_LIMIT_POLICY = _RateLimitPolicy(
    max_attempts=3,
    max_wait_seconds=30,
    fallback_waits=(1, 2),
)

_SHORT_WEEKDAY = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
_LONG_WEEKDAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_TIME = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
_IMF_FIXDATE = re.compile(
    rf"{_SHORT_WEEKDAY}, [0-3][0-9] {_MONTH} [0-9]{{4}} {_TIME} GMT"
)
_RFC850_DATE = re.compile(
    rf"{_LONG_WEEKDAY}, [0-3][0-9]-{_MONTH}-([0-9]{{2}}) {_TIME} GMT"
)
_ASCTIME_DATE = re.compile(
    rf"{_SHORT_WEEKDAY} {_MONTH} (?: [1-9]|[0-3][0-9]) {_TIME} [0-9]{{4}}"
)


def _parse_http_date(value: str, now_seconds: float) -> datetime | None:
    rfc850_match = _RFC850_DATE.fullmatch(value)
    is_asctime = _ASCTIME_DATE.fullmatch(value) is not None
    if (
        _IMF_FIXDATE.fullmatch(value) is None
        and rfc850_match is None
        and not is_asctime
    ):
        return None

    try:
        parsed = parsedate_to_datetime(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if is_asctime:
        parsed = parsed.replace(tzinfo=timezone.utc)
    elif parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        return None

    if rfc850_match is not None:
        try:
            now = datetime.fromtimestamp(now_seconds, timezone.utc)
            year = now.year - now.year % 100 + int(rfc850_match.group(1))
            candidate = parsed.replace(year=year)
            try:
                cutoff = now.replace(year=now.year + 50)
            except ValueError:
                cutoff = now.replace(year=now.year + 50, day=28)
        except (OSError, OverflowError, ValueError):
            return None
        if candidate > cutoff:
            try:
                candidate = candidate.replace(year=year - 100)
            except ValueError:
                return None
        parsed = candidate

    return parsed


def _retry_after_seconds(
    header_items: tuple[tuple[str, str], ...], wall_time: Callable[[], float]
) -> float | None:
    values = [value for name, value in header_items if name.lower() == "retry-after"]
    if len(values) != 1 or not isinstance(values[0], str):
        return None

    value = values[0].strip()
    if value.isascii() and value.isdecimal():
        return float(value)

    now = wall_time()
    retry_at = _parse_http_date(value, now)
    if retry_at is None:
        return None
    try:
        return max(0.0, retry_at.timestamp() - now)
    except (OSError, OverflowError, ValueError):
        return None


def retry_rate_limited(
    operation: Callable[[], HttpResponse],
    *,
    wall_time: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> HttpResponse:
    wall_time = wall_time or time.time
    sleeper = sleeper or time.sleep
    waited = 0.0

    for attempt in range(_QOBUZ_RATE_LIMIT_POLICY.max_attempts):
        response = operation()
        if response.status_code != 429:
            return response
        if attempt == _QOBUZ_RATE_LIMIT_POLICY.max_attempts - 1:
            break

        delay = _retry_after_seconds(response.header_items, wall_time)
        if delay is None:
            delay = _QOBUZ_RATE_LIMIT_POLICY.fallback_waits[attempt]
        if delay > _QOBUZ_RATE_LIMIT_POLICY.max_wait_seconds - waited:
            raise HttpRateLimitError(
                "Qobuz API rate limit retry budget exhausted."
            ) from None

        sleeper(delay)
        waited += delay

    raise HttpRateLimitError("Qobuz API rate limit retry attempts exhausted.") from None


class HttpClient:
    def __init__(
        self, headers: Mapping[str, str] | None = None, timeout=DEFAULT_TIMEOUT
    ):
        self.headers = dict(headers or {})
        self.timeout = timeout

    def get(self, url: str, params: Mapping[str, object] | None = None) -> HttpResponse:
        return get(url, params=params, headers=self.headers, timeout=self.timeout)


def _url_with_params(url: str, params: Mapping[str, object] | None = None) -> str:
    if not params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def get(
    url: str,
    params: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout=DEFAULT_TIMEOUT,
) -> HttpResponse:
    try:
        request = Request(_url_with_params(url, params), headers=dict(headers or {}))
        with urlopen(request, timeout=timeout) as response:
            header_items = tuple(response.headers.items())
            return HttpResponse(
                status_code=getattr(response, "status", response.getcode()),
                headers=dict(header_items),
                content=response.read(),
                header_items=header_items,
            )
    except HTTPError as exc:
        body, header_items = _consume_http_error(exc)
        return HttpResponse(
            status_code=exc.code,
            headers=dict(header_items),
            content=body,
            header_items=header_items,
        )
    except URLError as exc:
        raise HttpRequestError(str(exc.reason)) from exc
    except OSError as exc:
        raise HttpRequestError(str(exc)) from exc
    except ValueError as exc:
        raise HttpRequestError(str(exc)) from exc


def get_json(url: str, **kwargs):
    response = get(url, **kwargs)
    response.raise_for_status()
    return response.json()


def get_text(url: str, **kwargs) -> str:
    response = get(url, **kwargs)
    response.raise_for_status()
    return response.text


DEFAULT_CHUNK_SIZE = 64 * 1024


def _consume_http_error(exc: HTTPError) -> tuple[bytes, tuple[tuple[str, str], ...]]:
    try:
        header_items = tuple(exc.headers.items()) if exc.headers else ()
        return exc.read(), header_items
    finally:
        exc.close()


def stream_download(
    url: str,
    target,
    *,
    headers: Mapping[str, str] | None = None,
    timeout=DEFAULT_TIMEOUT,
    chunk_size=DEFAULT_CHUNK_SIZE,
    progress=None,
) -> int:
    try:
        request = Request(url, headers=dict(headers or {}))
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            if status >= 400:
                header_items = tuple(response.headers.items())
                raise HttpStatusError(
                    status,
                    response.read(),
                    dict(header_items),
                    header_items,
                )
            total_header = response.headers.get("content-length")
            try:
                total = int(total_header) if total_header else None
            except ValueError:
                total = None
            with open(target, "wb") as file:
                downloaded = 0
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    size = file.write(chunk)
                    downloaded += size
                    if progress is not None:
                        progress(size, downloaded, total)
    except HTTPError as exc:
        body, header_items = _consume_http_error(exc)
        raise HttpStatusError(
            exc.code,
            body,
            dict(header_items),
            header_items,
        ) from exc
    except URLError as exc:
        raise HttpRequestError(str(exc.reason)) from exc
    except OSError as exc:
        raise HttpRequestError(str(exc)) from exc
    except ValueError as exc:
        raise HttpRequestError(str(exc)) from exc

    if total is not None and total != downloaded:
        raise ConnectionError("File download was interrupted for " + str(target))
    return downloaded
