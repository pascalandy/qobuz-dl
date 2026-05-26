import json
from dataclasses import dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT = 30


class HttpError(Exception):
    """Base error raised by qobuz-dl's internal HTTP boundary."""


class HttpStatusError(HttpError):
    def __init__(self, status_code: int, body: bytes = b""):
        super().__init__(f"HTTP status {status_code}")
        self.status_code = status_code
        self.body = body


class HttpRequestError(HttpError):
    pass


@dataclass
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HttpStatusError(self.status_code, self.content)


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
    request = Request(_url_with_params(url, params), headers=dict(headers or {}))
    try:
        with urlopen(request, timeout=timeout) as response:
            return HttpResponse(
                status_code=getattr(response, "status", response.getcode()),
                headers=dict(response.headers.items()),
                content=response.read(),
            )
    except HTTPError as exc:
        return HttpResponse(
            status_code=exc.code,
            headers=dict(exc.headers.items()) if exc.headers else {},
            content=exc.read(),
        )
    except URLError as exc:
        raise HttpRequestError(str(exc.reason)) from exc
    except OSError as exc:
        raise HttpRequestError(str(exc)) from exc


def get_json(url: str, **kwargs):
    response = get(url, **kwargs)
    response.raise_for_status()
    return response.json()


def get_text(url: str, **kwargs) -> str:
    response = get(url, **kwargs)
    response.raise_for_status()
    return response.text


def stream_download(
    url: str,
    target,
    *,
    headers: Mapping[str, str] | None = None,
    timeout=DEFAULT_TIMEOUT,
    chunk_size=1024,
    progress=None,
) -> int:
    request = Request(url, headers=dict(headers or {}))
    try:
        with urlopen(request, timeout=timeout) as response, open(target, "wb") as file:
            status = getattr(response, "status", response.getcode())
            if status >= 400:
                raise HttpStatusError(status, response.read())
            total_header = response.headers.get("content-length")
            try:
                total = int(total_header) if total_header else None
            except ValueError:
                total = None
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
        raise HttpStatusError(exc.code, exc.read()) from exc
    except URLError as exc:
        raise HttpRequestError(str(exc.reason)) from exc
    except OSError as exc:
        raise HttpRequestError(str(exc)) from exc

    if total is not None and total != downloaded:
        raise ConnectionError("File download was interrupted for " + str(target))
    return downloaded
