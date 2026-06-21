import logging
import os
from dataclasses import dataclass
from typing import Tuple

import qobuz_dl.http as http
import qobuz_dl.metadata as metadata
from qobuz_dl.color import CYAN, GREEN, OFF, RED, YELLOW
from qobuz_dl.exceptions import NonStreamable
from qobuz_dl.sanitize import sanitize_filename, sanitize_filepath

QL_DOWNGRADE = "FormatRestrictedByFormatAvailability"
# used in case of error
DEFAULT_FORMATS = {
    "MP3": [
        "{artist} - {album} ({year}) [MP3]",
        "{tracknumber}. {tracktitle}",
    ],
    "Unknown": [
        "{artist} - {album}",
        "{tracknumber}. {tracktitle}",
    ],
}

DEFAULT_FOLDER = "{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]"
DEFAULT_TRACK = "{tracknumber}. {tracktitle}"
PROGRESS_MIN_INTERVAL_BYTES = 1024 * 1024
# Keep generated basenames comfortably below common filesystem limits (255).
MAX_FILENAME_LENGTH = 250

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DownloadPreparation:
    directory: str
    is_mp3: bool


class Download:
    def __init__(
        self,
        client,
        item_id: str,
        path: str,
        quality: int,
        embed_art: bool = False,
        albums_only: bool = False,
        downgrade_quality: bool = False,
        cover_og_quality: bool = False,
        no_cover: bool = False,
        folder_format=None,
        track_format=None,
    ):
        self.client = client
        self.item_id = item_id
        self.path = path
        self.quality = quality
        self.albums_only = albums_only
        self.embed_art = embed_art
        self.downgrade_quality = downgrade_quality
        self.cover_og_quality = cover_og_quality
        self.no_cover = no_cover
        self.folder_format = folder_format or DEFAULT_FOLDER
        self.track_format = track_format or DEFAULT_TRACK

    def download_id_by_type(self, track=True):
        if track:
            self.download_track()
        else:
            self.download_release()

    def download_release(self):
        count = 0
        meta = self.client.get_album_meta(self.item_id)

        if not meta.get("streamable"):
            raise NonStreamable("This release is not streamable")

        if self.albums_only and (
            meta.get("release_type") != "album"
            or meta.get("artist", {}).get("name") == "Various Artists"
        ):
            logger.info(f"{OFF}Ignoring Single/EP/VA: {meta.get('title', 'n/a')}")
            return

        album_title = _get_title(meta)

        preparation = self._prepare_release_download(meta, album_title)
        if not preparation:
            return

        if "goodies" in meta:
            try:
                _get_extra(
                    meta["goodies"][0]["url"], preparation.directory, "booklet.pdf"
                )
            except Exception as error:
                logger.debug("Skipping booklet download: %s", error)
        media_numbers = [track["media_number"] for track in meta["tracks"]["items"]]
        is_multiple = len(set(media_numbers)) > 1
        for i in meta["tracks"]["items"]:
            parse = self.client.get_track_url(i["id"], fmt_id=self.quality)
            if "sample" not in parse and parse.get("sampling_rate"):
                self._download_prepared_track(
                    preparation,
                    count,
                    parse,
                    i,
                    meta,
                    False,
                    i["media_number"] if is_multiple else None,
                )
            else:
                logger.info(f"{OFF}Demo. Skipping")
            count = count + 1
        logger.info(f"{GREEN}Completed")

    def download_track(self):
        parse = self.client.get_track_url(self.item_id, self.quality)

        if "sample" not in parse and parse.get("sampling_rate"):
            meta = self.client.get_track_meta(self.item_id)
            track_title = _get_title(meta)
            artist = _safe_get(meta, "performer", "name")
            logger.info(f"\n{YELLOW}Downloading: {artist} - {track_title}")
            preparation = self._prepare_track_download(meta, parse, track_title)
            if not preparation:
                return
            self._download_prepared_track(
                preparation,
                1,
                parse,
                meta,
                meta,
                True,
                None,
            )
        else:
            logger.info(f"{OFF}Demo. Skipping")
        logger.info(f"{GREEN}Completed")

    def _prepare_release_download(self, meta, album_title):
        file_format, quality_met, bit_depth, sampling_rate = self._get_format(meta)

        if not self._quality_allows_download(album_title, quality_met):
            return None

        logger.info(
            f"\n{YELLOW}Downloading: {album_title}\nQuality: {file_format}"
            f" ({bit_depth}/{sampling_rate})\n"
        )
        album_attr = self._get_album_attr(
            meta, album_title, file_format, bit_depth, sampling_rate
        )
        directory = self._prepare_destination(album_attr, file_format)
        self._download_cover(meta["image"]["large"], directory)
        return _DownloadPreparation(directory=directory, is_mp3=self._is_mp3())

    def _prepare_track_download(self, meta, track_url_dict, track_title):
        _file_format, quality_met, bit_depth, sampling_rate = self._get_format(
            meta, is_track_id=True, track_url_dict=track_url_dict
        )

        if not self._quality_allows_download(track_title, quality_met):
            return None

        track_attr = self._get_track_attr(meta, track_title, bit_depth, sampling_rate)
        directory = self._prepare_destination(track_attr, str(bit_depth))
        self._download_cover(meta["album"]["image"]["large"], directory)
        return _DownloadPreparation(directory=directory, is_mp3=self._is_mp3())

    def _quality_allows_download(self, item_title, quality_met):
        if self.downgrade_quality or quality_met:
            return True
        logger.info(
            f"{OFF}Skipping {item_title} as it doesn't meet quality requirement"
        )
        return False

    def _prepare_destination(self, folder_attr, file_format):
        folder_format, _ = _clean_format_str(
            self.folder_format, self.track_format, file_format
        )
        sanitized_title = sanitize_filepath(folder_format.format(**folder_attr))
        directory = os.path.join(self.path, sanitized_title)
        os.makedirs(directory, exist_ok=True)
        return directory

    def _download_cover(self, cover_url, directory):
        if self.no_cover:
            logger.info(f"{OFF}Skipping cover")
            return
        _get_extra(cover_url, directory, og_quality=self.cover_og_quality)

    def _download_prepared_track(
        self,
        preparation,
        tmp_count,
        track_url_dict,
        track_metadata,
        album_or_track_metadata,
        is_track,
        multiple=None,
    ):
        self._download_and_tag(
            preparation.directory,
            tmp_count,
            track_url_dict,
            track_metadata,
            album_or_track_metadata,
            is_track,
            preparation.is_mp3,
            multiple,
        )

    def _is_mp3(self):
        return int(self.quality) == 5

    def _download_and_tag(
        self,
        root_dir,
        tmp_count,
        track_url_dict,
        track_metadata,
        album_or_track_metadata,
        is_track,
        is_mp3,
        multiple=None,
    ):
        extension = ".mp3" if is_mp3 else ".flac"

        try:
            url = track_url_dict["url"]
        except KeyError:
            logger.info(f"{OFF}Track not available for download")
            return

        if multiple:
            root_dir = os.path.join(root_dir, f"Disc {multiple}")
            os.makedirs(root_dir, exist_ok=True)

        filename = os.path.join(root_dir, f".{tmp_count:02}.tmp")

        # Determine the filename
        track_title = track_metadata.get("title")
        artist = _safe_get(track_metadata, "performer", "name")
        filename_attr = self._get_filename_attr(artist, track_metadata, track_title)

        # track_format is a format string
        # e.g. '{tracknumber}. {artist} - {tracktitle}'
        formatted_path = sanitize_filename(self.track_format.format(**filename_attr))
        max_basename_length = MAX_FILENAME_LENGTH - len(extension)
        final_file = os.path.join(
            root_dir, formatted_path[:max_basename_length] + extension
        )

        if os.path.isfile(final_file):
            logger.info(f"{OFF}{track_title} was already downloaded")
            return

        download_with_progress(url, filename, filename)
        tag_function = metadata.tag_mp3 if is_mp3 else metadata.tag_flac
        try:
            tag_function(
                filename,
                root_dir,
                final_file,
                track_metadata,
                album_or_track_metadata,
                is_track,
                self.embed_art,
            )
        except Exception as e:
            logger.error(f"{RED}Error tagging the file: {e}", exc_info=True)

    @staticmethod
    def _get_filename_attr(artist, track_metadata, track_title):
        return {
            "artist": artist,
            "albumartist": _safe_get(
                track_metadata, "album", "artist", "name", default=artist
            ),
            "bit_depth": track_metadata["maximum_bit_depth"],
            "sampling_rate": track_metadata["maximum_sampling_rate"],
            "tracktitle": track_title,
            "version": track_metadata.get("version"),
            "tracknumber": f"{track_metadata['track_number']:02}",
        }

    @staticmethod
    def _get_track_attr(meta, track_title, bit_depth, sampling_rate):
        albumartist = sanitize_filename(meta["album"]["artist"]["name"])
        return {
            "album": sanitize_filename(meta["album"]["title"]),
            "artist": albumartist,
            "albumartist": albumartist,
            "tracktitle": track_title,
            "year": meta["album"]["release_date_original"].split("-")[0],
            "bit_depth": bit_depth,
            "sampling_rate": sampling_rate,
        }

    @staticmethod
    def _get_album_attr(meta, album_title, file_format, bit_depth, sampling_rate):
        albumartist = sanitize_filename(meta["artist"]["name"])
        return {
            "artist": albumartist,
            "albumartist": albumartist,
            "album": sanitize_filename(album_title),
            "year": meta["release_date_original"].split("-")[0],
            "format": file_format,
            "bit_depth": bit_depth,
            "sampling_rate": sampling_rate,
        }

    def _get_format(self, item_dict, is_track_id=False, track_url_dict=None):
        quality_met = True
        if int(self.quality) == 5:
            return ("MP3", quality_met, None, None)
        track_dict = item_dict
        if not is_track_id:
            track_dict = item_dict["tracks"]["items"][0]

        try:
            new_track_dict = (
                self.client.get_track_url(track_dict["id"], fmt_id=self.quality)
                if not track_url_dict
                else track_url_dict
            )
            restrictions = new_track_dict.get("restrictions")
            if isinstance(restrictions, list):
                if any(
                    restriction.get("code") == QL_DOWNGRADE
                    for restriction in restrictions
                ):
                    quality_met = False

            return (
                "FLAC",
                quality_met,
                new_track_dict["bit_depth"],
                new_track_dict["sampling_rate"],
            )
        except (KeyError, http.HttpError):
            return ("Unknown", quality_met, None, None)


def download_with_progress(url, fname, desc):
    """Stream ``url`` to ``fname``, logging throttled progress updates."""
    next_report = PROGRESS_MIN_INTERVAL_BYTES

    def show_progress(size, downloaded, total):
        nonlocal next_report
        if not total:
            return
        report_interval = max(total // 100, PROGRESS_MIN_INTERVAL_BYTES)
        if downloaded >= next_report or downloaded >= total:
            logger.info(f"{CYAN}{downloaded}/{total} /// {desc}")
            while next_report <= downloaded:
                next_report += report_interval

    try:
        http.stream_download(url, fname, progress=show_progress)
    except BaseException:
        try:
            os.remove(fname)
        except FileNotFoundError:
            pass
        except OSError as error:
            logger.debug("Could not remove partial download %s: %s", fname, error)
        raise


def _get_title(item_dict):
    album_title = item_dict["title"]
    version = item_dict.get("version")
    if version:
        album_title = (
            f"{album_title} ({version})"
            if version.lower() not in album_title.lower()
            else album_title
        )
    return album_title


def _get_extra(item, dirn, extra="cover.jpg", og_quality=False):
    extra_file = os.path.join(dirn, extra)
    if os.path.isfile(extra_file):
        logger.info(f"{OFF}{extra} was already downloaded")
        return
    download_with_progress(
        item.replace("_600.", "_org.") if og_quality else item,
        extra_file,
        extra,
    )


def _clean_format_str(folder: str, track: str, file_format: str) -> Tuple[str, str]:
    """Cleans up the format strings, avoids errors
    with MP3 files.
    """
    final = []
    for i, fs in enumerate((folder, track)):
        if fs.endswith(".mp3"):
            fs = fs[:-4]
        elif fs.endswith(".flac"):
            fs = fs[:-5]
        fs = fs.strip()

        # default to pre-chosen string if format is invalid
        if file_format in ("MP3", "Unknown") and (
            "bit_depth" in fs or "sampling_rate" in fs
        ):
            default = DEFAULT_FORMATS[file_format][i]
            logger.error(
                f"{RED}invalid format string for format {file_format}"
                f". defaulting to {default}"
            )
            fs = default
        final.append(fs)

    return tuple(final)


def _safe_get(d: dict, *keys, default=None):
    """A replacement for chained `get()` statements on dicts:
    >>> d = {'foo': {'bar': 'baz'}}
    >>> _safe_get(d, 'baz')
    None
    >>> _safe_get(d, 'foo', 'bar')
    'baz'
    """
    curr = d
    res = default
    for key in keys:
        res = curr.get(key, default)
        if res == default or not hasattr(res, "__getitem__"):
            return res
        else:
            curr = res
    return res
