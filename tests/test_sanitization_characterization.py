import os

import qobuz_dl.downloader as downloader
from qobuz_dl.core import QobuzDL
from qobuz_dl.downloader import Download
from qobuz_dl.sanitize import sanitize_filename, sanitize_filepath


def test_album_and_artist_folder_attrs_use_current_pathvalidate_filename_behavior():
    meta = {
        "artist": {"name": "Artist: A/B?*"},
        "release_date_original": "2024-01-02",
    }

    attrs = Download._get_album_attr(
        meta,
        album_title="Album: Name/Part?*",
        file_format="FLAC",
        bit_depth=24,
        sampling_rate=96,
    )

    assert attrs["artist"] == "Artist AB"
    assert attrs["albumartist"] == "Artist AB"
    assert attrs["album"] == "Album NamePart"
    assert (
        sanitize_filepath(
            "{albumartist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]".format(
                **attrs
            )
        )
        == "Artist AB - Album NamePart (2024) [24B-96kHz]"
    )


def test_track_folder_and_filename_generation_sanitize_illegal_names():
    meta = {
        "album": {
            "title": "Album: Name/Part?*",
            "artist": {"name": "Album Artist: Bad/Name?*"},
            "release_date_original": "2024-01-02",
        }
    }
    track_metadata = {
        "title": "Track: Name/Part?*",
        "performer": {"name": "Track Artist: Bad/Name?*"},
        "album": {"artist": {"name": "Fallback Artist"}},
        "maximum_bit_depth": 24,
        "maximum_sampling_rate": 96,
        "track_number": 3,
        "version": None,
    }

    folder_attrs = Download._get_track_attr(meta, track_metadata["title"], 24, 96)
    filename_attrs = Download._get_filename_attr(
        track_metadata["performer"]["name"], track_metadata, track_metadata["title"]
    )

    assert folder_attrs["album"] == "Album NamePart"
    assert folder_attrs["artist"] == "Album Artist BadName"
    assert folder_attrs["albumartist"] == "Album Artist BadName"
    assert sanitize_filename(
        "{tracknumber}. {artist} - {tracktitle}".format(**filename_attrs)
    ) == ("03. Track Artist BadName - Track NamePart")


def test_empty_and_whitespace_heavy_generated_names_are_currently_empty():
    assert sanitize_filename("   ") == ""
    assert sanitize_filepath("   ") == ""
    assert sanitize_filename('<>:"/\\|?*') == ""

    attrs = Download._get_album_attr(
        {"artist": {"name": "   "}, "release_date_original": "2024-01-02"},
        album_title='<>:"/\\|?*',
        file_format="FLAC",
        bit_depth=16,
        sampling_rate=44.1,
    )

    assert attrs["artist"] == ""
    assert attrs["album"] == ""
    assert sanitize_filepath("{artist}{album}".format(**attrs)) == ""


class FakeTrackClient:
    def get_track_url(self, item_id, fmt_id):
        assert item_id == "track-1"
        assert fmt_id == 27
        return {
            "url": "https://example.invalid/audio.flac",
            "sampling_rate": 96,
            "bit_depth": 24,
        }

    def get_track_meta(self, item_id):
        assert item_id == "track-1"
        return {
            "title": "Track: Name/Part?*",
            "performer": {"name": "Track Artist: Bad/Name?*"},
            "album": {
                "title": "Album: Name/Part?*",
                "artist": {"name": "Album Artist: Bad/Name?*"},
                "release_date_original": "2024-01-02",
                "image": {"large": "https://example.invalid/cover.jpg"},
            },
            "maximum_bit_depth": 24,
            "maximum_sampling_rate": 96,
            "track_number": 3,
            "version": None,
        }


def test_download_track_sanitizes_folder_and_final_file_paths(tmp_path, monkeypatch):
    downloaded = []
    tagged = []

    def fake_download_with_progress(url, fname, desc):
        downloaded.append((url, fname, desc))

    def fake_tag_flac(
        filename,
        root_dir,
        final_file,
        track_metadata,
        album_or_track_metadata,
        is_track,
        embed_art,
    ):
        tagged.append(
            (
                filename,
                root_dir,
                final_file,
                track_metadata,
                album_or_track_metadata,
                is_track,
                embed_art,
            )
        )

    monkeypatch.setattr(
        downloader, "download_with_progress", fake_download_with_progress
    )
    monkeypatch.setattr(downloader.metadata, "tag_flac", fake_tag_flac)

    download = Download(
        FakeTrackClient(),
        "track-1",
        str(tmp_path),
        27,
        no_cover=True,
        track_format="{tracknumber}. {artist} - {tracktitle}",
    )

    download.download_track()

    expected_dir = os.path.join(
        str(tmp_path), "Album Artist BadName - Album NamePart (2024) [24B-96kHz]"
    )
    expected_tmp = os.path.join(expected_dir, ".01.tmp")
    expected_final = os.path.join(
        expected_dir, "03. Track Artist BadName - Track NamePart.flac"
    )

    assert os.path.isdir(expected_dir)
    assert downloaded == [
        ("https://example.invalid/audio.flac", expected_tmp, expected_tmp)
    ]
    assert tagged[0][0] == expected_tmp
    assert tagged[0][1] == expected_dir
    assert tagged[0][2] == expected_final
    assert tagged[0][5] is True


def test_playlist_and_artist_handle_url_directories_are_sanitized(
    tmp_path, monkeypatch
):
    qdl = QobuzDL(directory=tmp_path, no_m3u_for_playlists=True)
    downloaded = []

    qdl.download_from_id = lambda item_id, album=True, alt_path=None: downloaded.append(
        (item_id, album, alt_path)
    )
    qdl.client = type(
        "Client",
        (),
        {
            "get_plist_meta": lambda self, item_id: iter(
                [
                    {
                        "name": "Playlist: Bad/Name?*",
                        "tracks": {"items": [{"id": "track-1"}]},
                    }
                ]
            ),
            "get_artist_meta": lambda self, item_id: iter(
                [
                    {
                        "name": "Artist: Bad/Name?*",
                        "albums": {"items": [{"id": "album-1"}]},
                    }
                ]
            ),
            "get_label_meta": lambda self, item_id: iter([]),
        },
    )()

    qdl.handle_url("https://play.qobuz.com/playlist/pl-1")
    qdl.handle_url("https://play.qobuz.com/artist/artist-1")

    assert downloaded == [
        ("track-1", False, os.path.join(str(tmp_path), "Playlist BadName")),
        ("album-1", True, os.path.join(str(tmp_path), "Artist BadName")),
    ]
