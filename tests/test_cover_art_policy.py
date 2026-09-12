import os
import sys
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3

import qobuz_dl.cli as cli
from qobuz_dl import downloader, metadata
from qobuz_dl.core import QobuzDL
from qobuz_dl.db import handle_download_id
from qobuz_dl.downloader import Download, DownloadResult

CONFLICT_MESSAGE = "--embed-art cannot be used with --no-cover"


def _write_fake_flac(path):
    streaminfo = bytearray(34)
    streaminfo[0:2] = (4096).to_bytes(2, "big")
    streaminfo[2:4] = (4096).to_bytes(2, "big")
    value = (44100 << 44) | (1 << 41) | (15 << 36)
    streaminfo[10:18] = value.to_bytes(8, "big")
    path.write_bytes(b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + streaminfo)


def _album():
    return {
        "id": "album-1",
        "title": "Album",
        "artist": {"name": "Album Artist"},
        "label": {"name": "Label"},
        "genres_list": ["Rock"],
        "tracks_count": 1,
        "release_date_original": "2024-05-06",
        "copyright": "",
        "image": {"large": "https://img.example.test/cover.jpg"},
    }


def _track():
    album = _album()
    return {
        "id": "track-1",
        "title": "Track",
        "track_number": 1,
        "media_number": 1,
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 96,
        "performer": {"name": "Track Artist"},
        "album": album,
        "copyright": "",
    }


def _tag(codec, temporary, root_dir, final_file, *, embed_art=True):
    album = _album()
    track = _track()
    tagger = metadata.tag_mp3 if codec == "mp3" else metadata.tag_flac
    tagger(
        str(temporary),
        str(root_dir),
        str(final_file),
        track,
        album,
        istrack=True,
        em_image=embed_art,
    )


def _write_temporary_audio(codec, path):
    if codec == "mp3":
        path.write_bytes(b"synthetic mp3 frame bytes")
    else:
        _write_fake_flac(path)


def _embedded_art(codec, path):
    if codec == "mp3":
        return ID3(path, translate=False).getall("APIC")[0].data
    return FLAC(path).pictures[0].data


def _write_valid_config(config_file, *, embed_art=False, no_cover=False):
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        "\n".join(
            [
                "[DEFAULT]",
                "email = user@example.com",
                "password = hashed-password",
                "default_folder = Qobuz Downloads",
                "default_limit = 20",
                "default_quality = 6",
                "no_m3u = false",
                "albums_only = false",
                "no_fallback = false",
                "og_cover = false",
                f"embed_art = {str(embed_art).lower()}",
                f"no_cover = {str(no_cover).lower()}",
                "no_database = false",
                "app_id = 123456",
                "smart_discography = false",
                "folder_format = {albumartist} - {album}",
                "track_format = {tracknumber}. {tracktitle}",
                "secrets = secret-one,secret-two",
            ]
        )
    )


def test_cover_option_validator_rejects_conflict():
    with pytest.raises(ValueError, match=CONFLICT_MESSAGE):
        downloader.validate_cover_options(True, True)


def test_direct_constructors_reject_cover_conflict_before_local_writes(tmp_path):
    download_dir = tmp_path / "downloads"
    database_file = tmp_path / "state" / "downloads.sqlite"

    with pytest.raises(ValueError, match=CONFLICT_MESSAGE):
        QobuzDL(
            directory=download_dir,
            embed_art=True,
            no_cover=True,
            downloads_db=database_file,
        )
    with pytest.raises(ValueError, match=CONFLICT_MESSAGE):
        Download(object(), "track-1", str(download_dir), 27, True, no_cover=True)

    assert not download_dir.exists()
    assert not database_file.exists()


def test_raw_cli_cover_conflict_stops_before_first_run_bootstrap(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qobuz-dl",
            "dl",
            "https://play.qobuz.com/album/album-1",
            "--embed-art",
            "--no-cover",
        ],
    )
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: pytest.fail("raw conflict must stop before config bootstrap"),
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert CONFLICT_MESSAGE in capsys.readouterr().err


@pytest.mark.parametrize(
    ("configured_embed", "configured_no_cover", "flag"),
    [
        (True, True, None),
        (True, False, "--no-cover"),
        (False, True, "--embed-art"),
    ],
)
def test_merged_cli_and_config_cover_conflict_stops_before_client(
    monkeypatch,
    tmp_path,
    capsys,
    configured_embed,
    configured_no_cover,
    flag,
):
    config_file = tmp_path / "config" / "config.ini"
    _write_valid_config(
        config_file,
        embed_art=configured_embed,
        no_cover=configured_no_cover,
    )
    argv = ["qobuz-dl", "dl", "https://play.qobuz.com/album/album-1"]
    if flag:
        argv.append(flag)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(tmp_path / "downloads.sqlite")),
    )

    class UnexpectedQobuzDL:
        def __init__(self, *args, **kwargs):
            pytest.fail("merged conflict must stop before client construction")

    monkeypatch.setattr(cli, "QobuzDL", UnexpectedQobuzDL)

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert CONFLICT_MESSAGE in capsys.readouterr().err


@pytest.mark.parametrize("codec", ["mp3", "flac"])
@pytest.mark.parametrize("failure", ["missing", "unreadable", "oversized"])
def test_unavailable_art_is_best_effort_for_both_codecs(
    tmp_path, monkeypatch, caplog, codec, failure
):
    root_dir = tmp_path / codec
    root_dir.mkdir()
    cover = root_dir / "cover.jpg"
    if failure == "oversized":
        with cover.open("wb") as stream:
            stream.truncate(16_777_169)
    elif failure == "unreadable":
        cover.write_bytes(b"unreadable cover")
        real_open = open

        def fail_cover_open(path, *args, **kwargs):
            if os.fspath(path) == str(cover):
                raise OSError("synthetic unreadable cover")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fail_cover_open)

    temporary = root_dir / f"temporary.{codec}"
    final_file = root_dir / f"final.{codec}"
    _write_temporary_audio(codec, temporary)
    caplog.set_level("WARNING", logger="qobuz_dl.metadata")

    _tag(codec, temporary, root_dir, final_file)

    assert final_file.exists()
    assert not temporary.exists()
    if codec == "mp3":
        assert ID3(final_file, translate=False).getall("APIC") == []
    else:
        assert FLAC(final_file).pictures == []
    assert any(
        "Continuing without embedded cover art" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize("codec", ["mp3", "flac"])
def test_art_at_common_inclusive_size_limit_is_embedded(tmp_path, codec):
    root_dir = tmp_path / codec
    root_dir.mkdir()
    cover = root_dir / "cover.jpg"
    payload = b"j" * 16_777_168
    cover.write_bytes(payload)
    temporary = root_dir / f"temporary.{codec}"
    final_file = root_dir / f"final.{codec}"
    _write_temporary_audio(codec, temporary)

    _tag(codec, temporary, root_dir, final_file)

    assert _embedded_art(codec, final_file) == payload


@pytest.mark.parametrize("codec", ["mp3", "flac"])
@pytest.mark.parametrize("local_cover", [True, False])
def test_cover_lookup_prefers_local_then_parent(tmp_path, codec, local_cover):
    album_dir = tmp_path / "album"
    disc_dir = album_dir / "disc"
    disc_dir.mkdir(parents=True)
    (album_dir / "cover.jpg").write_bytes(b"parent cover")
    if local_cover:
        (disc_dir / "cover.jpg").write_bytes(b"local cover")
    temporary = disc_dir / f"temporary.{codec}"
    final_file = disc_dir / f"final.{codec}"
    _write_temporary_audio(codec, temporary)

    _tag(codec, temporary, disc_dir, final_file)

    assert _embedded_art(codec, final_file) == (
        b"local cover" if local_cover else b"parent cover"
    )


class _TrackClient:
    def get_track_url(self, item_id, fmt_id):
        assert (item_id, fmt_id) == ("track-1", 27)
        return {
            "url": "https://media.example.test/track-1.flac",
            "sampling_rate": 96,
            "bit_depth": 24,
        }

    def get_track_meta(self, item_id):
        assert item_id == "track-1"
        return _track()


def test_missing_art_keeps_final_audio_and_records_success(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(downloader, "_get_extra", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        downloader.http,
        "stream_download",
        lambda url, path, **kwargs: _write_fake_flac(Path(path)),
    )
    database_file = tmp_path / "downloads.sqlite"
    qobuz = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        embed_art=True,
        downloads_db=database_file,
    )
    qobuz.client = _TrackClient()
    caplog.set_level("INFO")

    result = qobuz.download_from_id("track-1", album=False)

    expected = (
        tmp_path
        / "music"
        / "Album Artist - Album (2024) [24B-96kHz]"
        / "01. Track.flac"
    )
    assert result == DownloadResult("finalized", "downloaded", (str(expected),))
    assert expected.exists()
    assert FLAC(expected).pictures == []
    assert handle_download_id(database_file, "track-1") == ("track-1",)
    assert sum("Completed" in record.getMessage() for record in caplog.records) == 1


def test_existing_audio_is_not_retagged_when_art_becomes_available(
    tmp_path, monkeypatch
):
    music_dir = tmp_path / "music"
    track_dir = music_dir / "Album Artist - Album (2024) [24B-96kHz]"
    track_dir.mkdir(parents=True)
    final_file = track_dir / "01. Track.flac"
    _write_fake_flac(final_file)

    def write_cover(url, directory, **kwargs):
        Path(directory, "cover.jpg").write_bytes(b"new cover")

    monkeypatch.setattr(downloader, "_get_extra", write_cover)
    monkeypatch.setattr(
        downloader.http,
        "stream_download",
        lambda *args, **kwargs: pytest.fail("existing audio must not transfer"),
    )

    result = Download(
        _TrackClient(),
        "track-1",
        str(music_dir),
        27,
        embed_art=True,
    ).download_track()

    assert result == DownloadResult("finalized", "existing_file", (str(final_file),))
    assert FLAC(final_file).pictures == []


def test_cover_transport_failure_keeps_request_error_semantics(tmp_path, monkeypatch):
    def fail_cover(*args, **kwargs):
        raise ConnectionError("synthetic cover transfer failure")

    monkeypatch.setattr(downloader, "_get_extra", fail_cover)
    monkeypatch.setattr(
        downloader.http,
        "stream_download",
        lambda *args, **kwargs: pytest.fail("media must not transfer"),
    )
    database_file = tmp_path / "downloads.sqlite"
    qobuz = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        embed_art=True,
        downloads_db=database_file,
    )
    qobuz.client = _TrackClient()

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "request_error")
    assert handle_download_id(database_file, "track-1") is None


def test_real_tagging_failure_keeps_tagging_error_semantics(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "_get_extra", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        downloader.http,
        "stream_download",
        lambda url, path, **kwargs: Path(path).write_bytes(b"not a FLAC stream"),
    )
    database_file = tmp_path / "downloads.sqlite"
    qobuz = QobuzDL(
        directory=tmp_path / "music",
        quality=27,
        embed_art=True,
        downloads_db=database_file,
    )
    qobuz.client = _TrackClient()

    result = qobuz.download_from_id("track-1", album=False)

    assert result == DownloadResult("failed", "tagging_error")
    assert handle_download_id(database_file, "track-1") is None
    assert not list((tmp_path / "music").rglob("*.flac"))
    assert not list((tmp_path / "music").rglob(".*.tmp"))
