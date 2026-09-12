import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from mutagen.flac import FLAC

from qobuz_dl import downloader
from qobuz_dl.downloader import Download, DownloadResult

APPDATA_DIAGNOSTIC = (
    "APPDATA is not set. Set APPDATA to your Windows application-data "
    "directory and retry."
)
ENVIRONMENT_SECRET = "native-environment-secret"
ALBUM_DIRECTORY = "Album Artist - Track Album (2024) [24B-96kHz]"
UNICODE_TITLE = "界" * 400
UNICODE_COLLISION_CASES = (
    (f"{UNICODE_TITLE}A", "a185b41744ff27089bc40cdd653bc6c8"),
    (f"{UNICODE_TITLE}B", "02964d7937b74d403bfa77ad85251dc8"),
)

NATIVE_WINDOWS_CHILD = r"""
import builtins
import sys

import qobuz_dl
import qobuz_dl.cli as cli


def unexpected(*args, **kwargs):
    raise AssertionError("prompt, config, or network work ran")


builtins.input = unexpected
cli.getpass.getpass = unexpected
cli._ensure_config_exists = unexpected
cli._load_config_values = unexpected
cli._reset_config = unexpected
cli.Bundle = unexpected
cli.QobuzDL = unexpected
sys.argv = ["qobuz-dl", *sys.argv[1:]]
qobuz_dl.main()
"""


def _run_native_windows_cli(tmp_path, argv, appdata):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    environment = {
        **os.environ,
        "QOBUZ_DL_TEST_SECRET": ENVIRONMENT_SECRET,
    }
    if appdata is None:
        environment.pop("APPDATA", None)
    else:
        environment["APPDATA"] = appdata

    result = subprocess.run(
        [sys.executable, "-B", "-I", "-c", NATIVE_WINDOWS_CHILD, *argv],
        cwd=sandbox,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    side_effects = sorted(str(path.relative_to(sandbox)) for path in sandbox.rglob("*"))
    return result, side_effects


def _assert_no_diagnostic_leak(result, tmp_path):
    output = f"{result.stdout}\n{result.stderr}"
    assert "Traceback" not in output
    assert ENVIRONMENT_SECRET not in output
    assert str(tmp_path) not in output


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows")
@pytest.mark.parametrize("appdata", [None, ""], ids=["missing", "empty"])
@pytest.mark.parametrize(
    ("argv", "expected_output"),
    [
        (["--help"], "Download and organize Qobuz music"),
        (["--version"], f"qobuz-dl {version('qobuz-dl')}"),
        (["dl", "--help"], "Download Qobuz album, track, artist"),
        (["fun", "--help"], "Interactively search Qobuz"),
        (["lucky", "--help"], "Search Qobuz and download the first"),
    ],
    ids=["root-help", "version", "dl-help", "fun-help", "lucky-help"],
)
def test_native_windows_metadata_routes_ignore_missing_appdata(
    tmp_path, appdata, argv, expected_output
):
    result, side_effects = _run_native_windows_cli(tmp_path, argv, appdata)

    _assert_no_diagnostic_leak(result, tmp_path)
    assert (
        result.returncode,
        result.stderr,
        expected_output in result.stdout,
        side_effects,
    ) == (0, "", True, [])


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows")
@pytest.mark.parametrize("appdata", [None, ""], ids=["missing", "empty"])
@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no-args"),
        pytest.param(["--reset"], id="reset"),
        pytest.param(["--purge"], id="purge"),
        pytest.param(["--show-config"], id="show-config"),
        pytest.param(["dl", "https://play.qobuz.com/album/example"], id="dl"),
        pytest.param(["fun"], id="fun"),
        pytest.param(["lucky", "example"], id="lucky"),
    ],
)
def test_native_windows_continuing_routes_report_missing_appdata_safely(
    tmp_path, appdata, argv
):
    result, side_effects = _run_native_windows_cli(tmp_path, argv, appdata)

    _assert_no_diagnostic_leak(result, tmp_path)
    assert (
        result.returncode,
        result.stdout,
        result.stderr,
        side_effects,
    ) == (1, "", f"{APPDATA_DIAGNOSTIC}\n", [])


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows")
@pytest.mark.parametrize("appdata", [None, ""], ids=["missing", "empty"])
def test_native_windows_parser_error_precedes_config_path_resolution(tmp_path, appdata):
    result, side_effects = _run_native_windows_cli(
        tmp_path,
        ["--not-a-real-option"],
        appdata,
    )

    _assert_no_diagnostic_leak(result, tmp_path)
    assert (result.returncode, result.stdout, side_effects) == (2, "", [])
    assert "usage: qobuz-dl" in result.stderr
    assert "error: unrecognized arguments: --not-a-real-option" in result.stderr
    assert APPDATA_DIAGNOSTIC not in result.stderr


def _write_synthetic_flac(path):
    streaminfo = bytearray(34)
    streaminfo[0:2] = (4096).to_bytes(2, "big")
    streaminfo[2:4] = (4096).to_bytes(2, "big")
    value = (44100 << 44) | (1 << 41) | (15 << 36)
    streaminfo[10:18] = value.to_bytes(8, "big")
    path.write_bytes(b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + streaminfo)


def _track_metadata(
    track_id,
    title,
    *,
    artist="Track Artist",
    album_artist="Album Artist",
    album="Track Album",
):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": artist},
        "album": {
            "id": "album-1",
            "title": album,
            "artist": {"name": album_artist},
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


class _LocalTrackClient:
    def __init__(self, track_id, title, **metadata):
        self.metadata = _track_metadata(track_id, title, **metadata)

    def get_track_url(self, item_id, fmt_id):
        assert item_id == self.metadata["id"]
        assert fmt_id == 27
        return {
            "url": f"https://media.example.test/{item_id}.flac",
            "sampling_rate": 96,
            "bit_depth": 24,
        }

    def get_track_meta(self, item_id):
        assert item_id == self.metadata["id"]
        return self.metadata


def _install_fake_media_network(monkeypatch):
    temporary_paths = []

    def fake_stream_download(
        url,
        target_path,
        *,
        progress=None,
        retry_rate_limited=False,
        bandwidth_limit=None,
    ):
        assert url.startswith("https://media.example.test/")
        assert retry_rate_limited is True
        temporary_path = Path(target_path)
        temporary_paths.append(temporary_path)
        _write_synthetic_flac(temporary_path)

    monkeypatch.setattr(downloader.http, "stream_download", fake_stream_download)
    return temporary_paths


def _local_download(tmp_path, track_id, title, **metadata):
    return Download(
        _LocalTrackClient(track_id, title, **metadata),
        track_id,
        str(tmp_path),
        27,
        no_cover=True,
        track_format="{tracktitle}",
    )


def _assert_owned_temporary(path, destination):
    assert path.parent == destination
    assert path.name.startswith(".qdl-")
    assert path.name.endswith(".tmp")
    token = path.name.removeprefix(".qdl-").removesuffix(".tmp")
    assert len(token) == 32
    int(token, 16)
    assert not path.exists()


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows")
@pytest.mark.parametrize(
    ("track_id", "title", "expected_component"),
    [
        ("track-ordinary", "Ordinary title", "Ordinary title.flac"),
        (
            "track-reserved",
            "CON.txt",
            "track-515047d8f483c4a6df7f0f8f5e0abc01.flac",
        ),
        ("track-empty", "<>", "track-86ea5b6f5c94b841cbd724807198bde4.flac"),
    ],
    ids=["ordinary", "reserved", "empty"],
)
def test_native_windows_download_finalizes_stable_safe_files(
    tmp_path, monkeypatch, track_id, title, expected_component
):
    temporary_paths = _install_fake_media_network(monkeypatch)
    destination = tmp_path / ALBUM_DIRECTORY
    expected_path = destination / expected_component
    download = _local_download(tmp_path, track_id, title)

    first = download.download_track()
    repeated = download.download_track()

    assert first == DownloadResult("finalized", "downloaded", (str(expected_path),))
    assert repeated == DownloadResult(
        "finalized", "existing_file", (str(expected_path),)
    )
    assert FLAC(expected_path)["TITLE"] == [title]
    assert sorted(path.name for path in destination.iterdir()) == [expected_component]
    assert len(temporary_paths) == 1
    _assert_owned_temporary(temporary_paths[0], destination)


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows")
def test_native_windows_long_unicode_prefixes_create_distinct_final_files(
    tmp_path, monkeypatch
):
    temporary_paths = _install_fake_media_network(monkeypatch)
    destination = tmp_path / ALBUM_DIRECTORY
    expected_paths = tuple(
        destination / f"{'界' * 72}~{digest}.flac"
        for _title, digest in UNICODE_COLLISION_CASES
    )

    results = tuple(
        _local_download(tmp_path, f"track-{index}", title).download_track()
        for index, (title, _digest) in enumerate(UNICODE_COLLISION_CASES, start=1)
    )

    assert results == tuple(
        DownloadResult("finalized", "downloaded", (str(path),))
        for path in expected_paths
    )
    assert [FLAC(path)["TITLE"] for path in expected_paths] == [
        [title] for title, _digest in UNICODE_COLLISION_CASES
    ]
    assert all(len(os.fsencode(path.name)) <= 255 for path in expected_paths)
    assert expected_paths[0] != expected_paths[1]
    assert len(temporary_paths) == 2
    for path in temporary_paths:
        _assert_owned_temporary(path, destination)


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows")
def test_native_windows_name_limit_uses_255_byte_fallback(tmp_path):
    assert downloader._destination_name_max(str(tmp_path)) == 255


@pytest.mark.skipif(sys.platform != "darwin", reason="requires native macOS")
def test_native_macos_unicode_download_tags_renames_and_remains_readable(
    tmp_path, monkeypatch
):
    temporary_paths = _install_fake_media_network(monkeypatch)
    title = "Chanson 東京"
    destination = tmp_path / "Artiste Montréal - Album été"
    expected_path = destination / f"{title}.flac"
    download = Download(
        _LocalTrackClient(
            "track-macos",
            title,
            artist="Artiste Montréal",
            album_artist="Artiste Montréal",
            album="Album été",
        ),
        "track-macos",
        str(tmp_path),
        27,
        no_cover=True,
        folder_format="{artist} - {album}",
        track_format="{tracktitle}",
    )

    result = download.download_track()

    assert result == DownloadResult("finalized", "downloaded", (str(expected_path),))
    audio = FLAC(expected_path)
    assert audio["TITLE"] == [title]
    assert audio["ARTIST"] == ["Artiste Montréal"]
    assert audio["ALBUM"] == ["Album été"]
    assert len(temporary_paths) == 1
    _assert_owned_temporary(temporary_paths[0], destination)
