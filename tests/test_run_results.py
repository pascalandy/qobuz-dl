import os
from pathlib import Path

import pytest

from qobuz_dl import downloader, http
from qobuz_dl.console import ExitCode
from qobuz_dl.core import (
    QobuzDL,
    RunItem,
    RunProblem,
    RunResult,
    Source,
    SourceError,
    expand_sources,
    parse_source_url,
)
from qobuz_dl.downloader import QL_DOWNGRADE, DownloadResult
from qobuz_dl.exceptions import ApiRateLimitError

FIXTURES = Path(__file__).parent / "fixtures"

# Real-world shapes the command line accepts, with the source they become.
ACCEPTED_URLS = [
    ("https://play.qobuz.com/album/qxjbxh1dc3xyb", "album", "qxjbxh1dc3xyb"),
    ("https://open.qobuz.com/track/59829287", "track", "59829287"),
    (
        "https://www.qobuz.com/us-en/album/random-access-memories-daft-punk/"
        "0886443927087",
        "album",
        "0886443927087",
    ),
    (
        "https://www.qobuz.com/fr-fr/playlist/jazz-classics/1234567",
        "playlist",
        "1234567",
    ),
    ("https://play.qobuz.com/artist/36819", "artist", "36819"),
    ("https://play.qobuz.com/label/1153", "label", "1153"),
    ("https://play.qobuz.com/album/qxjbxh1dc3xyb/", "album", "qxjbxh1dc3xyb"),
    (
        "https://play.qobuz.com/album/qxjbxh1dc3xyb?utm_source=share#top",
        "album",
        "qxjbxh1dc3xyb",
    ),
    ("https://www.qobuz.com/us-en/album/caf%C3%A9-tacvba/abc123", "album", "abc123"),
    ("https://PLAY.qobuz.com/album/abc123", "album", "abc123"),
]
ACCEPTED_LASTFM_URLS = [
    "https://www.last.fm/user/example/playlists/123",
    "https://last.fm/user/example/playlists/123",
    "https://www.last.fm/de/user/example/playlists/123?ref=share",
]
REJECTED_URLS = [
    "https://evil.invalid/track/123",
    "https://play.qobuz.com.evil.invalid/album/abc123",
    "https://evil.invalid/play.qobuz.com/album/abc123",
    "https://play.qobuz.com@evil.invalid/album/abc123",
    "http://play.qobuz.com/album/abc123",
    "https://play.qobuz.com:8443/album/abc123",
    "https://play.qobuz.com/album/",
    "https://play.qobuz.com/video/abc123",
    "https://play.qobuz.com/album/abc-123",
    "https://play.qobuz.com/us-en/album/a/b/abc123",
    "https://www.last.fm/music/Some+Artist",
    "https://www.last.fm/user/example/library",
    "https://evil.invalid/www.last.fm/user/example/playlists/123",
    "https://www.last.fm.evil.invalid/user/example/playlists/123",
    "play.qobuz.com/album/abc123",
    "/us-en/album/-/abc123",
]


@pytest.mark.parametrize(("url", "url_type", "item_id"), ACCEPTED_URLS)
def test_accepted_qobuz_url_shapes_become_sources(url, url_type, item_id):
    assert parse_source_url(url) == Source("qobuz", url, None, url_type, item_id)


@pytest.mark.parametrize("url", ACCEPTED_LASTFM_URLS)
def test_accepted_lastfm_url_shapes_become_sources(url):
    assert parse_source_url(url) == Source("lastfm", url)


@pytest.mark.parametrize("url", REJECTED_URLS)
def test_look_alike_and_unsupported_urls_are_rejected(url):
    assert parse_source_url(url) is None
    with pytest.raises(SourceError, match="not a supported Qobuz or Last.fm URL"):
        expand_sources([url])


def test_text_files_expand_in_order_with_locations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("nested.txt").write_text("https://play.qobuz.com/track/2\n", encoding="utf-8")
    Path("urls.txt").write_text(
        "# a comment\n"
        "\n"
        "  https://play.qobuz.com/album/abc1  \n"
        "nested.txt\n"
        "https://www.last.fm/user/example/playlists/9\r\n",
        encoding="utf-8",
    )

    sources = expand_sources(["urls.txt", "https://play.qobuz.com/label/7"])

    assert sources == [
        Source(
            "qobuz", "https://play.qobuz.com/album/abc1", "urls.txt:3", "album", "abc1"
        ),
        Source("qobuz", "https://play.qobuz.com/track/2", "nested.txt:1", "track", "2"),
        Source("lastfm", "https://www.last.fm/user/example/playlists/9", "urls.txt:5"),
        Source("qobuz", "https://play.qobuz.com/label/7", None, "label", "7"),
    ]


def test_invalid_line_names_its_file_and_line(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("urls.txt").write_text(
        "https://play.qobuz.com/album/abc1\nhtps://play.qobuz.com/album/abc2\n",
        encoding="utf-8",
    )

    with pytest.raises(SourceError) as error:
        expand_sources(["urls.txt"])

    assert str(error.value) == (
        "urls.txt:2: not a supported Qobuz or Last.fm URL: "
        "'htps://play.qobuz.com/album/abc2'"
    )


def test_missing_argument_file_is_named(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SourceError) as error:
        expand_sources(["missing.txt"])

    assert str(error.value) == (
        "not a supported Qobuz or Last.fm URL, and no such file: 'missing.txt'"
    )


def test_origin_labels_argument_locations():
    with pytest.raises(SourceError) as error:
        expand_sources(["https://play.qobuz.com/album/a1", "nope"], origin="<stdin>")

    assert str(error.value).startswith("<stdin>:2: ")


def test_self_inclusion_is_an_error_but_double_inclusion_keeps_both(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    Path("shared.txt").write_text("https://play.qobuz.com/track/5\n", encoding="utf-8")
    Path("twice.txt").write_text("shared.txt\nshared.txt\n", encoding="utf-8")
    Path("loop-a.txt").write_text("loop-b.txt\n", encoding="utf-8")
    Path("loop-b.txt").write_text("loop-a.txt\n", encoding="utf-8")
    Path("self.txt").write_text("self.txt\n", encoding="utf-8")

    assert [source.location for source in expand_sources(["twice.txt"])] == [
        "shared.txt:1",
        "shared.txt:1",
    ]
    with pytest.raises(SourceError, match=r"^self.txt:1: 'self.txt' includes itself$"):
        expand_sources(["self.txt"])
    with pytest.raises(
        SourceError, match=r"^loop-b.txt:1: 'loop-a.txt' includes itself$"
    ):
        expand_sources(["loop-a.txt"])


def test_unreadable_text_file_is_named(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("binary.txt").write_bytes(b"\xff\xfe\x00bad")

    with pytest.raises(SourceError) as error:
        expand_sources(["binary.txt"])

    assert str(error.value) == "cannot read text file 'binary.txt': not UTF-8 text"


@pytest.mark.parametrize(
    ("result", "classification"),
    [
        (DownloadResult("finalized", "downloaded", ("a",)), "satisfied"),
        (DownloadResult("finalized", "verified_artifact", ("a",)), "satisfied"),
        (DownloadResult("finalized", "existing_file", ("a",)), "satisfied"),
        (DownloadResult("ignored", "type_filter"), "no_op"),
        (DownloadResult("ignored", "empty_release"), "no_op"),
        (DownloadResult("ignored", "quality_filter"), "permanent"),
        (DownloadResult("ignored", "demo"), "permanent"),
        (DownloadResult("failed", "path_conflict"), "permanent"),
        (DownloadResult("failed", "request_error"), "permanent"),
        (DownloadResult("failed", "request_error", retryable=True), "temporary"),
    ],
)
def test_classification_table(result, classification):
    assert RunItem("src", "track", "1", result).classification == classification


def test_problems_are_unsatisfied_and_classified_by_retryability():
    assert RunProblem("no_match", "no results", "query").classification == "permanent"
    assert (
        RunProblem("rate_limited", "limit", "query", retryable=True).classification
        == "temporary"
    )


def _item(state, reason, retryable=False, paths=()):
    return RunItem("src", "track", "1", DownloadResult(state, reason, paths, retryable))


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([], ExitCode.OK),
        ([_item("finalized", "downloaded", paths=("a",))], ExitCode.OK),
        ([_item("ignored", "type_filter")], ExitCode.OK),
        (
            [
                _item("finalized", "downloaded", paths=("a",)),
                _item("failed", "request_error", True),
            ],
            ExitCode.TEMPORARY,
        ),
        (
            [
                _item("ignored", "quality_filter"),
                _item("failed", "request_error", True),
            ],
            ExitCode.FAILURE,
        ),
        (
            [_item("failed", "path_conflict"), _item("failed", "request_error", True)],
            ExitCode.FAILURE,
        ),
        (
            [
                _item("failed", "missing_url"),
                RunProblem("rate_limited", "limit", "src", retryable=True),
            ],
            ExitCode.FAILURE,
        ),
        ([RunProblem("rate_limited", "limit", "src", retryable=True)], 75),
        ([RunProblem("no_match", "none", "src")], ExitCode.FAILURE),
    ],
)
def test_exit_precedence_is_failure_then_temporary_then_success(entries, expected):
    run = RunResult()
    for entry in entries:
        if isinstance(entry, RunItem):
            run.add_item(entry)
        else:
            run.add_problem(entry)

    assert run.exit_code() == expected


def test_finalized_paths_are_reported_once_as_they_arrive():
    reported = []
    run = RunResult(on_path=reported.append)

    run.add_item(_item("finalized", "downloaded", paths=("a.flac",)))
    run.add_item(_item("failed", "tagging_error", paths=("b.flac",)))
    run.add_item(_item("finalized", "verified_artifact", paths=("a.flac",)))
    run.add_item(_item("finalized", "existing_file", paths=("c.flac",)))

    assert reported == ["a.flac", "c.flac"]
    assert len(run.items) == 4


@pytest.mark.parametrize(
    ("children", "expected"),
    [
        (
            [
                DownloadResult("failed", "request_error", retryable=True),
                DownloadResult("failed", "request_error", retryable=True),
            ],
            DownloadResult("failed", "request_error", retryable=True),
        ),
        (
            [
                DownloadResult("finalized", "downloaded", ("a",)),
                DownloadResult("failed", "request_error", retryable=True),
            ],
            DownloadResult("failed", "request_error", ("a",), retryable=True),
        ),
        (
            [
                DownloadResult("failed", "missing_url"),
                DownloadResult("failed", "request_error", retryable=True),
            ],
            DownloadResult("failed", "missing_url", retryable=False),
        ),
    ],
)
def test_album_is_retryable_only_when_every_failed_track_is(children, expected):
    assert downloader._aggregate_download_results(children) == expected


def _flac_url(track_id):
    return {
        "url": f"https://media.example.test/{track_id}.flac",
        "sampling_rate": 44.1,
        "bit_depth": 16,
        "format_id": 6,
        "mime_type": "audio/flac",
    }


def _track(track_id, number):
    return {
        "id": track_id,
        "title": f"Track {number}",
        "performer": {"name": "Artist"},
        "track_number": number,
        "media_number": 1,
        "maximum_bit_depth": 16,
        "maximum_sampling_rate": 44.1,
        "version": None,
    }


class _AlbumClient:
    """One album; each track's file URL response or error is configurable."""

    def __init__(self, responses):
        self.responses = responses

    def get_album_meta(self, album_id):
        return {
            "id": album_id,
            "streamable": True,
            "release_type": "album",
            "title": "Album",
            "artist": {"name": "Artist"},
            "release_date_original": "2024-01-02",
            "image": {"large": "https://images.example.test/cover.jpg"},
            "tracks": {
                "items": [
                    _track(track_id, number)
                    for number, track_id in enumerate(self.responses, start=1)
                ]
            },
        }

    def get_track_url(self, track_id, fmt_id):
        response = self.responses[track_id]
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.fixture
def offline_media(monkeypatch):
    fixture = (FIXTURES / "synthetic-silence.flac").read_bytes()

    def copy_fixture(url, filename, _description, *, retry_rate_limited=False):
        Path(filename).write_bytes(fixture)

    def publish(filename, _root, final_name, *_args, finalize=True):
        if finalize:
            os.replace(filename, final_name)

    monkeypatch.setattr(downloader, "download_with_progress", copy_fixture)
    monkeypatch.setattr(downloader.metadata, "tag_flac", publish)


def _album_run(tmp_path, responses):
    reported = []
    qobuz = QobuzDL(directory=tmp_path / "music", no_cover=True, folder_format="album")
    qobuz.client = _AlbumClient(responses)
    qobuz.run_result = RunResult(on_path=reported.append)
    run = qobuz.download_sources(expand_sources(["https://play.qobuz.com/album/a1"]))
    return run, reported


def test_refusal_plus_network_failure_in_one_album_exits_1(tmp_path, offline_media):
    refused = {**_flac_url("t1"), "restrictions": [{"code": QL_DOWNGRADE}]}
    timeout = http.HttpTransportError("timed out")

    qobuz = QobuzDL(
        directory=tmp_path / "music",
        no_cover=True,
        folder_format="album",
        quality_fallback=False,
    )
    qobuz.client = _AlbumClient({"t1": refused, "t2": timeout})
    run = qobuz.download_sources(expand_sources(["https://play.qobuz.com/album/a1"]))

    assert [(item.item_id, item.result) for item in run.items] == [
        ("t1", DownloadResult("ignored", "quality_filter")),
        ("t2", DownloadResult("failed", "request_error", retryable=True)),
    ]
    assert run.exit_code() == ExitCode.FAILURE


def test_permanent_plus_network_failure_in_one_album_exits_1(tmp_path, offline_media):
    missing = {**_flac_url("t1"), "url": None}
    run, reported = _album_run(
        tmp_path, {"t1": missing, "t2": http.HttpTransportError("reset")}
    )

    assert [item.result.reason for item in run.items] == [
        "missing_url",
        "request_error",
    ]
    assert reported == []
    assert run.exit_code() == ExitCode.FAILURE


def test_partial_album_with_only_temporary_failures_exits_75(tmp_path, offline_media):
    run, reported = _album_run(
        tmp_path, {"t1": _flac_url("t1"), "t2": http.HttpStatusError(503)}
    )

    final = str(tmp_path / "music" / "album" / "01. Track 1.flac")
    assert reported == [final]
    assert [(item.source, item.kind, item.item_id) for item in run.items] == [
        ("https://play.qobuz.com/album/a1", "track", "t1"),
        ("https://play.qobuz.com/album/a1", "track", "t2"),
    ]
    assert run.items[1].result.retryable is True
    assert run.exit_code() == ExitCode.TEMPORARY


def test_permanent_request_error_is_not_retryable(tmp_path, offline_media):
    run, _reported = _album_run(tmp_path, {"t1": http.HttpStatusError(404)})

    assert run.items[0].result == DownloadResult("failed", "request_error")
    assert run.exit_code() == ExitCode.FAILURE


def test_album_level_failures_are_recorded_once(tmp_path):
    class UnavailableAlbum:
        def get_album_meta(self, album_id):
            raise http.HttpStatusError(502)

    qobuz = QobuzDL(directory=tmp_path / "music", no_cover=True)
    qobuz.client = UnavailableAlbum()

    run = qobuz.download_sources(expand_sources(["https://play.qobuz.com/album/a1"]))

    assert [(item.kind, item.item_id, item.result) for item in run.items] == [
        ("album", "a1", DownloadResult("failed", "request_error", retryable=True))
    ]
    assert run.exit_code() == ExitCode.TEMPORARY


def test_collection_failure_is_a_problem_and_the_next_source_still_runs(tmp_path):
    calls = []

    class Client:
        def get_artist_meta(self, item_id):
            raise http.HttpStatusError(503)

        def get_album_meta(self, item_id):
            calls.append(item_id)
            return {"streamable": False}

    qobuz = QobuzDL(directory=tmp_path / "music", no_cover=True)
    qobuz.client = Client()

    run = qobuz.download_sources(
        expand_sources(
            ["https://play.qobuz.com/artist/1", "https://play.qobuz.com/album/b2"]
        )
    )

    assert run.problems == [
        RunProblem(
            "request_error",
            "could not read the source: HTTP status 503",
            "https://play.qobuz.com/artist/1",
            retryable=True,
        )
    ]
    assert calls == ["b2"]
    assert run.exit_code() == ExitCode.FAILURE


def test_rate_limit_still_aborts_the_run_for_the_caller(tmp_path):
    class Client:
        def get_album_meta(self, item_id):
            raise ApiRateLimitError("Qobuz API rate limit retries exhausted.")

    qobuz = QobuzDL(directory=tmp_path / "music", no_cover=True)
    qobuz.client = Client()

    with pytest.raises(ApiRateLimitError):
        qobuz.download_sources(expand_sources(["https://play.qobuz.com/album/a1"]))


def test_lastfm_problems_are_recorded_with_retryability(tmp_path, monkeypatch):
    playlist = "https://www.last.fm/user/example/playlists/1"

    def unavailable(url, **kwargs):
        raise http.HttpStatusError(503)

    monkeypatch.setattr(http, "get_text", unavailable)
    qobuz = QobuzDL(directory=tmp_path / "music", no_cover=True)
    run = qobuz.download_sources(expand_sources([playlist]))

    assert [(p.code, p.source, p.retryable) for p in run.problems] == [
        ("request_error", playlist, True)
    ]

    monkeypatch.setattr(
        http,
        "get_text",
        lambda url, **kwargs: (FIXTURES / "lastfm_playlist.html").read_text(),
    )
    qobuz = QobuzDL(directory=tmp_path / "music", no_cover=True)
    qobuz.search_by_type = lambda *args, **kwargs: []
    run = qobuz.download_sources(expand_sources([playlist]))

    assert {problem.code for problem in run.problems} == {"no_match"}
    assert all(not problem.retryable for problem in run.problems)
    assert run.exit_code() == ExitCode.FAILURE
