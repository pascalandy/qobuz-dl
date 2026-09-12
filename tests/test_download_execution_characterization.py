import os
import shutil
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3

from qobuz_dl import downloader
from qobuz_dl.core import QobuzDL
from qobuz_dl.downloader import Download

FIXTURES = Path(__file__).parent / "fixtures"


def _track(track_id, title, track_number, media_number=1):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Track Artist"},
        "album": {"artist": {"name": "Album Artist"}},
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 96,
        "track_number": track_number,
        "media_number": media_number,
        "version": None,
    }


def _album_meta(*, tracks=None, goodies=None):
    return {
        "id": "album-1",
        "streamable": True,
        "release_type": "album",
        "title": "Album Title",
        "artist": {"name": "Album Artist"},
        "release_date_original": "2024-02-03",
        "image": {"large": "https://img.example.test/cover_600.jpg"},
        "tracks": {
            "items": tracks
            or [
                _track("track-1", "Opening", 1, 1),
                _track("track-2", "Finale", 2, 2),
            ]
        },
        "tracks_count": 2,
        "genres_list": ["Rock"],
        "label": {"name": "Label"},
        "copyright": "",
        "goodies": goodies
        if goodies is not None
        else [{"url": "https://img.example.test/booklet.pdf"}],
    }


def _track_meta(track_id="track-1", title="Single Track"):
    return {
        **_track(track_id, title, 1),
        "album": {
            "title": "Track Album",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-02-03",
            "image": {"large": "https://img.example.test/cover_600.jpg"},
            "tracks_count": 1,
            "genres_list": ["Rock"],
        },
        "copyright": "",
    }


def _labeled_track_meta():
    track_meta = _track_meta()
    track_meta["album"]["label"] = {"name": "Nested Track Label"}
    return track_meta


def _track_url(track_id, *, restrictions=None):
    parsed = {
        "url": f"https://media.example.test/{track_id}.flac",
        "sampling_rate": 96,
        "bit_depth": 24,
    }
    if restrictions is not None:
        parsed["restrictions"] = restrictions
    return parsed


class FakeDownloadClient:
    def __init__(self, *, album_meta=None, track_meta=None, restrictions=None):
        self.album_meta = album_meta or _album_meta()
        self.track_meta = track_meta or _track_meta()
        self.restrictions = restrictions
        self.track_url_calls = []

    def get_album_meta(self, item_id):
        assert item_id == self.album_meta["id"]
        return self.album_meta

    def get_track_meta(self, item_id):
        assert item_id == self.track_meta["id"]
        return self.track_meta

    def get_track_url(self, item_id, fmt_id):
        self.track_url_calls.append((item_id, fmt_id))
        return _track_url(item_id, restrictions=self.restrictions)


def _recording_download(monkeypatch, downloads):
    def fake_download_with_progress(url, fname, desc, *, retry_rate_limited=False):
        downloads.append((url, fname, desc))
        Path(fname).write_bytes(b"audio")

    monkeypatch.setattr(
        downloader, "download_with_progress", fake_download_with_progress
    )


def _recording_tag(monkeypatch, tagged):
    def fake_tag(
        filename,
        root_dir,
        final_file,
        track_metadata,
        album_or_track_metadata,
        is_track,
        embed_art,
    ):
        tagged.append(
            {
                "filename": filename,
                "root_dir": root_dir,
                "final_file": final_file,
                "track_id": track_metadata["id"],
                "album_id": album_or_track_metadata["id"],
                "is_track": is_track,
                "embed_art": embed_art,
            }
        )
        os.replace(filename, final_file)

    monkeypatch.setattr(downloader.metadata, "tag_flac", fake_tag)


def _assert_owned_temporary(path, directory):
    temporary = Path(path)
    assert temporary.parent == Path(directory)
    assert temporary.name.startswith(".qdl-")
    assert temporary.name.endswith(".tmp")
    token = temporary.name.removeprefix(".qdl-").removesuffix(".tmp")
    assert len(token) == 32
    int(token, 16)


def _download_real_media(
    monkeypatch,
    tmp_path,
    *,
    quality,
    track_meta=None,
    album_meta=None,
    album=False,
):
    extension = "mp3" if quality == 5 else "flac"
    fixture = FIXTURES / f"synthetic-silence.{extension}"

    def copy_fixture(_url, filename, _description, *, retry_rate_limited=False):
        shutil.copyfile(fixture, filename)

    monkeypatch.setattr(downloader, "download_with_progress", copy_fixture)
    qdl = QobuzDL(
        directory=tmp_path,
        quality=quality,
        no_cover=True,
        folder_format="proof",
        track_format="track",
    )
    qdl.client = FakeDownloadClient(track_meta=track_meta, album_meta=album_meta)

    qdl.download_from_id("album-1" if album else "track-1", album=album)

    return tmp_path / "proof" / f"track.{extension}"


def test_direct_mp3_download_writes_nested_album_label_to_final_file(
    tmp_path, monkeypatch
):
    final_file = _download_real_media(
        monkeypatch,
        tmp_path,
        quality=5,
        track_meta=_labeled_track_meta(),
    )

    assert final_file.exists()
    assert ID3(final_file, translate=False)["TPUB"].text == ["Nested Track Label"]


def test_direct_flac_download_writes_nested_album_label_to_final_file(
    tmp_path, monkeypatch
):
    final_file = _download_real_media(
        monkeypatch,
        tmp_path,
        quality=6,
        track_meta=_labeled_track_meta(),
    )

    assert final_file.exists()
    assert FLAC(final_file)["LABEL"] == ["Nested Track Label"]


@pytest.mark.parametrize("quality", [5, 6], ids=["mp3", "flac"])
def test_direct_download_tolerates_missing_nested_album_label(
    tmp_path, monkeypatch, quality
):
    track_meta = _track_meta()

    final_file = _download_real_media(
        monkeypatch,
        tmp_path,
        quality=quality,
        track_meta=track_meta,
    )

    if quality == 5:
        assert "TPUB" not in ID3(final_file, translate=False)
    else:
        assert FLAC(final_file)["LABEL"] == ["n/a"]


@pytest.mark.parametrize("quality", [5, 6], ids=["mp3", "flac"])
def test_album_download_preserves_label_in_final_file(tmp_path, monkeypatch, quality):
    album_meta = _album_meta(tracks=[_track("track-1", "Opening", 1)])
    album_meta.pop("goodies")

    final_file = _download_real_media(
        monkeypatch,
        tmp_path,
        quality=quality,
        album_meta=album_meta,
        album=True,
    )

    if quality == 5:
        assert ID3(final_file, translate=False)["TPUB"].text == ["Label"]
    else:
        assert FLAC(final_file)["LABEL"] == ["Label"]


def test_download_id_by_type_delegates_to_explicit_methods(monkeypatch, tmp_path):
    calls = []
    download = Download(object(), "item-1", str(tmp_path), 27)
    monkeypatch.setattr(download, "download_track", lambda: calls.append("track"))
    monkeypatch.setattr(download, "download_release", lambda: calls.append("release"))

    download.download_id_by_type()
    download.download_id_by_type(track=True)
    download.download_id_by_type(track=False)

    assert calls == ["track", "track", "release"]


def test_album_download_places_multidisc_tracks_cover_and_booklet(
    tmp_path, monkeypatch
):
    downloads = []
    tagged = []
    _recording_download(monkeypatch, downloads)
    _recording_tag(monkeypatch, tagged)
    client = FakeDownloadClient()

    Download(
        client,
        "album-1",
        str(tmp_path),
        27,
        cover_og_quality=True,
    ).download_release()

    album_dir = os.path.join(
        str(tmp_path), "Album Artist - Album Title (2024) [24B-96kHz]"
    )
    disc_1 = os.path.join(album_dir, "Disc 1")
    disc_2 = os.path.join(album_dir, "Disc 2")

    assert len(downloads) == 4
    assert downloads[:2] == [
        (
            "https://img.example.test/cover_org.jpg",
            os.path.join(album_dir, "cover.jpg"),
            "cover.jpg",
        ),
        (
            "https://img.example.test/booklet.pdf",
            os.path.join(album_dir, "booklet.pdf"),
            "booklet.pdf",
        ),
    ]
    assert [record[0] for record in downloads[2:]] == [
        "https://media.example.test/track-1.flac",
        "https://media.example.test/track-2.flac",
    ]
    _assert_owned_temporary(downloads[2][1], disc_1)
    _assert_owned_temporary(downloads[3][1], disc_2)
    assert all(target == description for _, target, description in downloads[2:])
    assert [record["filename"] for record in tagged] == [
        downloads[2][1],
        downloads[3][1],
    ]
    assert [
        (record["root_dir"], record["final_file"], record["is_track"])
        for record in tagged
    ] == [
        (disc_1, os.path.join(disc_1, "01. Opening.flac"), False),
        (disc_2, os.path.join(disc_2, "02. Finale.flac"), False),
    ]
    assert client.track_url_calls == [
        ("track-1", 27),
        ("track-2", 27),
    ]


def test_track_download_uses_fallback_quality_and_can_skip_cover(tmp_path, monkeypatch):
    downloads = []
    tagged = []
    _recording_download(monkeypatch, downloads)
    _recording_tag(monkeypatch, tagged)
    client = FakeDownloadClient(
        restrictions=[{"code": downloader.QL_DOWNGRADE}],
    )

    Download(
        client,
        "track-1",
        str(tmp_path),
        27,
        downgrade_quality=True,
        no_cover=True,
    ).download_track()

    track_dir = os.path.join(
        str(tmp_path), "Album Artist - Track Album (2024) [24B-96kHz]"
    )
    assert len(downloads) == 1
    url, temporary, description = downloads[0]
    assert url == "https://media.example.test/track-1.flac"
    _assert_owned_temporary(temporary, track_dir)
    assert description == temporary
    assert tagged[0]["filename"] == temporary
    assert tagged[0]["final_file"] == os.path.join(track_dir, "01. Single Track.flac")
    assert tagged[0]["is_track"] is True


def test_album_download_skips_each_restricted_track_when_fallback_disabled(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(
        downloader,
        "download_with_progress",
        lambda *args, **kwargs: pytest.fail("download should be skipped"),
    )
    client = FakeDownloadClient(
        album_meta=_album_meta(goodies=[]),
        restrictions=[{"code": downloader.QL_DOWNGRADE}],
    )
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    result = Download(
        client,
        "album-1",
        str(tmp_path),
        27,
        downgrade_quality=False,
        no_cover=True,
    ).download_release()

    assert (result.state, result.reason, result.finalized_paths) == (
        "ignored",
        "quality_filter",
        (),
    )
    assert not list(tmp_path.rglob("*.flac"))
    assert (
        sum(
            "doesn't meet quality requirement" in record.getMessage()
            for record in caplog.records
        )
        == 2
    )
    assert client.track_url_calls == [("track-1", 27), ("track-2", 27)]


def test_existing_track_file_is_skipped_without_streaming_or_tagging(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(
        downloader,
        "download_with_progress",
        lambda *args, **kwargs: pytest.fail("existing file should not stream"),
    )
    monkeypatch.setattr(
        downloader.metadata,
        "tag_flac",
        lambda *args, **kwargs: pytest.fail("existing file should not be tagged"),
    )
    client = FakeDownloadClient()
    track_dir = tmp_path / "Album Artist - Track Album (2024) [24B-96kHz]"
    track_dir.mkdir()
    final_file = track_dir / "01. Single Track.flac"
    final_file.write_bytes(b"already here")
    caplog.set_level("INFO", logger="qobuz_dl.downloader")

    Download(
        client,
        "track-1",
        str(tmp_path),
        27,
        no_cover=True,
    ).download_track()

    assert final_file.read_bytes() == b"already here"
    assert any(
        "was already downloaded" in record.getMessage() for record in caplog.records
    )


def test_failed_media_stream_removes_partial_file_and_logs_safe_failure(
    tmp_path, monkeypatch, caplog
):
    def fake_stream_download(
        url, target_path, *, progress=None, retry_rate_limited=False
    ):
        Path(target_path).write_bytes(b"partial")
        raise ConnectionError("interrupted stream")

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(
        downloader.metadata,
        "tag_flac",
        lambda *args, **kwargs: pytest.fail("failed stream should not be tagged"),
    )
    qdl = QobuzDL(directory=tmp_path, quality=27, no_cover=True)
    qdl.client = FakeDownloadClient()
    caplog.set_level("ERROR", logger="qobuz_dl.downloader")

    result = qdl.download_from_id("track-1", album=False)

    track_dir = tmp_path / "Album Artist - Track Album (2024) [24B-96kHz]"
    assert not list(track_dir.glob(".*.tmp"))
    assert result.state == "failed"
    assert result.reason == "request_error"
    assert result.finalized_paths == ()
    assert any(
        "Error getting release" in record.getMessage() for record in caplog.records
    )


def test_track_tag_failure_removes_only_its_operation_temporary(tmp_path, monkeypatch):
    track_dir = tmp_path / "Album Artist - Track Album (2024) [24B-96kHz]"
    track_dir.mkdir()
    sentinel = track_dir / ".unrelated.tmp"
    sentinel.write_bytes(b"unrelated sentinel bytes")
    operation_paths = []

    def fake_stream_download(
        url, target_path, *, progress=None, retry_rate_limited=False
    ):
        operation_path = Path(target_path)
        operation_paths.append(operation_path)
        operation_path.write_bytes(b"downloaded audio bytes")

    def fail_tag(*args, **kwargs):
        raise RuntimeError("tagging failed")

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", fail_tag)

    Download(
        FakeDownloadClient(),
        "track-1",
        str(tmp_path),
        27,
        no_cover=True,
    ).download_track()

    assert len(operation_paths) == 1
    assert not operation_paths[0].exists()
    assert sentinel.read_bytes() == b"unrelated sentinel bytes"


def test_track_tag_interrupt_propagates_and_removes_operation_temporary(
    tmp_path, monkeypatch
):
    operation_paths = []
    interrupt = KeyboardInterrupt("tagging interrupted")

    def fake_stream_download(
        url, target_path, *, progress=None, retry_rate_limited=False
    ):
        operation_path = Path(target_path)
        operation_paths.append(operation_path)
        operation_path.write_bytes(b"downloaded audio bytes")

    def interrupt_tag(*args, **kwargs):
        raise interrupt

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", interrupt_tag)
    download = Download(
        FakeDownloadClient(),
        "track-1",
        str(tmp_path),
        27,
        no_cover=True,
    )

    with pytest.raises(KeyboardInterrupt) as exc_info:
        download.download_track()

    assert exc_info.value is interrupt
    assert len(operation_paths) == 1
    assert not operation_paths[0].exists()


def test_nested_track_downloads_own_distinct_temporary_files(tmp_path, monkeypatch):
    operation_paths = {}
    final_paths = {}
    observations = {}
    audio_a = b"operation A partial and final bytes"
    audio_b = b"operation B partial bytes"
    download_b = Download(
        FakeDownloadClient(track_meta=_track_meta("track-b", "Operation B")),
        "track-b",
        str(tmp_path),
        27,
        no_cover=True,
    )

    def fake_stream_download(
        url, target_path, *, progress=None, retry_rate_limited=False
    ):
        operation = "a" if url.endswith("track-a.flac") else "b"
        operation_path = Path(target_path)
        operation_paths[operation] = operation_path
        operation_path.write_bytes(audio_a if operation == "a" else audio_b)
        if operation == "a":
            download_b.download_track()
            path_a = operation_paths["a"]
            observations["a_exists_after_b"] = path_a.exists()
            observations["a_bytes_after_b"] = (
                path_a.read_bytes() if path_a.exists() else None
            )
            observations["b_exists_after_failure"] = operation_paths["b"].exists()
        else:
            live_paths = (operation_paths["a"], operation_paths["b"])
            observations["both_exist_during_b"] = all(
                path.exists() for path in live_paths
            )

    def fake_tag(
        filename,
        root_dir,
        final_file,
        track_metadata,
        album_or_track_metadata,
        is_track,
        embed_art,
    ):
        operation = "a" if track_metadata["id"] == "track-a" else "b"
        final_paths[operation] = Path(final_file)
        if operation == "b":
            raise RuntimeError("operation B tagging failed")
        os.replace(filename, final_file)

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", fake_tag)

    Download(
        FakeDownloadClient(track_meta=_track_meta("track-a", "Operation A")),
        "track-a",
        str(tmp_path),
        27,
        no_cover=True,
    ).download_track()

    assert observations["both_exist_during_b"] is True
    assert operation_paths["a"] != operation_paths["b"]
    assert final_paths["a"] != final_paths["b"]
    assert observations["a_exists_after_b"] is True
    assert observations["a_bytes_after_b"] == audio_a
    assert observations["b_exists_after_failure"] is False
    assert not operation_paths["b"].exists()
    assert final_paths["a"].read_bytes() == audio_a


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits require POSIX")
@pytest.mark.parametrize(
    ("creation_umask", "expected_mode"),
    [(0o022, 0o644), (0o077, 0o600)],
)
def test_operation_temporary_uses_ordinary_creation_mode(
    tmp_path, monkeypatch, creation_umask, expected_mode
):
    observed_modes = []
    final_paths = []

    def fake_stream_download(
        url, target_path, *, progress=None, retry_rate_limited=False
    ):
        operation_path = Path(target_path)
        observed_modes.append(operation_path.stat().st_mode & 0o777)
        operation_path.write_bytes(b"downloaded audio bytes")

    def fake_tag(filename, root_dir, final_file, *args):
        final_paths.append(Path(final_file))
        os.replace(filename, final_file)

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", fake_tag)

    previous_umask = os.umask(creation_umask)
    try:
        Download(
            FakeDownloadClient(),
            "track-1",
            str(tmp_path),
            27,
            no_cover=True,
        ).download_track()
    finally:
        os.umask(previous_umask)

    assert observed_modes == [expected_mode]
    assert len(final_paths) == 1
    assert final_paths[0].stat().st_mode & 0o777 == expected_mode


def test_tag_interrupt_after_rename_preserves_completed_final_file(
    tmp_path, monkeypatch
):
    operation_paths = []
    final_paths = []
    interrupt = KeyboardInterrupt("interrupted after rename")

    def fake_stream_download(
        url, target_path, *, progress=None, retry_rate_limited=False
    ):
        operation_path = Path(target_path)
        operation_paths.append(operation_path)
        operation_path.write_bytes(b"completed audio bytes")

    def rename_then_interrupt(filename, root_dir, final_file, *args):
        final_path = Path(final_file)
        final_paths.append(final_path)
        os.replace(filename, final_file)
        raise interrupt

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", rename_then_interrupt)

    with pytest.raises(KeyboardInterrupt) as exc_info:
        Download(
            FakeDownloadClient(),
            "track-1",
            str(tmp_path),
            27,
            no_cover=True,
        ).download_track()

    assert exc_info.value is interrupt
    assert len(operation_paths) == 1
    assert not operation_paths[0].exists()
    assert len(final_paths) == 1
    assert final_paths[0].read_bytes() == b"completed audio bytes"
