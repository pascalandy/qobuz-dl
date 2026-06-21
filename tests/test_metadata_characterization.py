from mutagen.flac import FLAC
from mutagen.id3 import ID3

from qobuz_dl import metadata
from qobuz_dl.utils import make_m3u


def _write_fake_flac(path):
    streaminfo = bytearray(34)
    streaminfo[0:2] = (4096).to_bytes(2, "big")
    streaminfo[2:4] = (4096).to_bytes(2, "big")
    value = (44100 << 44) | (1 << 41) | (15 << 36)
    streaminfo[10:18] = value.to_bytes(8, "big")
    path.write_bytes(b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + streaminfo)


def _fake_album():
    return {
        "id": "album-1",
        "title": "Fake Album",
        "artist": {"name": "Album Artist"},
        "label": {"name": "Test Label"},
        "genres_list": ["Pop/Rock", "Pop/Rock→Rock"],
        "tracks_count": 9,
        "release_date_original": "2024-05-06",
        "copyright": "(C) 2024 Label",
    }


def _fake_track(album):
    return {
        "id": "track-2",
        "title": "Finale",
        "version": "Live",
        "work": "Suite",
        "track_number": 2,
        "media_number": 2,
        "performer": {"name": "Track Performer"},
        "composer": {"name": "Composer Name"},
        "album": album,
        "copyright": "(P) 2024 Track Owner",
        "parental_warning": True,
    }


def test_metadata_title_formats_versions_and_classical_work_titles():
    assert metadata._get_title({"title": "Song", "version": "Live"}) == "Song (Live)"
    assert (
        metadata._get_title(
            {"work": "Symphony No. 5", "title": "I. Allegro", "version": "Live"}
        )
        == "Symphony No. 5: I. Allegro (Live)"
    )


def test_metadata_genre_normalization_preserves_first_seen_order_without_repeats():
    assert (
        metadata._format_genres(
            ["Pop/Rock", "Pop/Rock→Rock", "Pop/Rock→Rock→Alternatif et Indé"]
        )
        == "Pop, Rock, Alternatif et Indé"
    )


def test_metadata_copyright_replaces_qobuz_marker_text_with_symbols():
    assert metadata._format_copyright("(P) 2024 Label (C) 2024 Owner") == (
        "℗ 2024 Label © 2024 Owner"
    )
    assert metadata._format_copyright("") == ""


def test_tag_flac_writes_album_metadata_embeds_cover_and_renames(tmp_path):
    album = _fake_album()
    track = _fake_track(album)
    album_dir = tmp_path / "Album"
    disc_dir = album_dir / "Disc 2"
    disc_dir.mkdir(parents=True)
    (album_dir / "cover.jpg").write_bytes(b"fake-jpeg-cover")
    temp_file = disc_dir / ".02.tmp"
    final_file = disc_dir / "02. Finale.flac"
    _write_fake_flac(temp_file)

    metadata.tag_flac(
        str(temp_file),
        str(disc_dir),
        str(final_file),
        track,
        album,
        istrack=False,
        em_image=True,
    )

    assert final_file.exists()
    assert not temp_file.exists()
    audio = FLAC(final_file)
    assert audio["TITLE"] == ["Suite: Finale (Live)"]
    assert audio["TRACKNUMBER"] == ["2"]
    assert audio["DISCNUMBER"] == ["2"]
    assert audio["COMPOSER"] == ["Composer Name"]
    assert audio["ARTIST"] == ["Track Performer"]
    assert audio["ALBUMARTIST"] == ["Album Artist"]
    assert audio["ALBUM"] == ["Fake Album"]
    assert audio["TRACKTOTAL"] == ["9"]
    assert audio["DATE"] == ["2024-05-06"]
    assert audio["LABEL"] == ["Test Label"]
    assert audio["GENRE"] == ["Pop, Rock"]
    assert audio["COPYRIGHT"] == ["© 2024 Label"]
    assert len(audio.pictures) == 1
    assert audio.pictures[0].data == b"fake-jpeg-cover"


def test_tag_mp3_writes_track_metadata_cover_flag_and_renames(tmp_path):
    album = _fake_album()
    track = _fake_track(album)
    tagged_files = []

    for embed_art in (True, False):
        root_dir = tmp_path / f"mp3-cover-{embed_art}"
        root_dir.mkdir()
        if embed_art:
            (root_dir / "cover.jpg").write_bytes(b"fake-jpeg-cover")
        temp_file = root_dir / ".02.tmp"
        final_file = root_dir / "02. Finale.mp3"
        temp_file.write_bytes(b"fake mp3 frame bytes")

        metadata.tag_mp3(
            str(temp_file),
            str(root_dir),
            str(final_file),
            track,
            album,
            istrack=True,
            em_image=embed_art,
        )

        assert final_file.exists()
        assert not temp_file.exists()
        tagged_files.append((final_file, embed_art))

    tagged = ID3(tagged_files[0][0], translate=False)
    assert tagged["TIT2"].text == ["Suite: Finale (Live)"]
    assert tagged["TRCK"].text == ["2/9"]
    assert tagged["TPOS"].text == ["2"]
    assert tagged["TPE1"].text == ["Track Performer"]
    assert tagged["TPE2"].text == ["Album Artist"]
    assert tagged["TALB"].text == ["Fake Album"]
    assert tagged["TDAT"].text == ["2024-05-06"]
    assert tagged["TPUB"].text == ["Test Label"]
    assert tagged["TCON"].text == ["Pop, Rock"]
    assert tagged["TCOP"].text == ["℗ 2024 Track Owner"]
    assert tagged["TYER"].text == ["2024"]
    assert tagged.version == (2, 3, 0)
    assert tagged.getall("APIC")[0].data == b"fake-jpeg-cover"

    no_cover = ID3(tagged_files[1][0], translate=False)
    assert no_cover.getall("APIC") == []


def test_taggers_preserve_missing_optional_metadata_differences(tmp_path):
    album = _fake_album()
    album.pop("label")
    track = _fake_track(album)
    track.pop("composer")
    track.pop("performer")

    flac_dir = tmp_path / "flac-no-label"
    flac_dir.mkdir()
    flac_temp = flac_dir / ".02.tmp"
    flac_final = flac_dir / "02. Finale.flac"
    _write_fake_flac(flac_temp)

    metadata.tag_flac(
        str(flac_temp),
        str(flac_dir),
        str(flac_final),
        track,
        album,
        istrack=True,
        em_image=False,
    )

    flac = FLAC(flac_final)
    assert flac["ARTIST"] == ["Album Artist"]
    assert flac["LABEL"] == ["n/a"]
    assert "COMPOSER" not in flac
    assert "DISCNUMBER" not in flac

    mp3_dir = tmp_path / "mp3-no-label"
    mp3_dir.mkdir()
    mp3_temp = mp3_dir / ".02.tmp"
    mp3_final = mp3_dir / "02. Finale.mp3"
    mp3_temp.write_bytes(b"fake mp3 frame bytes")

    metadata.tag_mp3(
        str(mp3_temp),
        str(mp3_dir),
        str(mp3_final),
        track,
        album,
        istrack=False,
        em_image=False,
    )

    mp3 = ID3(mp3_final, translate=False)
    assert mp3["TPE1"].text == ["Album Artist"]
    assert mp3["TRCK"].text == ["2/9"]
    assert mp3["TPOS"].text == ["2"]
    assert "TPUB" not in mp3
    assert "TCOM" not in mp3


def test_make_m3u_writes_sorted_relative_entries_from_fake_media(tmp_path):
    playlist_dir = tmp_path / "Playlist"
    playlist_dir.mkdir()
    media = [
        (playlist_dir / "02. Second.flac", "Second", "Artist B"),
        (playlist_dir / "01. First.flac", "First", "Artist A"),
        (playlist_dir / "Disc 2" / "03. Third.flac", "Third", "Artist C"),
    ]
    for path, title, artist in media:
        path.parent.mkdir(exist_ok=True)
        _write_fake_flac(path)
        audio = FLAC(path)
        audio["TITLE"] = title
        audio["ARTIST"] = artist
        audio.save()

    make_m3u(playlist_dir)

    playlist = (playlist_dir / "Playlist.m3u").read_text(encoding="utf-8")
    assert playlist.split("\n\n") == [
        "#EXTM3U",
        "#EXTINF:0, Artist A - First\n01. First.flac",
        "#EXTINF:0, Artist B - Second\n02. Second.flac",
        "#EXTINF:0, Artist C - Third\nDisc 2/03. Third.flac",
    ]
