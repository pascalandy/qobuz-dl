import errno
import os
from pathlib import Path

import pytest

from qobuz_dl import downloader
from qobuz_dl.downloader import Download, DownloadResult

ALBUM_DIRECTORY = "Album Artist - Track Album (2024) [24B-96kHz]"
UNICODE_TITLE = "界" * 400
UNICODE_DIGEST = "021a629ab26f794b630e2893a8fc5652"
UNICODE_COLLISION_CASES = (
    (f"{UNICODE_TITLE}A", "a185b41744ff27089bc40cdd653bc6c8"),
    (f"{UNICODE_TITLE}B", "02964d7937b74d403bfa77ad85251dc8"),
)


def _track_metadata(track_id, title):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Track Artist"},
        "album": {
            "id": "album-1",
            "title": "Track Album",
            "artist": {"name": "Album Artist"},
            "release_date_original": "2024-02-03",
            "image": {"large": "https://img.example.test/cover.jpg"},
            "tracks_count": 1,
            "genres_list": ["Rock"],
        },
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 96,
        "track_number": 1,
        "media_number": 1,
        "version": None,
        "copyright": "",
    }


class _TrackClient:
    def __init__(self, track_id, title, quality=27):
        self.metadata = _track_metadata(track_id, title)
        self.quality = quality

    def get_track_url(self, item_id, fmt_id):
        assert item_id == self.metadata["id"]
        assert fmt_id == self.quality
        return {
            "url": f"https://media.example.test/{item_id}.flac",
            "sampling_rate": 96,
            "bit_depth": 24,
        }

    def get_track_meta(self, item_id):
        assert item_id == self.metadata["id"]
        return self.metadata


def _install_real_file_boundaries(monkeypatch):
    temporary_paths = []

    def fake_stream_download(
        url, target_path, *, progress=None, retry_rate_limited=False
    ):
        temporary_path = Path(target_path)
        temporary_paths.append(temporary_path)
        temporary_path.write_bytes(f"audio:{Path(url).stem}".encode())

    def fake_tag(filename, root_dir, final_file, *args):
        os.replace(filename, final_file)

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    monkeypatch.setattr(downloader.metadata, "tag_flac", fake_tag)
    monkeypatch.setattr(downloader.metadata, "tag_mp3", fake_tag)
    return temporary_paths


def _download(tmp_path, track_id, title):
    return Download(
        _TrackClient(track_id, title),
        track_id,
        str(tmp_path),
        27,
        no_cover=True,
        track_format="{tracktitle}",
    ).download_track()


def _expected_unicode_component(max_bytes, digest=UNICODE_DIGEST):
    suffix = f"~{digest}.flac"
    prefix_bytes = max_bytes - len(os.fsencode(suffix))
    prefix_characters = prefix_bytes // len(os.fsencode("界"))
    return f"{'界' * prefix_characters}{suffix}"


def _assert_owned_temporary(path, destination):
    assert path.parent == destination
    assert path.name.startswith(".qdl-")
    assert path.name.endswith(".tmp")
    token = path.name.removeprefix(".qdl-").removesuffix(".tmp")
    assert len(token) == 32
    int(token, 16)


def test_distinct_empty_components_create_distinct_stable_final_files(
    tmp_path, monkeypatch
):
    temporary_paths = _install_real_file_boundaries(monkeypatch)
    destination = tmp_path / ALBUM_DIRECTORY
    expected_paths = (
        destination / "track-86ea5b6f5c94b841cbd724807198bde4.flac",
        destination / "track-cded6afb3aa9d26a4ae0a0ae9234ec24.flac",
    )

    first = _download(tmp_path, "track-empty-a", "<>")
    second = _download(tmp_path, "track-empty-b", ":?")
    repeated = _download(tmp_path, "track-empty-a", "<>")

    assert first == DownloadResult("finalized", "downloaded", (str(expected_paths[0]),))
    assert second == DownloadResult(
        "finalized", "downloaded", (str(expected_paths[1]),)
    )
    assert repeated == DownloadResult(
        "finalized", "existing_file", (str(expected_paths[0]),)
    )
    assert expected_paths[0].read_bytes() == b"audio:track-empty-a"
    assert expected_paths[1].read_bytes() == b"audio:track-empty-b"
    assert len(temporary_paths) == 2
    assert temporary_paths[0] != temporary_paths[1]
    for temporary_path in temporary_paths:
        _assert_owned_temporary(temporary_path, destination)
        assert not temporary_path.exists()


@pytest.mark.parametrize(
    ("title", "expected_component"),
    [
        ("CON.txt", "track-515047d8f483c4a6df7f0f8f5e0abc01.flac"),
        ("CON .txt", "track-3a5adadb4d47a19a1c05b6e4721a3f99.flac"),
        ("com1 .TXT", "track-ccf7153199fbd2868af3bf2d1e58a0e5.flac"),
        ("com¹.backup", "track-643a6170c8426b482b65614fe2f0af3c.flac"),
        ("LpT² .backup", "track-a1de16120be105bfca2f48059838648b.flac"),
        ("LPT9.hidden", "track-c2cddc04b91b3ae0bf80ba5fa6705738.flac"),
        ("CONCERT", "CONCERT.flac"),
    ],
)
def test_windows_reserved_stems_are_repaired_without_changing_ordinary_names(
    tmp_path, monkeypatch, title, expected_component
):
    _install_real_file_boundaries(monkeypatch)
    expected_path = tmp_path / ALBUM_DIRECTORY / expected_component

    result = _download(tmp_path, "track-1", title)

    assert result == DownloadResult("finalized", "downloaded", (str(expected_path),))
    assert expected_path.read_bytes() == b"audio:track-1"


@pytest.mark.skipif(
    not hasattr(os, "pathconf"), reason="os.pathconf is unavailable on this platform"
)
def test_long_unicode_component_fits_actual_destination_name_limit_by_bytes(
    tmp_path, monkeypatch
):
    temporary_paths = _install_real_file_boundaries(monkeypatch)
    destination = tmp_path / ALBUM_DIRECTORY
    destination.mkdir()
    name_max = os.pathconf(destination, "PC_NAME_MAX")
    expected_path = destination / _expected_unicode_component(name_max)

    result = _download(tmp_path, "track-unicode", UNICODE_TITLE)

    assert result == DownloadResult("finalized", "downloaded", (str(expected_path),))
    assert expected_path.read_bytes() == b"audio:track-unicode"
    assert len(os.fsencode(expected_path.name)) <= name_max
    assert len(os.fsencode(expected_path.name + "界")) > name_max
    assert len(temporary_paths) == 1
    _assert_owned_temporary(temporary_paths[0], destination)
    assert not temporary_paths[0].exists()


@pytest.mark.skipif(
    not hasattr(os, "pathconf"), reason="os.pathconf is unavailable on this platform"
)
def test_long_unicode_titles_with_the_same_prefix_create_distinct_final_files(
    tmp_path, monkeypatch
):
    temporary_paths = _install_real_file_boundaries(monkeypatch)
    destination = tmp_path / ALBUM_DIRECTORY
    destination.mkdir()
    name_max = os.pathconf(destination, "PC_NAME_MAX")
    expected_paths = tuple(
        destination / _expected_unicode_component(name_max, digest)
        for title, digest in UNICODE_COLLISION_CASES
    )

    results = tuple(
        _download(tmp_path, f"track-{index}", title)
        for index, (title, _digest) in enumerate(UNICODE_COLLISION_CASES, start=1)
    )

    assert results == tuple(
        DownloadResult("finalized", "downloaded", (str(expected_path),))
        for expected_path in expected_paths
    )
    assert expected_paths[0].read_bytes() == b"audio:track-1"
    assert expected_paths[1].read_bytes() == b"audio:track-2"
    assert expected_paths[0] != expected_paths[1]
    assert len(temporary_paths) == 2
    for temporary_path in temporary_paths:
        _assert_owned_temporary(temporary_path, destination)
        assert not temporary_path.exists()


@pytest.mark.parametrize(
    "unsupported_limit",
    [-1, OSError(errno.EINVAL, "unsupported")],
    ids=["indeterminate", "unsupported"],
)
def test_unsupported_or_indeterminate_name_limit_uses_255_byte_fallback(
    tmp_path, monkeypatch, unsupported_limit
):
    _install_real_file_boundaries(monkeypatch)
    expected_path = tmp_path / ALBUM_DIRECTORY / _expected_unicode_component(255)

    def fake_pathconf(path, name):
        if isinstance(unsupported_limit, OSError):
            raise unsupported_limit
        return unsupported_limit

    monkeypatch.setattr(os, "pathconf", fake_pathconf, raising=False)

    result = _download(tmp_path, "track-unicode", UNICODE_TITLE)

    assert result == DownloadResult("finalized", "downloaded", (str(expected_path),))
    assert expected_path.read_bytes() == b"audio:track-unicode"
    assert len(os.fsencode(expected_path.name)) <= 255


def test_destination_name_limit_path_errors_propagate(tmp_path, monkeypatch):
    _install_real_file_boundaries(monkeypatch)
    path_error = FileNotFoundError(errno.ENOENT, "destination disappeared")

    def fail_pathconf(path, name):
        raise path_error

    monkeypatch.setattr(os, "pathconf", fail_pathconf, raising=False)

    with pytest.raises(FileNotFoundError) as exc_info:
        _download(tmp_path, "track-1", "Ordinary title")

    assert exc_info.value is path_error


@pytest.mark.parametrize(
    ("quality", "name_max", "extension"),
    [(5, 42, ".mp3"), (27, 43, ".flac")],
)
def test_tight_fallback_limit_allows_owned_temporary_and_stable_final_path(
    tmp_path, monkeypatch, quality, name_max, extension
):
    temporary_paths = _install_real_file_boundaries(monkeypatch)
    destination = tmp_path / ALBUM_DIRECTORY
    expected_path = destination / f"track-86ea5b6f5c94b841cbd724807198bde4{extension}"
    real_open = os.open

    def fake_pathconf(path, name):
        assert Path(path) == destination
        assert name == "PC_NAME_MAX"
        return name_max

    def limit_component_at_open(path, flags, mode=0o777):
        if len(os.fsencode(Path(path).name)) > name_max:
            raise OSError(errno.ENAMETOOLONG, "component exceeds name limit", path)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "pathconf", fake_pathconf, raising=False)
    monkeypatch.setattr(os, "open", limit_component_at_open)
    download = Download(
        _TrackClient("track-tight", "<>", quality),
        "track-tight",
        str(tmp_path),
        quality,
        no_cover=True,
        folder_format=ALBUM_DIRECTORY,
        track_format="{tracktitle}",
    )

    first = download.download_track()
    repeated = download.download_track()

    assert first == DownloadResult("finalized", "downloaded", (str(expected_path),))
    assert repeated == DownloadResult(
        "finalized", "existing_file", (str(expected_path),)
    )
    assert expected_path.read_bytes() == b"audio:track-tight"
    assert len(temporary_paths) == 1
    _assert_owned_temporary(temporary_paths[0], destination)
    assert len(os.fsencode(temporary_paths[0].name)) <= name_max
    assert not temporary_paths[0].exists()


def test_name_limit_smaller_than_complete_fallback_fails_clearly(tmp_path, monkeypatch):
    temporary_paths = _install_real_file_boundaries(monkeypatch)
    monkeypatch.setattr(os, "pathconf", lambda path, name: 42, raising=False)

    with pytest.raises(ValueError) as exc_info:
        _download(tmp_path, "track-empty", "<>")

    assert str(exc_info.value)
    assert temporary_paths == []
    assert not list(tmp_path.rglob("*.flac"))
