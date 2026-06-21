import logging
import os
import re

import mutagen.id3 as id3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3NoHeaderError

logger = logging.getLogger(__name__)


# unicode symbols: \u00a9 for (C), \u2117 for (P)
COPYRIGHT, PHON_COPYRIGHT = "\u00a9", "\u2117"
# if a metadata block exceeds this, mutagen will raise error
# and the file won't be tagged
FLAC_MAX_BLOCKSIZE = 16777215

ID3_LEGEND = {
    "album": id3.TALB,
    "albumartist": id3.TPE2,
    "artist": id3.TPE1,
    "comment": id3.COMM,
    "composer": id3.TCOM,
    "copyright": id3.TCOP,
    "date": id3.TDAT,
    "genre": id3.TCON,
    "isrc": id3.TSRC,
    "label": id3.TPUB,
    "performer": id3.TOPE,
    "title": id3.TIT2,
    "year": id3.TYER,
}
_MISSING = object()


def _get_title(track_dict):
    title = track_dict["title"]
    version = track_dict.get("version")
    if version:
        title = f"{title} ({version})"
    # for classical works
    if track_dict.get("work"):
        title = f"{track_dict['work']}: {title}"

    return title


def _format_copyright(s: str) -> str:
    if s:
        s = s.replace("(P)", PHON_COPYRIGHT)
        s = s.replace("(C)", COPYRIGHT)
    return s


def _format_genres(genres: list) -> str:
    """Fixes the weirdly formatted genre lists returned by the API.
    >>> g = ['Pop/Rock', 'Pop/Rock→Rock', 'Pop/Rock→Rock→Alternatif et Indé']
    >>> _format_genres(g)
    'Pop, Rock, Alternatif et Indé'
    """
    genres = re.findall(r"([^\u2192\/]+)", "/".join(genres))
    return ", ".join(dict.fromkeys(genres))


def _build_metadata_payload(d: dict, album: dict, istrack=True):
    artist = d.get("performer", {}).get("name")
    if istrack:
        album_data = d["album"]
        artist = artist or album_data["artist"]["name"]
        copyright_text = d.get("copyright") or "n/a"
    else:
        album_data = album
        artist = artist or album_data["artist"]["name"]
        copyright_text = album.get("copyright") or "n/a"

    try:
        composer = d["composer"]["name"]
    except KeyError:
        composer = _MISSING

    flac_label = album.get("label", {}).get("name", "n/a")
    try:
        mp3_label = album["label"]["name"]
    except KeyError:
        mp3_label = _MISSING

    return {
        "title": _get_title(d),
        "tracknumber": str(d["track_number"]),
        "discnumber": str(d["media_number"]),
        "composer": composer,
        "artist": artist,
        "flac_label": flac_label,
        "mp3_label": mp3_label,
        "genre": _format_genres(album_data["genres_list"]),
        "albumartist": album_data["artist"]["name"],
        "tracktotal": str(album_data["tracks_count"]),
        "album": album_data["title"],
        "date": album_data["release_date_original"],
        "copyright": _format_copyright(copyright_text),
    }


def _embed_flac_img(root_dir, audio: FLAC):
    emb_image = os.path.join(root_dir, "cover.jpg")
    multi_emb_image = os.path.join(
        os.path.abspath(os.path.join(root_dir, os.pardir)), "cover.jpg"
    )
    if os.path.isfile(emb_image):
        cover_image = emb_image
    else:
        cover_image = multi_emb_image

    try:
        # rest of the metadata still gets embedded
        # when the image size is too big
        if os.path.getsize(cover_image) > FLAC_MAX_BLOCKSIZE:
            raise Exception(
                "downloaded cover size too large to embed. "
                "turn off `og_cover` to avoid error"
            )

        image = Picture()
        image.type = 3
        image.mime = "image/jpeg"
        image.desc = "cover"
        with open(cover_image, "rb") as img:
            image.data = img.read()
        audio.add_picture(image)
    except Exception as e:
        logger.error(f"Error embedding image: {e}", exc_info=True)


def _embed_id3_img(root_dir, audio: id3.ID3):
    emb_image = os.path.join(root_dir, "cover.jpg")
    multi_emb_image = os.path.join(
        os.path.abspath(os.path.join(root_dir, os.pardir)), "cover.jpg"
    )
    if os.path.isfile(emb_image):
        cover_image = emb_image
    else:
        cover_image = multi_emb_image

    with open(cover_image, "rb") as cover:
        audio.add(id3.APIC(3, "image/jpeg", 3, "", cover.read()))


# Use KeyError catching instead of dict.get to avoid empty tags
def tag_flac(
    filename, root_dir, final_name, d: dict, album, istrack=True, em_image=False
):
    """
    Tag a FLAC file

    :param str filename: FLAC file path
    :param str root_dir: Root dir used to get the cover art
    :param str final_name: Final name of the FLAC file (complete path)
    :param dict d: Track dictionary from Qobuz_client
    :param dict album: Album dictionary from Qobuz_client
    :param bool istrack
    :param bool em_image: Embed cover art into file
    """
    audio = FLAC(filename)
    tags = _build_metadata_payload(d, album, istrack=istrack)

    audio["TITLE"] = tags["title"]

    audio["TRACKNUMBER"] = tags["tracknumber"]  # TRACK NUMBER

    if "Disc " in final_name:
        audio["DISCNUMBER"] = tags["discnumber"]

    if tags["composer"] is not _MISSING:
        audio["COMPOSER"] = tags["composer"]  # COMPOSER

    audio["ARTIST"] = tags["artist"]  # TRACK ARTIST
    audio["LABEL"] = tags["flac_label"]
    audio["GENRE"] = tags["genre"]
    audio["ALBUMARTIST"] = tags["albumartist"]
    audio["TRACKTOTAL"] = tags["tracktotal"]
    audio["ALBUM"] = tags["album"]
    audio["DATE"] = tags["date"]
    audio["COPYRIGHT"] = tags["copyright"]

    if em_image:
        _embed_flac_img(root_dir, audio)

    audio.save()
    os.rename(filename, final_name)


def tag_mp3(filename, root_dir, final_name, d, album, istrack=True, em_image=False):
    """
    Tag an mp3 file

    :param str filename: mp3 temporary file path
    :param str root_dir: Root dir used to get the cover art
    :param str final_name: Final name of the mp3 file (complete path)
    :param dict d: Track dictionary from Qobuz_client
    :param bool istrack
    :param bool em_image: Embed cover art into file
    """

    try:
        audio = id3.ID3(filename)
    except ID3NoHeaderError:
        audio = id3.ID3()

    payload = _build_metadata_payload(d, album, istrack=istrack)
    tags = {
        "title": payload["title"],
        "artist": payload["artist"],
        "genre": payload["genre"],
        "albumartist": payload["albumartist"],
        "album": payload["album"],
        "date": payload["date"],
        "copyright": payload["copyright"],
    }
    if payload["mp3_label"] is not _MISSING:
        tags["label"] = payload["mp3_label"]
    tags["year"] = tags["date"][:4]

    audio["TRCK"] = id3.TRCK(
        encoding=3, text=f"{payload['tracknumber']}/{payload['tracktotal']}"
    )
    audio["TPOS"] = id3.TPOS(encoding=3, text=payload["discnumber"])

    # write metadata in `tags` to file
    for k, v in tags.items():
        id3tag = ID3_LEGEND[k]
        audio[id3tag.__name__] = id3tag(encoding=3, text=v)

    if em_image:
        _embed_id3_img(root_dir, audio)

    audio.save(filename, v2_version=3)
    os.rename(filename, final_name)
