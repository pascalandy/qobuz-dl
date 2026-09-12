import logging
import os
import re
import string
import time

from mutagen.flac import FLAC
from mutagen.mp3 import EasyMP3

logger = logging.getLogger(__name__)


class PartialFormatter(string.Formatter):
    def __init__(self, missing="n/a", bad_fmt="n/a"):
        self.missing, self.bad_fmt = missing, bad_fmt

    def get_field(self, field_name, args, kwargs):
        try:
            val = super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError):
            val = None, field_name
        return val

    def format_field(self, value, spec):
        if not value:
            return self.missing
        try:
            return super().format_field(value, spec)
        except ValueError:
            if self.bad_fmt:
                return self.bad_fmt
            raise


def make_m3u(pl_directory, finalized_paths):
    track_list = ["#EXTM3U"]
    rel_folder = os.path.basename(os.path.normpath(pl_directory))
    pl_name = rel_folder + ".m3u"
    for finalized_path in finalized_paths:
        audio_file = os.path.abspath(os.fspath(finalized_path))
        if not os.path.isfile(audio_file):
            logger.warning("Skipping %s in m3u: file is not readable", finalized_path)
            continue

        suffix = os.path.splitext(audio_file)[1].lower()
        if suffix == ".mp3":
            reader = EasyMP3
        elif suffix == ".flac":
            reader = FLAC
        else:
            logger.warning(
                "Skipping %s in m3u: unsupported media suffix %s",
                finalized_path,
                suffix or "<none>",
            )
            continue

        audio_rel_file = os.path.relpath(audio_file, pl_directory).replace(os.sep, "/")
        try:
            pl_item = reader(audio_file)
            title = pl_item["TITLE"][0]
            artist = pl_item["ARTIST"][0]
            length = int(pl_item.info.length)
            index = "#EXTINF:{}, {} - {}\n{}".format(
                length, artist, title, audio_rel_file
            )
        except Exception as error:
            logger.warning("Skipping %s in m3u: %s", finalized_path, error)
            continue
        track_list.append(index)

    with open(os.path.join(pl_directory, pl_name), "w", encoding="utf-8") as pl:
        pl.write("\n\n".join(track_list))


def smart_discography_filter(
    contents: list, save_space: bool = False, skip_extras: bool = False
) -> list:
    """When downloading some artists' discography, many random and spam-like
    albums can get downloaded. This helps filter those out to just get the good stuff.

    This function removes:
        * albums by other artists, which may contain a feature from the requested artist
        * duplicate albums in different qualities
        * (optionally) removes collector's, deluxe, live albums

    :param list contents: contents returned by qobuz API
    :param bool save_space: choose highest bit depth, lowest sampling rate
    :param bool remove_extras: remove albums with extra material (i.e. live, deluxe,...)
    :returns: filtered items list
    """

    TYPE_REGEXES = {
        "remaster": r"(?i)(re)?master(ed)?",
        "extra": r"(?i)(anniversary|deluxe|live|collector|demo|expanded)",
    }

    def is_type(album_t: str, album: dict) -> bool:
        """Check if album is of type `album_t`"""
        version = album.get("version", "")
        title = album.get("title", "")
        regex = TYPE_REGEXES[album_t]
        return re.search(regex, f"{title} {version}") is not None

    def essence(album: dict) -> str:
        """Ignore text in parens/brackets, return all lowercase.
        Used to group two albums that may be named similarly, but not exactly
        the same.
        """
        r = re.match(r"([^\(]+)(?:\s*[\(\[][^\)][\)\]])*", album)
        return r.group(1).strip().lower()

    requested_artist = contents[0]["name"]
    items = [
        item
        for page in contents
        for item in page["albums"]["items"]
        if item.get("artist", {}).get("name") == requested_artist
    ]

    # use dicts to group duplicate albums together by title
    title_grouped = {}
    for item in items:
        title_grouped.setdefault(essence(item["title"]), []).append(item)

    items = []
    for albums in title_grouped.values():
        admissible = [
            album for album in albums if not (skip_extras and is_type("extra", album))
        ]
        if not admissible:
            continue

        best_bit_depth = max(a["maximum_bit_depth"] for a in admissible)
        get_best = min if save_space else max
        best_sampling_rate = get_best(
            a["maximum_sampling_rate"]
            for a in admissible
            if a["maximum_bit_depth"] == best_bit_depth
        )
        remaster_exists = any(is_type("remaster", a) for a in admissible)

        def is_valid(album: dict) -> bool:
            return (
                album["maximum_bit_depth"] == best_bit_depth
                and album["maximum_sampling_rate"] == best_sampling_rate
                and not (remaster_exists and not is_type("remaster", album))
            )

        filtered = tuple(filter(is_valid, admissible))
        # most of the time, len is 0 or 1.
        # if greater, it is a complete duplicate,
        # so it doesn't matter which is chosen
        if len(filtered) >= 1:
            items.append(filtered[0])

    return items


def format_duration(duration):
    return time.strftime("%H:%M:%S", time.gmtime(duration))


def create_and_return_dir(directory):
    fix = os.path.normpath(directory)
    os.makedirs(fix, exist_ok=True)
    return fix


def get_url_info(url):
    """Return the type and id parsed from a Qobuz URL.

    Compatible with urls of the form:
        https://www.qobuz.com/us-en/{type}/{name}/{id}
        https://open.qobuz.com/{type}/{id}
        https://play.qobuz.com/{type}/{id}
        /us-en/{type}/-/{id}

    :raises ValueError: when the URL is not a recognizable Qobuz URL.
    """

    r = re.search(
        r"(?:https:\/\/(?:w{3}|open|play)\.qobuz\.com)?(?:\/[a-z]{2}-[a-z]{2})"
        r"?\/(album|artist|track|playlist|label)(?:\/[-\w\d]+)?\/([\w\d]+)",
        url,
    )
    if r is None:
        raise ValueError(f"Invalid Qobuz URL: {url!r}")
    return r.groups()
