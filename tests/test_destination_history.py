import errno
import os
import shutil
import stat
from pathlib import Path

import pytest

from qobuz_dl import db, downloader
from qobuz_dl.core import QobuzDL
from qobuz_dl.db import DownloadHistory, MediaProperties, VerifiedArtifact
from qobuz_dl.downloader import Download, DownloadResult

FIXTURES = Path(__file__).parent / "fixtures"


def _flac_fixture(*, bit_depth=16, sample_rate_hz=44100):
    fixture = bytearray((FIXTURES / "synthetic-silence.flac").read_bytes())
    if (bit_depth, sample_rate_hz) == (16, 44100):
        return bytes(fixture)
    stream_info = int.from_bytes(fixture[18:26], "big")
    channels = (stream_info >> 41) & 0b111
    total_samples = stream_info & ((1 << 36) - 1)
    stream_info = (
        (sample_rate_hz << 44)
        | (channels << 41)
        | ((bit_depth - 1) << 36)
        | total_samples
    )
    fixture[18:26] = stream_info.to_bytes(8, "big")
    return bytes(fixture)


def _track_metadata(track_id="track-1", title="Track"):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Track Artist"},
        "album": {
            "id": "album-1",
            "title": "Album",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-01-02",
            "image": {"large": "https://images.example.test/cover.jpg"},
            "tracks_count": 1,
            "genres_list": ["Rock"],
            "label": {"name": "Label"},
        },
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 192,
        "track_number": 1,
        "media_number": 1,
        "version": None,
        "copyright": "",
    }


def _album_metadata(tracks):
    return {
        "id": "album-1",
        "streamable": True,
        "release_type": "album",
        "title": "Album",
        "artist": {"name": "Album Artist"},
        "release_date_original": "2024-01-02",
        "image": {"large": "https://images.example.test/cover.jpg"},
        "tracks": {"items": tracks},
        "tracks_count": len(tracks),
        "genres_list": ["Rock"],
        "label": {"name": "Label"},
        "copyright": "",
    }


class _Client:
    def __init__(self):
        self.urls = {}
        self.metadata = {}

    def get_track_url(self, track_id, fmt_id):
        return self.urls.get(
            track_id,
            {
                "url": f"https://media.example.test/{track_id}.flac",
                "sampling_rate": 44.1,
                "bit_depth": 16,
                "format_id": 6,
                "mime_type": "audio/flac",
            },
        )

    def get_track_meta(self, track_id):
        return self.metadata.get(track_id, _track_metadata(track_id))

    def get_album_meta(self, album_id):
        assert album_id == "album-1"
        tracks = self.metadata.values() or [_track_metadata()]
        return _album_metadata(list(tracks))


def _install_real_flac_download(monkeypatch):
    transfers = []

    def copy_fixture(
        url,
        filename,
        _description,
        *,
        retry_rate_limited=False,
        bandwidth_limit=None,
    ):
        transfers.append(url)
        if "hires" not in url:
            Path(filename).write_bytes(_flac_fixture())
            return
        Path(filename).write_bytes(_flac_fixture(bit_depth=24, sample_rate_hz=96000))

    def publish(filename, _root, final_name, *_args, finalize=True):
        if finalize:
            os.replace(filename, final_name)

    monkeypatch.setattr(downloader, "download_with_progress", copy_fixture)
    monkeypatch.setattr(downloader.metadata, "tag_flac", publish)
    return transfers


def _qobuz(tmp_path, *, database=True):
    qobuz = QobuzDL(
        directory=tmp_path / "music",
        quality=6,
        no_cover=True,
        downloads_db=tmp_path / "history.sqlite" if database else None,
        folder_format="album",
        track_format="{tracknumber}. {tracktitle}",
    )
    qobuz.client = _Client()
    return qobuz


def _prepare_hires_replacement(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1-hires.flac",
        "sampling_rate": 96,
        "bit_depth": 24,
        "format_id": 27,
        "mime_type": "audio/flac",
    }
    return qobuz, final_path, old_bytes, transfers


def test_direct_track_reuses_only_fresh_verified_same_media(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)

    first = qobuz.download_from_id("track-1", album=False)
    second = qobuz.download_from_id("track-1", album=False)

    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    assert first == DownloadResult("finalized", "downloaded", (str(final_path),))
    assert second == DownloadResult(
        "finalized", "verified_artifact", (str(final_path),)
    )
    assert transfers == ["https://media.example.test/track-1.flac"]


def test_no_db_reuses_artifact_from_the_same_run(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)

    first = qobuz.download_from_id("track-1", album=False)
    second = qobuz.download_from_id("track-1", album=False)

    assert first.reason == "downloaded"
    assert second.reason == "verified_artifact"
    assert len(transfers) == 1
    assert qobuz.downloads_db is None


def test_no_db_operation_makes_no_sqlite_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db.sqlite3,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("SQLite access in --no-db mode"),
    )
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)

    first = qobuz.download_from_id("track-1", album=False)
    second = qobuz.download_from_id("track-1", album=False)

    assert first.reason == "downloaded"
    assert second.reason == "verified_artifact"
    assert len(transfers) == 1


@pytest.mark.parametrize("occupied_kind", ["file", "symlink", "directory"])
def test_unknown_occupied_destination_is_a_conflict(
    tmp_path, monkeypatch, occupied_kind
):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    final_path.parent.mkdir(parents=True)
    if occupied_kind == "file":
        final_path.write_bytes(b"unknown")
    elif occupied_kind == "directory":
        final_path.mkdir()
    else:
        target = tmp_path / "target.flac"
        shutil.copyfile(FIXTURES / "synthetic-silence.flac", target)
        try:
            final_path.symlink_to(target)
        except OSError as error:
            pytest.skip(f"symlink creation unavailable: {error}")

    before = final_path.lstat()
    symlink_target = os.readlink(final_path) if final_path.is_symlink() else None
    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "path_conflict")
    assert final_path.lstat() == before
    if occupied_kind == "file":
        assert final_path.read_bytes() == b"unknown"
    elif occupied_kind == "directory":
        assert final_path.is_dir() and not final_path.is_symlink()
    else:
        assert final_path.is_symlink()
        assert os.readlink(final_path) == symlink_target
    assert transfers == []


def test_deleted_evidence_downloads_the_missing_path_again(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    final_path.unlink()

    second = qobuz.download_from_id("track-1", album=False)

    assert second.reason == "downloaded"
    assert final_path.is_file()
    assert len(transfers) == 2


def test_legacy_id_without_artifact_does_not_block_direct_download(
    tmp_path, monkeypatch
):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    qobuz.download_history.record_legacy_id("track-1")

    result = qobuz.download_from_id("track-1", album=False)

    assert result.reason == "downloaded"
    assert len(transfers) == 1


def test_replaced_evidence_conflicts_without_touching_the_unknown_file(
    tmp_path, monkeypatch
):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    replacement = bytearray(final_path.read_bytes())
    replacement[-1] ^= 1
    final_path.write_bytes(replacement)

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "path_conflict")
    assert final_path.read_bytes() == replacement
    assert len(transfers) == 1


def test_effective_media_change_rejects_mismatched_replacement_and_keeps_old(
    tmp_path, monkeypatch
):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1-wrong.flac",
        "sampling_rate": 96,
        "bit_depth": 24,
        "format_id": 27,
        "mime_type": "audio/flac",
    }

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "media_error")
    assert final_path.read_bytes() == old_bytes
    assert len(transfers) == 2


def test_requested_quality_and_fallback_flag_are_only_provenance(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    qobuz.quality_fallback = True
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1-fallback.flac",
        "sampling_rate": 44.1,
        "bit_depth": 16,
        "format_id": 6,
        "mime_type": "audio/flac",
        "restrictions": [{"code": downloader.QL_DOWNGRADE}],
    }
    first = qobuz.download_from_id("track-1", album=False)
    qobuz.quality = 27
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1-full.flac",
        "sampling_rate": 44.1,
        "bit_depth": 16,
        "format_id": 27,
        "mime_type": "audio/flac",
    }

    second = qobuz.download_from_id("track-1", album=False)

    assert first.reason == "downloaded"
    assert second.reason == "verified_artifact"
    assert len(transfers) == 1


def test_two_track_ids_resolving_to_one_path_conflict(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    qobuz.client.metadata["track-2"] = _track_metadata("track-2")

    first = qobuz.download_from_id("track-1", album=False)
    second = qobuz.download_from_id("track-2", album=False)

    assert first.reason == "downloaded"
    assert second == DownloadResult("failed", "path_conflict")
    assert len(transfers) == 1


@pytest.mark.parametrize(
    ("attribute", "template"),
    [
        ("folder_format", "other album"),
        ("track_format", "copy {tracknumber}. {tracktitle}"),
    ],
)
def test_changed_template_creates_a_new_destination(
    tmp_path, monkeypatch, attribute, template
):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    setattr(qobuz, attribute, template)

    second = qobuz.download_from_id("track-1", album=False)

    assert first.reason == "downloaded"
    assert second.reason == "downloaded"
    assert Path(first.finalized_paths[0]).is_file()
    assert Path(second.finalized_paths[0]).is_file()
    assert first.finalized_paths != second.finalized_paths
    assert len(transfers) == 2


def _force_known_replacement(monkeypatch, qobuz, final_path):
    artifact = qobuz.download_history.verified_artifact("track-1", final_path)
    assert artifact is not None
    monkeypatch.setattr(
        downloader.Download,
        "_destination_decision",
        lambda *_args, **_kwargs: downloader.Replace(artifact),
    )


@pytest.mark.parametrize(
    ("failure_point", "reason"),
    [
        ("stream", "request_error"),
        ("tag", "tagging_error"),
        ("inspection", "media_error"),
        ("publication", "publish_error"),
    ],
)
def test_known_replacement_failures_preserve_old_artifact(
    tmp_path, monkeypatch, failure_point, reason
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    _force_known_replacement(monkeypatch, qobuz, final_path)

    if failure_point == "stream":

        def fail_stream(*_args, **_kwargs):
            raise ConnectionError("stream failed")

        monkeypatch.setattr(downloader, "download_with_progress", fail_stream)
    elif failure_point == "tag":

        def fail_tag(*_args, **_kwargs):
            raise RuntimeError("tag failed")

        monkeypatch.setattr(downloader.metadata, "tag_flac", fail_tag)
    elif failure_point == "inspection":
        monkeypatch.setattr(
            DownloadHistory, "inspect_artifact", lambda *_args, **_kwargs: None
        )
    else:

        def fail_publication(source, destination):
            if Path(destination) == final_path:
                raise OSError("publication failed")

        monkeypatch.setattr(downloader.os, "link", fail_publication)

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", reason)
    assert final_path.read_bytes() == old_bytes
    assert qobuz.download_history.verified_artifact("track-1", final_path) is not None


def test_staged_flush_failure_stops_before_publication_and_preserves_old_artifact(
    tmp_path, monkeypatch
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    _force_known_replacement(monkeypatch, qobuz, final_path)
    publication_attempts = []

    def fail_flush(_descriptor):
        raise OSError("flush failed")

    def capture_publication(source, destination):
        publication_attempts.append((source, destination))

    monkeypatch.setattr(downloader.os, "fsync", fail_flush)
    monkeypatch.setattr(downloader.os, "link", capture_publication)

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "publish_error")
    assert publication_attempts == []
    assert final_path.read_bytes() == old_bytes
    assert qobuz.download_history.verified_artifact("track-1", final_path) is not None


def test_interrupted_replacement_restores_old_artifact(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    _force_known_replacement(monkeypatch, qobuz, final_path)
    real_link = os.link

    def interrupt_after_link(source, destination):
        result = real_link(source, destination)
        if Path(destination) == final_path:
            raise KeyboardInterrupt
        return result

    monkeypatch.setattr(downloader.os, "link", interrupt_after_link)

    with pytest.raises(KeyboardInterrupt):
        qobuz.download_from_id("track-1", album=False)

    assert final_path.read_bytes() == old_bytes
    assert qobuz.download_history.verified_artifact("track-1", final_path) is not None


def test_fresh_different_media_artifact_is_replaced_successfully(tmp_path, monkeypatch):
    derived_path = tmp_path / "derived.flac"
    derived_path.write_bytes(_flac_fixture(bit_depth=24, sample_rate_hz=96000))
    derived = DownloadHistory.inspect_artifact("derived", derived_path, 27)
    assert derived is not None
    assert derived.media.bit_depth == 24
    assert derived.media.sample_rate_hz == 96000

    qobuz, final_path, _old_bytes, transfers = _prepare_hires_replacement(
        tmp_path, monkeypatch
    )

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("finalized", "downloaded", (str(final_path),))
    artifact = qobuz.download_history.verified_artifact("track-1", final_path)
    assert artifact is not None
    assert artifact.media.bit_depth == 24
    assert artifact.media.sample_rate_hz == 96000
    assert transfers == [
        "https://media.example.test/track-1.flac",
        "https://media.example.test/track-1-hires.flac",
    ]
    assert not list(final_path.parent.glob(".qdl-*"))


def test_changed_old_artifact_before_reverify_is_preserved_as_conflict(
    tmp_path, monkeypatch
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    _force_known_replacement(monkeypatch, qobuz, final_path)
    changed = bytearray(final_path.read_bytes())
    changed[-1] ^= 1

    def change_destination_before_publication(
        _filename,
        _root,
        _final_name,
        *_args,
        finalize=True,
    ):
        final_path.write_bytes(changed)

    monkeypatch.setattr(
        downloader.metadata, "tag_flac", change_destination_before_publication
    )

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "path_conflict")
    assert final_path.read_bytes() == bytes(changed)


def test_destination_swap_between_reverify_and_rename_is_kept_private(
    tmp_path, monkeypatch
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    _force_known_replacement(monkeypatch, qobuz, final_path)
    interloper = b"interloper"
    real_rename = os.rename

    def swap_then_rename(source, destination):
        if os.path.abspath(source) == os.path.abspath(final_path):
            final_path.unlink()
            final_path.write_bytes(interloper)
        return real_rename(source, destination)

    monkeypatch.setattr(downloader.os, "rename", swap_then_rename)

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "path_conflict")
    assert not final_path.exists()
    assert _files_equal_to(final_path.parent, interloper)


def test_intervening_destination_creation_is_not_overwritten(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    real_link = os.link

    def create_destination_then_link(source, destination):
        if Path(destination) == final_path:
            Path(destination).write_bytes(b"intervening")
        return real_link(source, destination)

    monkeypatch.setattr(downloader.os, "link", create_destination_then_link)

    result = qobuz.download_from_id("track-1", album=False)

    assert result.state == "failed"
    assert final_path.read_bytes() == b"intervening"


def test_new_publication_does_not_adopt_a_path_swapped_after_link(
    tmp_path, monkeypatch
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    real_link = os.link

    def link_then_replace(source, destination):
        real_link(source, destination)
        Path(destination).unlink()
        Path(destination).write_bytes(b"intervening")

    monkeypatch.setattr(downloader.os, "link", link_then_replace)

    result = qobuz.download_from_id("track-1", album=False)

    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    assert result.state == "failed"
    assert _files_equal_to(final_path.parent, b"intervening")


def test_unsupported_hard_link_uses_verified_exclusive_copy(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    monkeypatch.setattr(
        downloader.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(
            OSError(errno.ENOTSUP, "links unsupported")
        ),
    )

    result = qobuz.download_from_id("track-1", album=False)

    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    assert result == DownloadResult("finalized", "downloaded", (str(final_path),))
    assert DownloadHistory.inspect_artifact("track-1", final_path, 6) is not None


@pytest.mark.skipif(os.name != "posix", reason="POSIX modes require POSIX")
@pytest.mark.parametrize("publication", ["hard_link", "exclusive_copy"])
def test_private_staging_and_publication_use_ordinary_umask_modes(
    tmp_path, monkeypatch, publication
):
    _install_real_flac_download(monkeypatch)
    transfer = downloader.download_with_progress
    qobuz = _qobuz(tmp_path, database=False)
    staged_modes = []
    directory_modes = []

    def capture_modes(*args, **kwargs):
        staged_path = Path(args[1])
        staged_modes.append(stat.S_IMODE(staged_path.stat().st_mode))
        directory_modes.append(stat.S_IMODE(staged_path.parent.stat().st_mode))
        return transfer(*args, **kwargs)

    monkeypatch.setattr(downloader, "download_with_progress", capture_modes)
    if publication == "exclusive_copy":
        monkeypatch.setattr(
            downloader.os,
            "link",
            lambda *_args: (_ for _ in ()).throw(OSError(errno.EXDEV, "no links")),
        )

    previous_umask = os.umask(0o027)
    try:
        result = qobuz.download_from_id("track-1", album=False)
    finally:
        os.umask(previous_umask)

    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    assert result == DownloadResult("finalized", "downloaded", (str(final_path),))
    assert directory_modes == [0o700]
    assert staged_modes == [0o640]
    assert stat.S_IMODE(final_path.stat().st_mode) == 0o640


def test_interrupted_copy_publication_removes_only_owned_partial(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    monkeypatch.setattr(
        downloader.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EXDEV, "no links")),
    )

    def interrupt_copy(_source, destination):
        destination.write(b"partial")
        raise KeyboardInterrupt

    monkeypatch.setattr(downloader.shutil, "copyfileobj", interrupt_copy)

    with pytest.raises(KeyboardInterrupt):
        qobuz.download_from_id("track-1", album=False)

    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    assert not final_path.exists()
    assert list(final_path.parent.glob(".qdl-*"))


def test_copy_publication_does_not_adopt_intervening_path(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    monkeypatch.setattr(
        downloader.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EXDEV, "no links")),
    )
    real_copy = downloader._DestinationTransaction._copy_no_clobber
    swapped = False

    def copy_then_interleave(transaction, source, destination):
        nonlocal swapped
        real_copy(transaction, source, destination)
        interloper = Path(destination).with_name("interloper")
        interloper.write_bytes(b"intervening")
        os.replace(interloper, destination)
        swapped = True

    monkeypatch.setattr(
        downloader._DestinationTransaction,
        "_copy_no_clobber",
        copy_then_interleave,
    )

    result = qobuz.download_from_id("track-1", album=False)

    assert swapped
    assert result.state == "failed"
    assert _files_equal_to(final_path.parent, b"intervening")


def _files_equal_to(root, expected):
    matches = []
    for path in root.rglob("*"):
        try:
            if (
                path.is_file()
                and not path.is_symlink()
                and path.read_bytes() == expected
            ):
                matches.append(path)
        except OSError:
            pass
    return matches


def test_replacement_interloper_after_backup_move_survives(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    _force_known_replacement(monkeypatch, qobuz, final_path)
    real_rename = os.rename

    def move_then_interlope(source, destination):
        result = real_rename(source, destination)
        if os.path.abspath(source) == os.path.abspath(final_path):
            final_path.write_bytes(b"interloper")
        return result

    monkeypatch.setattr(downloader.os, "rename", move_then_interlope)

    result = qobuz.download_from_id("track-1", album=False)

    assert result.state == "failed"
    assert final_path.read_bytes() == b"interloper"
    assert _files_equal_to(final_path.parent, old_bytes)


def test_changed_publication_is_not_recorded_and_keeps_recovery(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    _force_known_replacement(monkeypatch, qobuz, final_path)
    real_link = os.link

    def corrupt_after_link(source, destination):
        result = real_link(source, destination)
        if os.path.abspath(destination) == os.path.abspath(final_path):
            final_path.write_bytes(b"foreign")
        return result

    monkeypatch.setattr(downloader.os, "link", corrupt_after_link)

    result = qobuz.download_from_id("track-1", album=False)

    assert result.state == "failed"
    restored = qobuz.download_history.verified_artifact("track-1", final_path)
    assert restored is not None
    assert restored.media.bit_depth == 16
    assert restored.media.sample_rate_hz == 44100
    assert _files_equal_to(final_path.parent, old_bytes)


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("phase", ["publish", "restore"])
def test_base_exception_never_deletes_only_old_backup(
    tmp_path, monkeypatch, interruption, phase
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    _force_known_replacement(monkeypatch, qobuz, final_path)
    real_link = os.link
    link_calls = 0
    real_copy = shutil.copyfileobj

    def interrupt_link(source, destination):
        nonlocal link_calls
        if os.path.abspath(destination) == os.path.abspath(final_path):
            link_calls += 1
            if link_calls == 1:
                if phase == "publish":
                    real_link(source, destination)
                    raise interruption
                raise OSError(errno.EIO, "force recovery")
        return real_link(source, destination)

    def interrupt_restore(source, destination):
        if phase == "restore" and Path(source.name).name.startswith("backup"):
            raise interruption
        return real_copy(source, destination)

    monkeypatch.setattr(downloader.os, "link", interrupt_link)
    monkeypatch.setattr(downloader.shutil, "copyfileobj", interrupt_restore)

    with pytest.raises(interruption):
        qobuz.download_from_id("track-1", album=False)

    assert _files_equal_to(final_path.parent, old_bytes)


def test_shared_path_swap_during_cleanup_preserves_unknown_file(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    real_inspect = DownloadHistory.inspect_artifact
    real_rename = os.rename

    monkeypatch.setattr(
        downloader.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EXDEV, "no links")),
    )

    def fail_final_inspection(track_id, path, requested_quality):
        if os.path.abspath(path) == os.path.abspath(final_path):
            return None
        return real_inspect(track_id, path, requested_quality)

    def swap_during_quarantine(source, destination):
        if os.path.abspath(source) == os.path.abspath(final_path):
            os.unlink(source)
            final_path.write_bytes(b"unknown")
        return real_rename(source, destination)

    monkeypatch.setattr(DownloadHistory, "inspect_artifact", fail_final_inspection)
    monkeypatch.setattr(downloader.os, "rename", swap_during_quarantine)

    result = qobuz.download_from_id("track-1", album=False)

    assert result.state == "failed"
    assert _files_equal_to(final_path.parent, b"unknown")


def test_hard_link_publication_changed_in_place_cannot_finalize(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    real_link = os.link

    def corrupt_linked_file(source, destination):
        result = real_link(source, destination)
        if os.path.abspath(destination) == os.path.abspath(final_path):
            final_path.write_bytes(b"foreign")
        return result

    monkeypatch.setattr(downloader.os, "link", corrupt_linked_file)

    result = qobuz.download_from_id("track-1", album=False)

    assert result.state == "failed"


def test_decoy_public_staging_symlink_is_untouched_by_private_workspace(
    tmp_path, monkeypatch
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    unrelated = tmp_path / "unrelated"
    unrelated.write_bytes(b"keep me")
    final_path.parent.mkdir(parents=True)
    decoy = final_path.parent / ".qdl-public.tmp"
    try:
        decoy.symlink_to(unrelated)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    transfer = downloader.download_with_progress
    staged_paths = []

    def capture_private_stage(*args, **kwargs):
        staged_paths.append(Path(args[1]))
        return transfer(*args, **kwargs)

    monkeypatch.setattr(downloader, "download_with_progress", capture_private_stage)

    result = qobuz.download_from_id("track-1", album=False)

    assert result.state == "finalized"
    assert len(staged_paths) == 1
    assert staged_paths[0].parent.parent == final_path.parent
    assert staged_paths[0].parent != final_path.parent
    assert decoy.is_symlink()
    assert os.readlink(decoy) == str(unrelated)
    assert unrelated.read_bytes() == b"keep me"


def test_history_receives_the_exact_proven_final_artifact(tmp_path, monkeypatch):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    final_path = tmp_path / "music" / "album" / "01. Track.flac"
    real_inspect = DownloadHistory.inspect_artifact
    proven = []
    recorded = []

    def capture_final_inspection(track_id, path, requested_quality):
        artifact = real_inspect(track_id, path, requested_quality)
        if os.path.abspath(path) == os.path.abspath(final_path):
            proven.append(artifact)
        return artifact

    def capture_recording(artifact):
        recorded.append(artifact)
        return artifact

    monkeypatch.setattr(DownloadHistory, "inspect_artifact", capture_final_inspection)
    monkeypatch.setattr(qobuz.download_history, "record_verified", capture_recording)

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("finalized", "downloaded", (str(final_path),))
    assert len(proven) == 1
    assert recorded == [proven[0]]
    assert recorded[0] is proven[0]


@pytest.mark.parametrize("returned", [None, object()])
def test_unexpected_history_result_preserves_new_and_old_media(
    tmp_path, monkeypatch, returned
):
    qobuz, final_path, old_bytes, _transfers = _prepare_hires_replacement(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        qobuz.download_history, "record_verified", lambda _artifact: returned
    )

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "publish_error")
    assert final_path.read_bytes() == _flac_fixture(bit_depth=24, sample_rate_hz=96000)
    assert _files_equal_to(final_path.parent, old_bytes)


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_interrupted_history_record_preserves_published_and_prior_media(
    tmp_path, monkeypatch, interruption
):
    qobuz, final_path, old_bytes, _transfers = _prepare_hires_replacement(
        tmp_path, monkeypatch
    )
    real_record = qobuz.download_history.record_verified

    def record_then_interrupt(artifact):
        recorded = real_record(artifact)
        assert recorded == artifact
        raise interruption

    monkeypatch.setattr(
        qobuz.download_history, "record_verified", record_then_interrupt
    )

    with pytest.raises(interruption):
        qobuz.download_from_id("track-1", album=False)

    assert final_path.read_bytes() == _flac_fixture(bit_depth=24, sample_rate_hz=96000)
    recorded = qobuz.download_history.verified_artifact("track-1", final_path)
    proven = DownloadHistory.inspect_artifact("track-1", final_path, 6)
    assert recorded == proven
    assert recorded is not None
    assert recorded.media.bit_depth == 24
    assert recorded.media.sample_rate_hz == 96000
    assert _files_equal_to(final_path.parent, old_bytes)


def test_interrupted_commit_cleanup_does_not_roll_back_publication(
    tmp_path, monkeypatch
):
    qobuz, final_path, old_bytes, _transfers = _prepare_hires_replacement(
        tmp_path, monkeypatch
    )

    def interrupt_cleanup(_path):
        raise KeyboardInterrupt

    monkeypatch.setattr(downloader.shutil, "rmtree", interrupt_cleanup)

    with pytest.raises(KeyboardInterrupt):
        qobuz.download_from_id("track-1", album=False)

    assert final_path.read_bytes() == _flac_fixture(bit_depth=24, sample_rate_hz=96000)
    recorded = qobuz.download_history.verified_artifact("track-1", final_path)
    assert recorded is not None
    assert recorded.media.bit_depth == 24
    assert _files_equal_to(final_path.parent, old_bytes)


def test_mp3_effective_media_requires_format_mime_and_320kbps(tmp_path):
    download = Download(object(), "track-1", str(tmp_path), 5, no_cover=True)
    expected = download._expected_media(
        {
            "format_id": 5,
            "mime_type": "audio/mpeg",
            "sampling_rate": 44.1,
        }
    )

    assert expected is not None
    assert (
        download._expected_media({"mime_type": "audio/mpeg", "sampling_rate": 44.1})
        is None
    )
    assert download._expected_media({"format_id": True}) is None
    assert download._expected_media({"format_id": 5.5}) is None


@pytest.mark.parametrize(
    ("bitrate_bps", "matches"),
    [
        (319999, True),
        (320001, True),
        (128000, False),
        (192000, False),
        (256000, False),
    ],
)
def test_mp3_effective_media_matches_only_near_320_kbps(tmp_path, bitrate_bps, matches):
    download = Download(object(), "track-1", str(tmp_path), 5, no_cover=True)
    expected = downloader._ExpectedMedia("mp3", None, 44100, 320000)

    assert (
        download._media_matches(
            expected, MediaProperties("mp3", None, 44100, bitrate_bps)
        )
        is matches
    )


def test_effective_mp3_format_controls_extension_and_tagger(tmp_path, monkeypatch):
    qobuz = _qobuz(tmp_path, database=False)
    qobuz.quality = 27
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1.mp3",
        "format_id": 5,
        "mime_type": "audio/mpeg",
        "sampling_rate": 44.1,
    }
    tagged = []

    def transfer(_url, filename, _description, **_kwargs):
        Path(filename).write_bytes(b"media")

    def tag_mp3(filename, _root, final_name, *_args, finalize=True):
        tagged.append((filename, final_name, finalize))

    def inspect(track_id, path, requested_quality):
        return VerifiedArtifact(
            track_id=str(track_id),
            path=os.path.normcase(os.path.abspath(path)),
            requested_quality=requested_quality,
            media=MediaProperties("mp3", None, 44100, 320000),
            size_bytes=5,
            sha256="0" * 64,
        )

    monkeypatch.setattr(downloader, "download_with_progress", transfer)
    monkeypatch.setattr(downloader.metadata, "tag_mp3", tag_mp3)
    monkeypatch.setattr(
        downloader.metadata,
        "tag_flac",
        lambda *_args, **_kwargs: pytest.fail("effective MP3 used FLAC tagger"),
    )
    monkeypatch.setattr(DownloadHistory, "inspect_artifact", inspect)

    result = qobuz.download_from_id("track-1", album=False)

    final_path = tmp_path / "music" / "album" / "01. Track.mp3"
    assert result == DownloadResult("finalized", "downloaded", (str(final_path),))
    assert final_path.read_bytes() == b"media"
    assert len(tagged) == 1
    assert tagged[0][1:] == (str(final_path), False)


def test_no_fallback_refuses_an_effective_mp3_downgrade(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    qobuz.quality = 27
    qobuz.quality_fallback = False
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1.mp3",
        "format_id": 5,
        "mime_type": "audio/mpeg",
        "sampling_rate": 44.1,
        "restrictions": [{"code": downloader.QL_DOWNGRADE}],
    }

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("ignored", "quality_filter")
    assert transfers == []
    assert not list((tmp_path / "music").rglob("*.mp3"))


def test_legacy_playlist_mode_keeps_requested_codec(tmp_path, monkeypatch):
    client = _Client()
    client.urls["track-1"] = {
        "url": "https://media.example.test/track-1.mp3",
        "format_id": 5,
        "mime_type": "audio/mpeg",
        "sampling_rate": 44.1,
    }
    used_taggers = []

    def transfer(_url, filename, _description, **_kwargs):
        Path(filename).write_bytes(b"legacy")

    def tag_flac(filename, _root, final_name, *_args):
        used_taggers.append("flac")
        os.replace(filename, final_name)

    monkeypatch.setattr(downloader, "download_with_progress", transfer)
    monkeypatch.setattr(downloader.metadata, "tag_flac", tag_flac)
    monkeypatch.setattr(
        downloader.metadata,
        "tag_mp3",
        lambda *_args, **_kwargs: pytest.fail("legacy routing changed codec"),
    )
    download = Download(
        client,
        "track-1",
        str(tmp_path),
        27,
        no_cover=True,
        folder_format="album",
        track_format="{tracktitle}",
        verified_destinations=False,
    )

    result = download.download_track()

    final_path = tmp_path / "album" / "Track.flac"
    assert result == DownloadResult("finalized", "downloaded", (str(final_path),))
    assert used_taggers == ["flac"]
    assert (
        download._expected_media(
            {
                "format_id": 5,
                "mime_type": "audio/flac",
                "sampling_rate": 44.1,
            }
        )
        is None
    )


def test_missing_effective_format_fails_before_transfer(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path, database=False)
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1.flac",
        "sampling_rate": 44.1,
        "bit_depth": 16,
    }

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "media_error")
    assert transfers == []
    assert not list((tmp_path / "music").rglob("*.flac"))


def test_missing_effective_format_preserves_verified_destination(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    first = qobuz.download_from_id("track-1", album=False)
    final_path = Path(first.finalized_paths[0])
    old_bytes = final_path.read_bytes()
    qobuz.client.urls["track-1"] = {
        "url": "https://media.example.test/track-1.flac",
        "sampling_rate": 44.1,
        "bit_depth": 16,
    }

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "media_error")
    assert transfers == ["https://media.example.test/track-1.flac"]
    assert final_path.read_bytes() == old_bytes
    assert qobuz.download_history.verified_artifact("track-1", final_path) is not None


def test_complete_album_rerun_reuses_verified_children(tmp_path, monkeypatch):
    transfers = _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    qobuz.client.metadata = {
        "track-1": _track_metadata("track-1", "First"),
        "track-2": {
            **_track_metadata("track-2", "Second"),
            "track_number": 2,
        },
    }

    first = qobuz.download_from_id("album-1", album=True)
    second = qobuz.download_from_id("album-1", album=True)

    assert first.reason == "downloaded"
    assert second.reason == "verified_artifact"
    assert len(first.finalized_paths) == 2
    assert second.finalized_paths == first.finalized_paths
    assert len(transfers) == 2


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        ("partial", "tagging_error"),
        ("refused", "quality_filter"),
        ("failed", "path_conflict"),
    ],
)
def test_album_outcomes_keep_finalized_child_paths(
    tmp_path, monkeypatch, outcome, reason
):
    _install_real_flac_download(monkeypatch)
    qobuz = _qobuz(tmp_path)
    qobuz.client.metadata = {
        "track-1": _track_metadata("track-1", "First"),
        "track-2": {
            **_track_metadata("track-2", "Second"),
            "track_number": 2,
        },
    }
    first_path = tmp_path / "music" / "album" / "01. First.flac"
    second_path = tmp_path / "music" / "album" / "02. Second.flac"
    if outcome == "partial":

        def fail_second(
            filename,
            _root,
            _final_name,
            track,
            *_args,
            finalize=True,
        ):
            if track["id"] == "track-2":
                raise RuntimeError("tag failed")

        monkeypatch.setattr(downloader.metadata, "tag_flac", fail_second)
    elif outcome == "refused":
        qobuz.quality_fallback = False
        qobuz.client.urls["track-2"] = {
            "url": "https://media.example.test/track-2.flac",
            "sampling_rate": 44.1,
            "bit_depth": 16,
            "format_id": 6,
            "mime_type": "audio/flac",
            "restrictions": [{"code": downloader.QL_DOWNGRADE}],
        }
    else:
        second_path.parent.mkdir(parents=True)
        second_path.write_bytes(b"unknown")

    result = qobuz.download_from_id("album-1", album=True)

    assert result.state == ("ignored" if outcome == "refused" else "failed")
    assert result.reason == reason
    assert result.finalized_paths == (str(first_path),)
    assert first_path.is_file()
    if outcome == "failed":
        assert second_path.read_bytes() == b"unknown"
