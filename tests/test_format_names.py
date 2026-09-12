import os
from pathlib import Path

import pytest

from qobuz_dl import downloader
from qobuz_dl.downloader import Download, DownloadResult


def _track(track_id="track-1", title="Single Track"):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Track Artist"},
        "album": {"artist": {"name": "Album Artist"}},
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 96,
        "track_number": 1,
        "media_number": 1,
        "version": None,
        "copyright": "",
    }


def _album_meta():
    tracks = [_track()]
    return {
        "id": "album-1",
        "streamable": True,
        "release_type": "album",
        "title": "Album Title",
        "artist": {"name": "Album Artist"},
        "release_date_original": "2024-02-03",
        "image": {"large": "https://img.example.test/cover.jpg"},
        "tracks": {"items": tracks},
        "tracks_count": len(tracks),
        "genres_list": ["Rock"],
        "label": {"name": "Label"},
        "copyright": "",
    }


def _track_meta():
    return {
        **_track(),
        "album": {
            "id": "track-album",
            "title": "Track Album",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-02-03",
            "image": {"large": "https://img.example.test/cover.jpg"},
            "tracks_count": 1,
            "genres_list": ["Rock"],
        },
    }


class _Client:
    def get_album_meta(self, item_id):
        assert item_id == "album-1"
        return _album_meta()

    def get_track_meta(self, item_id):
        assert item_id == "track-1"
        return _track_meta()

    def get_track_url(self, item_id, fmt_id):
        assert item_id == "track-1"
        extension = "mp3" if fmt_id == 5 else "flac"
        return {
            "url": f"https://media.example.test/{item_id}.{extension}",
            "sampling_rate": 96,
            "bit_depth": 24,
        }


def _install_file_boundaries(monkeypatch):
    transfers = []

    def fake_download(url, filename, description, *, retry_rate_limited=False):
        transfers.append((url, filename, description))
        Path(filename).write_bytes(b"audio")

    def fake_tag(filename, root_dir, final_file, *args):
        os.replace(filename, final_file)

    monkeypatch.setattr(downloader, "download_with_progress", fake_download)
    monkeypatch.setattr(downloader.metadata, "tag_mp3", fake_tag)
    monkeypatch.setattr(downloader.metadata, "tag_flac", fake_tag)
    return transfers


def test_direct_mp3_default_uses_mp3_folder_instead_of_missing_quality(
    tmp_path, monkeypatch
):
    _install_file_boundaries(monkeypatch)
    expected = (
        tmp_path / "Album Artist - Track Album (2024) [MP3]" / "01. Single Track.mp3"
    )

    result = Download(
        _Client(), "track-1", str(tmp_path), 5, no_cover=True
    ).download_track()

    assert result == DownloadResult("finalized", "downloaded", (str(expected),))
    assert expected.read_bytes() == b"audio"
    assert "NoneB-NonekHz" not in str(expected)


def test_direct_mp3_keeps_valid_custom_folder_format(tmp_path, monkeypatch):
    _install_file_boundaries(monkeypatch)
    expected = tmp_path / "Album Artist - Track Album portable" / "Single Track.mp3"

    result = Download(
        _Client(),
        "track-1",
        str(tmp_path),
        5,
        no_cover=True,
        folder_format="{albumartist} - {album} portable",
        track_format="{tracktitle}",
    ).download_track()

    assert result == DownloadResult("finalized", "downloaded", (str(expected),))
    assert expected.read_bytes() == b"audio"


@pytest.mark.parametrize(
    (
        "item_id",
        "is_album",
        "quality",
        "requested_suffix",
        "extension",
        "directory",
    ),
    [
        (
            "track-1",
            False,
            5,
            ".mp3",
            ".mp3",
            "Album Artist - Track Album (2024) [MP3]",
        ),
        (
            "album-1",
            True,
            5,
            ".flac",
            ".mp3",
            "Album Artist - Album Title (2024) [MP3]",
        ),
        (
            "track-1",
            False,
            27,
            ".mp3",
            ".flac",
            "Album Artist - Track Album (2024) [24B-96kHz]",
        ),
        (
            "album-1",
            True,
            27,
            ".flac",
            ".flac",
            "Album Artist - Album Title (2024) [24B-96kHz]",
        ),
    ],
)
def test_album_and_direct_formats_produce_one_audio_extension_and_stable_path(
    tmp_path,
    monkeypatch,
    item_id,
    is_album,
    quality,
    requested_suffix,
    extension,
    directory,
):
    transfers = _install_file_boundaries(monkeypatch)
    track_format = f"{{tracknumber}}. {{tracktitle}}{requested_suffix}"
    expected = tmp_path / directory / f"01. Single Track{extension}"
    download = Download(
        _Client(),
        item_id,
        str(tmp_path),
        quality,
        no_cover=True,
        track_format=track_format,
    )

    first = download.download_release() if is_album else download.download_track()
    repeated = download.download_release() if is_album else download.download_track()

    assert first == DownloadResult("finalized", "downloaded", (str(expected),))
    assert repeated == DownloadResult("finalized", "existing_file", (str(expected),))
    assert expected.read_bytes() == b"audio"
    assert not Path(f"{expected}{extension}").exists()
    assert download.track_format == track_format
    assert len(transfers) == 1
