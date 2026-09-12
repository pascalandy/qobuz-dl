import builtins

import pytest

from qobuz_dl import downloader, http
from qobuz_dl.commands import qobuz_dl_args
from qobuz_dl.core import QobuzDL


class FakeHeaders(dict):
    def items(self):
        return super().items()


class BufferResponse:
    def __init__(self, body=b"", *, status=200, headers=None, read_times=()):
        self.status = status
        self.headers = FakeHeaders(headers or {})
        self.body = body
        self.read_times = list(read_times)
        self.read_sizes = []
        self.closed = False
        self.clock = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def getcode(self):
        return self.status

    def close(self):
        self.closed = True

    def read(self, size=-1):
        self.read_sizes.append(size)
        if self.body and self.read_times:
            self.clock.advance(self.read_times.pop(0))
        if size == -1:
            chunk = self.body
            self.body = b""
            return chunk
        chunk = self.body[:size]
        self.body = self.body[size:]
        return chunk


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds):
        self.now += seconds


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("off", None),
        ("1KiB/s", 1024),
        ("37KiB/s", 37 * 1024),
        ("1MiB/s", 1024 * 1024),
        ("12MiB/s", 12 * 1024 * 1024),
    ],
)
def test_cli_bandwidth_grammar_accepts_only_named_values(value, expected):
    arguments = qobuz_dl_args().parse_args(
        ["dl", "https://play.qobuz.com/track/example", "--bandwidth-limit", value]
    )

    assert arguments.bandwidth_limit == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "auto",
        "0KiB/s",
        "01KiB/s",
        "+1KiB/s",
        "-1KiB/s",
        "1.5MiB/s",
        "1 KiB/s",
        "1KiB /s",
        "1KB/s",
        "1MB/s",
        "1kib/s",
        "1MIB/S",
    ],
)
def test_cli_bandwidth_grammar_rejects_every_other_form(value):
    with pytest.raises(SystemExit) as exc_info:
        qobuz_dl_args().parse_args(
            [
                "dl",
                "https://play.qobuz.com/track/example",
                "--bandwidth-limit",
                value,
            ]
        )

    assert exc_info.value.code == 2


def test_cli_bandwidth_over_integer_digit_limit_uses_fixed_safe_error(capsys):
    value = f"{'9' * 5000}KiB/s"

    with pytest.raises(SystemExit) as exc_info:
        qobuz_dl_args().parse_args(
            [
                "dl",
                "https://play.qobuz.com/track/example",
                "--bandwidth-limit",
                value,
            ]
        )

    output = capsys.readouterr()
    assert exc_info.value.code == 2
    assert (
        "argument --bandwidth-limit: must be 'off', NKiB/s, or NMiB/s "
        "with a positive integer N"
    ) in output.err
    assert value not in output.err


@pytest.mark.parametrize("value", [0, -1, True, False, 1.0, "1024"])
def test_qobuz_dl_rejects_invalid_public_bandwidth_values(tmp_path, value):
    with pytest.raises(ValueError, match="bandwidth_limit"):
        QobuzDL(directory=tmp_path, bandwidth_limit=value)


def test_qobuz_dl_threads_bandwidth_to_new_downloads(tmp_path):
    qobuz = QobuzDL(directory=tmp_path, bandwidth_limit=4096)
    qobuz.client = object()

    download = qobuz._new_downloader("track-1")

    assert download.bandwidth_limit == 4096


def test_stream_download_paces_exact_bytes_after_read_and_write(tmp_path, monkeypatch):
    clock = Clock()
    response = BufferResponse(
        b"abcdefghijklmno",
        headers={"content-length": "15"},
        read_times=(0.03, 0.01),
    )
    response.clock = clock
    progress = []
    real_open = builtins.open

    class TimedWriter:
        def __init__(self, target, mode):
            self.file = real_open(target, mode)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return self.file.__exit__(exc_type, exc, traceback)

        def write(self, chunk):
            clock.advance(0.02)
            return self.file.write(chunk)

    monkeypatch.setattr(http, "urlopen", lambda request, timeout: response)
    monkeypatch.setattr(http.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(http.time, "sleep", clock.sleep)
    monkeypatch.setattr(
        builtins,
        "open",
        lambda target, mode: (
            TimedWriter(target, mode) if mode == "wb" else real_open(target, mode)
        ),
    )
    target = tmp_path / "track.flac"

    downloaded = http.stream_download(
        "https://media.example.test/track.flac",
        target,
        chunk_size=64,
        bandwidth_limit=100,
        progress=lambda size, total, expected: progress.append(
            (size, total, expected, clock.now)
        ),
    )

    assert target.read_bytes() == b"abcdefghijklmno"
    assert downloaded == 15
    assert response.read_sizes == [10, 10, 10]
    assert clock.sleeps == pytest.approx([0.05, 0.02])
    assert [entry[:3] for entry in progress] == [(10, 10, 15), (5, 15, 15)]
    assert [entry[3] for entry in progress] == pytest.approx([0.1, 0.15])


def test_stream_download_rechecks_deadline_after_early_sleep_return(
    tmp_path, monkeypatch
):
    clock = Clock()
    response = BufferResponse(b"abcdefghij")
    response.clock = clock
    early_return = True

    def sleep(seconds):
        nonlocal early_return
        clock.sleeps.append(seconds)
        if early_return:
            clock.advance(seconds / 4)
            early_return = False
        else:
            clock.advance(seconds)

    monkeypatch.setattr(http, "urlopen", lambda request, timeout: response)
    monkeypatch.setattr(http.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(http.time, "sleep", sleep)

    http.stream_download(
        "https://media.example.test/track.flac",
        tmp_path / "track.flac",
        bandwidth_limit=100,
    )

    assert clock.sleeps == pytest.approx([0.1, 0.075])
    assert clock.now == pytest.approx(0.1)


def test_stream_download_reads_at_least_one_byte_for_low_public_limit(
    tmp_path, monkeypatch
):
    clock = Clock()
    response = BufferResponse(b"ab")
    response.clock = clock
    monkeypatch.setattr(http, "urlopen", lambda request, timeout: response)
    monkeypatch.setattr(http.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(http.time, "sleep", clock.sleep)

    http.stream_download(
        "https://media.example.test/track.flac",
        tmp_path / "track.flac",
        chunk_size=64,
        bandwidth_limit=5,
    )

    assert response.read_sizes == [1, 1, 1]
    assert clock.sleeps == pytest.approx([0.2, 0.2])


def test_stream_download_gives_no_oversleep_or_idle_credit(tmp_path, monkeypatch):
    clock = Clock()
    response = BufferResponse(b"abcdefghijklmnopqrst")
    response.clock = clock
    progress_times = []

    def oversleep(seconds):
        clock.sleeps.append(seconds)
        clock.advance(seconds + 0.05)

    def record_progress(size, downloaded, total):
        progress_times.append(clock.now)
        if downloaded == 10:
            clock.advance(0.2)

    monkeypatch.setattr(http, "urlopen", lambda request, timeout: response)
    monkeypatch.setattr(http.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(http.time, "sleep", oversleep)

    http.stream_download(
        "https://media.example.test/track.flac",
        tmp_path / "track.flac",
        bandwidth_limit=100,
        progress=record_progress,
    )

    assert clock.sleeps == pytest.approx([0.1, 0.1])
    assert progress_times == pytest.approx([0.15, 0.5])


def test_unlimited_stream_preserves_chunking_and_never_reads_the_clock(
    tmp_path, monkeypatch
):
    response = BufferResponse(b"abcdefghij", headers={"content-length": "10"})
    progress = []
    monkeypatch.setattr(http, "urlopen", lambda request, timeout: response)
    monkeypatch.setattr(
        http.time,
        "monotonic",
        lambda: pytest.fail("unlimited downloads must not read the pacing clock"),
    )
    monkeypatch.setattr(
        http.time,
        "sleep",
        lambda seconds: pytest.fail("unlimited downloads must not sleep"),
    )
    target = tmp_path / "track.flac"

    downloaded = http.stream_download(
        "https://media.example.test/track.flac",
        target,
        chunk_size=4,
        bandwidth_limit=None,
        progress=lambda size, total, expected: progress.append((size, total, expected)),
    )

    assert target.read_bytes() == b"abcdefghij"
    assert downloaded == 10
    assert response.read_sizes == [4, 4, 4, 4]
    assert progress == [(4, 4, 10), (4, 8, 10), (2, 10, 10)]


def test_rate_limit_wait_finishes_before_media_pacing_starts(tmp_path, monkeypatch):
    clock = Clock()
    rejected = BufferResponse(status=429, headers={"Retry-After": "2"})
    accepted = BufferResponse(b"abcdefghij")
    rejected.clock = accepted.clock = clock
    responses = iter((rejected, accepted))
    monkeypatch.setattr(http, "urlopen", lambda request, timeout: next(responses))
    monkeypatch.setattr(http.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(http.time, "sleep", clock.sleep)

    http.stream_download(
        "https://media.example.test/track.flac",
        tmp_path / "track.flac",
        retry_rate_limited=True,
        bandwidth_limit=100,
    )

    assert clock.sleeps == pytest.approx([2, 0.1])
    assert clock.now == pytest.approx(2.1)
    assert rejected.closed is True
    assert accepted.closed is True


def test_pacing_cancellation_cleans_partial_file_and_closes_response(
    tmp_path, monkeypatch
):
    response = BufferResponse(b"abcdefghij")
    response.clock = Clock()
    monkeypatch.setattr(http, "urlopen", lambda request, timeout: response)
    monkeypatch.setattr(http.time, "monotonic", lambda: 0.0)

    def cancel(seconds):
        raise KeyboardInterrupt("pacing cancelled")

    monkeypatch.setattr(http.time, "sleep", cancel)
    target = tmp_path / "partial.flac"

    with pytest.raises(KeyboardInterrupt, match="pacing cancelled"):
        downloader.download_with_progress(
            "https://media.example.test/track.flac",
            target,
            "track",
            bandwidth_limit=100,
        )

    assert not target.exists()
    assert response.closed is True
