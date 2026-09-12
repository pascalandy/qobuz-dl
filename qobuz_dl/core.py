import logging
import os
from dataclasses import dataclass
from html.parser import HTMLParser

from qobuz_dl import downloader, http, qopy
from qobuz_dl.bundle import Bundle
from qobuz_dl.color import CYAN, OFF, RED, RESET, YELLOW
from qobuz_dl.db import create_db, handle_download_id
from qobuz_dl.exceptions import NonStreamable
from qobuz_dl.sanitize import sanitize_filename
from qobuz_dl.utils import (
    PartialFormatter,
    create_and_return_dir,
    format_duration,
    get_url_info,
    make_m3u,
    smart_discography_filter,
)

WEB_URL = "https://play.qobuz.com/"
QUALITIES = {
    5: "5 - MP3",
    6: "6 - 16 bit, 44.1kHz",
    7: "7 - 24 bit, <96kHz",
    27: "27 - 24 bit, >96kHz",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DirectDownloadPlan:
    item_id: str
    album: bool


@dataclass(frozen=True)
class _CollectionDownloadPlan:
    url_type: str
    collection_name: str
    item_ids: tuple[str, ...]
    album: bool
    create_m3u: bool = False


@dataclass(frozen=True)
class LastFmTrack:
    artist: str
    title: str


@dataclass(frozen=True)
class _PlaylistOccurrence:
    item_id: str
    result: downloader.DownloadResult


def _normalize_search_query(query):
    if not isinstance(query, str):
        return ""
    return query.strip()


def _validate_bandwidth_limit(bandwidth_limit: int | None) -> None:
    if bandwidth_limit is None:
        return
    if (
        isinstance(bandwidth_limit, bool)
        or not isinstance(bandwidth_limit, int)
        or bandwidth_limit <= 0
    ):
        raise ValueError("bandwidth_limit must be a positive integer or None")


class LastFmPlaylistParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.tracks: list[LastFmTrack] = []
        self._artist_fragments: list[str] | None = None
        self._title_fragments: list[str] | None = None
        self._cell = None
        self._capture = None
        self._anchor_seen = False
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._reset_row(active=True)
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "td":
            self._clear_cell()
            if self._artist_fragments is None:
                return
            attrs_dict = dict(attrs)
            classes = (attrs_dict.get("class") or "").split()
            if "chartlist-artist" in classes:
                self._cell = "artist"
            elif "chartlist-name" in classes:
                self._cell = "title"
        elif tag == "a" and self._cell is not None and not self._anchor_seen:
            self._capture = self._cell
            self._anchor_seen = True

    def handle_endtag(self, tag):
        if tag == "tr":
            self._finish_row()
        elif tag == "h1" and self._in_h1:
            self._in_h1 = False
        elif tag == "td":
            self._clear_cell()
        elif tag == "a" and self._capture is not None:
            self._capture = None

    def handle_data(self, data):
        if self._in_h1 and not self.title:
            text = data.strip()
            if text:
                self.title = text
        elif self._capture == "artist":
            self._artist_fragments.append(data)
        elif self._capture == "title":
            self._title_fragments.append(data)

    def _clear_cell(self):
        self._cell = None
        self._capture = None
        self._anchor_seen = False

    def _reset_row(self, *, active):
        self._clear_cell()
        self._artist_fragments = [] if active else None
        self._title_fragments = [] if active else None

    def _finish_row(self):
        if self._artist_fragments is not None:
            artist = " ".join("".join(self._artist_fragments).split())
            title = " ".join("".join(self._title_fragments).split())
            if artist and title:
                self.tracks.append(LastFmTrack(artist=artist, title=title))
        self._reset_row(active=False)


def _select_one(options, prompt, *, label=str, default_index=None):
    for index, option in enumerate(options, start=1):
        default_marker = " [default]" if default_index == index - 1 else ""
        print(f"{index}. {label(option)}{default_marker}")
    while True:
        choice = input(prompt).strip()
        if not choice and default_index is not None:
            return options[default_index]
        try:
            index = int(choice)
        except ValueError:
            print("Enter a number from the list.")
            continue
        if 1 <= index <= len(options):
            return options[index - 1]
        print("Enter a number from the list.")


def _select_many(options, prompt, *, label=str):
    for index, option in enumerate(options, start=1):
        print(f"{index}. {label(option)}")
    while True:
        raw = input(prompt).strip()
        if not raw:
            return []
        selected = []
        try:
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    start, end = [int(value.strip()) for value in part.split("-", 1)]
                    selected.extend(range(start, end + 1))
                else:
                    selected.append(int(part))
        except ValueError:
            print("Enter comma-separated numbers or ranges like 1,3-5.")
            continue
        if all(1 <= index <= len(options) for index in selected):
            deduped = []
            for index in selected:
                if index not in deduped:
                    deduped.append(index)
            return [options[index - 1] for index in deduped]
        print("Enter numbers from the list.")


def _confirm(prompt):
    while True:
        answer = input(f"{prompt} [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"", "n", "no"}:
            return False
        print("Enter yes or no.")


class QobuzDL:
    def __init__(
        self,
        directory="Qobuz Downloads",
        quality=6,
        embed_art=False,
        lucky_limit=1,
        lucky_type="album",
        interactive_limit=20,
        ignore_singles_eps=False,
        no_m3u_for_playlists=False,
        quality_fallback=True,
        cover_og_quality=False,
        no_cover=False,
        downloads_db=None,
        folder_format="{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]",
        track_format="{tracknumber}. {tracktitle}",
        smart_discography=False,
        bandwidth_limit: int | None = None,
    ):
        downloader.validate_cover_options(embed_art, no_cover)
        _validate_bandwidth_limit(bandwidth_limit)
        self.directory = create_and_return_dir(directory)
        self.quality = quality
        self.embed_art = embed_art
        self.lucky_limit = lucky_limit
        self.lucky_type = lucky_type
        self.interactive_limit = interactive_limit
        self.ignore_singles_eps = ignore_singles_eps
        self.no_m3u_for_playlists = no_m3u_for_playlists
        self.quality_fallback = quality_fallback
        self.cover_og_quality = cover_og_quality
        self.no_cover = no_cover
        self.downloads_db = create_db(downloads_db) if downloads_db else None
        self.folder_format = folder_format
        self.track_format = track_format
        self.smart_discography = smart_discography
        self.bandwidth_limit = bandwidth_limit

    def initialize_client(self, email, pwd, app_id, secrets):
        self.client = qopy.Client(email, pwd, app_id, secrets)
        logger.info(f"{YELLOW}Set max quality: {QUALITIES[int(self.quality)]}\n")

    def get_tokens(self):
        bundle = Bundle()
        self.app_id = bundle.get_app_id()
        self.secrets = [
            secret for secret in bundle.get_secrets().values() if secret
        ]  # avoid empty fields

    def download_from_id(self, item_id, album=True, alt_path=None):
        if handle_download_id(self.downloads_db, item_id, add_id=False):
            logger.info(
                f"{OFF}This release ID ({item_id}) was already downloaded "
                "according to the local database.\nUse the '--no-db' flag "
                "to bypass this."
            )
            return downloader.DownloadResult("ignored", "database_duplicate")
        try:
            dloader = self._new_downloader(item_id, alt_path)
            if album:
                result = dloader.download_release()
            else:
                result = dloader.download_track()
        except (http.HttpError, ConnectionError):
            result = downloader.DownloadResult("failed", "request_error")
        except NonStreamable:
            result = downloader.DownloadResult("failed", "not_streamable")

        if result.state == "finalized":
            handle_download_id(self.downloads_db, item_id, add_id=True)
        return result

    def _new_downloader(self, item_id, alt_path=None):
        return downloader.Download(
            self.client,
            item_id,
            alt_path or self.directory,
            int(self.quality),
            self.embed_art,
            self.ignore_singles_eps,
            self.quality_fallback,
            self.cover_og_quality,
            self.no_cover,
            self.folder_format,
            self.track_format,
            bandwidth_limit=self.bandwidth_limit,
        )

    def _resolve_url_download_plan(self, url):
        try:
            url_type, item_id = get_url_info(url)
        except (KeyError, ValueError):
            logger.info(
                f'{RED}Invalid url: "{url}". Use urls from https://play.qobuz.com!'
            )
            return

        if url_type == "album":
            return _DirectDownloadPlan(item_id=item_id, album=True)
        if url_type == "track":
            return _DirectDownloadPlan(item_id=item_id, album=False)
        if url_type == "artist":
            return self._resolve_artist_download_plan(item_id)
        if url_type == "label":
            return self._resolve_label_download_plan(item_id)
        if url_type == "playlist":
            return self._resolve_playlist_download_plan(item_id)

        logger.info(f'{RED}Invalid url: "{url}". Use urls from https://play.qobuz.com!')
        return

    def _resolve_artist_download_plan(self, item_id):
        content = list(self.client.get_artist_meta(item_id))
        content_name = content[0]["name"]
        if self.smart_discography:
            # change `save_space` and `skip_extras` for customization
            items = smart_discography_filter(
                content,
                save_space=True,
                skip_extras=True,
            )
        else:
            items = self._collection_items(content, "albums")
        return _CollectionDownloadPlan(
            url_type="artist",
            collection_name=content_name,
            item_ids=tuple(item["id"] for item in items),
            album=True,
        )

    def _resolve_label_download_plan(self, item_id):
        content = list(self.client.get_label_meta(item_id))
        return _CollectionDownloadPlan(
            url_type="label",
            collection_name=content[0]["name"],
            item_ids=tuple(
                item["id"] for item in self._collection_items(content, "albums")
            ),
            album=True,
        )

    def _resolve_playlist_download_plan(self, item_id):
        content = list(self.client.get_plist_meta(item_id))
        return _CollectionDownloadPlan(
            url_type="playlist",
            collection_name=content[0]["name"],
            item_ids=tuple(
                item["id"] for item in self._collection_items(content, "tracks")
            ),
            album=False,
            create_m3u=not self.no_m3u_for_playlists,
        )

    def _collection_items(self, content, item_key):
        return [item for page in content for item in page[item_key]["items"]]

    def _execute_url_download_plan(self, plan):
        if isinstance(plan, _DirectDownloadPlan):
            self.download_from_id(plan.item_id, plan.album)
            return

        logger.info(
            f"{YELLOW}Downloading all the music from "
            f"{plan.collection_name} ({plan.url_type})!"
        )
        new_path = create_and_return_dir(
            os.path.join(self.directory, sanitize_filename(plan.collection_name))
        )

        logger.info(f"{YELLOW}{len(plan.item_ids)} downloads in queue")
        if plan.url_type == "playlist":
            occurrences = self._download_playlist_occurrences(
                plan.item_ids,
                new_path,
                recover_existing=plan.create_m3u,
            )
            if plan.create_m3u:
                make_m3u(new_path, self._playlist_finalized_paths(occurrences))
            return occurrences

        for item_id in plan.item_ids:
            self.download_from_id(item_id, plan.album, new_path)

    def _download_playlist_occurrences(
        self, item_ids, destination, *, recover_existing
    ):
        results_by_id = {}
        occurrences = []
        for item_id in item_ids:
            if item_id not in results_by_id:
                result = self.download_from_id(item_id, False, destination)
                if recover_existing and result.reason == "database_duplicate":
                    result = self._reuse_playlist_destination(
                        item_id, destination, result
                    )
                results_by_id[item_id] = result
            occurrences.append(_PlaylistOccurrence(item_id, results_by_id[item_id]))
        return tuple(occurrences)

    def _reuse_playlist_destination(self, item_id, destination, duplicate_result):
        try:
            final_path = self._new_downloader(
                item_id, destination
            ).existing_track_path()
        except (http.HttpError, ConnectionError):
            return duplicate_result
        if final_path:
            return downloader.DownloadResult(
                "finalized", "existing_file", (final_path,)
            )
        return duplicate_result

    @staticmethod
    def _playlist_finalized_paths(occurrences):
        claimed_paths = {}
        finalized_paths = []
        for occurrence in occurrences:
            for path in occurrence.result.finalized_paths:
                path_key = os.path.normcase(os.path.abspath(path))
                existing_owner = claimed_paths.setdefault(path_key, occurrence.item_id)
                if existing_owner != occurrence.item_id:
                    logger.warning(
                        "%s and %s resolved to the same playlist file: %s",
                        existing_owner,
                        occurrence.item_id,
                        path,
                    )
                finalized_paths.append(path)
        return tuple(finalized_paths)

    def handle_url(self, url):
        plan = self._resolve_url_download_plan(url)
        if plan:
            self._execute_url_download_plan(plan)

    def download_list_of_urls(self, urls):
        if not urls or not isinstance(urls, list):
            logger.info(f"{OFF}Nothing to download")
            return
        for url in urls:
            if "last.fm" in url:
                self.download_lastfm_pl(url)
            elif os.path.isfile(url):
                self.download_from_txt_file(url)
            else:
                self.handle_url(url)

    def download_from_txt_file(self, txt_file):
        try:
            with open(txt_file, encoding="utf-8") as txt:
                urls = [
                    stripped
                    for line in txt
                    if (stripped := line.strip()) and not stripped.startswith("#")
                ]
        except (OSError, UnicodeDecodeError) as e:
            logger.error(f"{RED}Invalid text file: {e}")
            return
        logger.info(
            f"{YELLOW}qobuz-dl will download {len(urls)} urls from file: {txt_file}"
        )
        self.download_list_of_urls(urls)

    def lucky_mode(self, query, download=True):
        query = _normalize_search_query(query)
        if len(query) < 3:
            logger.info(f"{RED}Your search query is too short or invalid")
            return

        logger.info(
            f'{YELLOW}Searching {self.lucky_type}s for "{query}".\n'
            f"{YELLOW}qobuz-dl will attempt to download the first "
            f"{self.lucky_limit} results."
        )
        results = self.search_by_type(query, self.lucky_type, self.lucky_limit, True)

        if download:
            self.download_list_of_urls(results)

        return results

    def search_by_type(self, query, item_type, limit=10, lucky=False):
        query = _normalize_search_query(query)
        if len(query) < 3:
            logger.info(f"{RED}Your search query is too short or invalid")
            return

        possibles = {
            "album": {
                "func": self.client.search_albums,
                "album": True,
                "key": "albums",
                "format": "{artist[name]} - {title}",
                "requires_extra": True,
            },
            "artist": {
                "func": self.client.search_artists,
                "album": True,
                "key": "artists",
                "format": "{name} - ({albums_count} releases)",
                "requires_extra": False,
            },
            "track": {
                "func": self.client.search_tracks,
                "album": False,
                "key": "tracks",
                "format": "{performer[name]} - {title}",
                "requires_extra": True,
            },
            "playlist": {
                "func": self.client.search_playlists,
                "album": False,
                "key": "playlists",
                "format": "{name} - ({tracks_count} releases)",
                "requires_extra": False,
            },
        }

        try:
            mode_dict = possibles[item_type]
            results = mode_dict["func"](query, limit)
            iterable = results[mode_dict["key"]]["items"]
            item_list = []
            for i in iterable:
                fmt = PartialFormatter()
                text = fmt.format(mode_dict["format"], **i)
                if mode_dict["requires_extra"]:
                    text = "{} - {} [{}]".format(
                        text,
                        format_duration(i["duration"]),
                        "HI-RES" if i["hires_streamable"] else "LOSSLESS",
                    )

                url = "{}{}/{}".format(WEB_URL, item_type, i.get("id", ""))
                item_list.append({"text": text, "url": url} if not lucky else url)
            return item_list
        except (KeyError, IndexError):
            logger.info(f"{RED}Invalid type: {item_type}")
            return

    def interactive(self, download=True):
        qualities = [
            {"q_string": "320", "q": 5},
            {"q_string": "Lossless", "q": 6},
            {"q_string": "Hi-res =< 96kHz", "q": 7},
            {"q_string": "Hi-Res > 96 kHz", "q": 27},
        ]

        try:
            item_types = ["Albums", "Tracks", "Artists", "Playlists"]
            selected_type = _select_one(
                item_types,
                "I'll search for [number]: ",
            )[:-1].lower()
            logger.info(f"{YELLOW}Ok, we'll search for {selected_type}s{RESET}")
            final_url_list = []
            while True:
                query = input(f"{CYAN}Enter your search: [Ctrl + c to quit]{RESET}\n- ")
                logger.info(f"{YELLOW}Searching...{RESET}")
                options = self.search_by_type(
                    query, selected_type, self.interactive_limit
                )
                if not options:
                    logger.info(f"{OFF}Nothing found{RESET}")
                    continue
                print(
                    f'*** RESULTS FOR "{query.title()}" ***\n'
                    "Select item numbers to add to the queue. "
                    "Use commas and ranges (example: 1,3-5).\n"
                    "Press Enter without a selection to try another search."
                )
                selected_items = _select_many(
                    options,
                    "Items to download: ",
                    label=lambda option: option.get("text"),
                )
                if selected_items:
                    final_url_list.extend(item["url"] for item in selected_items)
                    if not _confirm(
                        "Items were added to queue to be downloaded. Keep searching?"
                    ):
                        break
                else:
                    logger.info(f"{YELLOW}Ok, try again...{RESET}")
                    continue
            if final_url_list:
                print(
                    "Select the quality (the quality will be automatically "
                    "downgraded if the selected is not found)."
                )
                current_quality = int(self.quality)
                default_quality_index = next(
                    (
                        index
                        for index, quality in enumerate(qualities)
                        if quality["q"] == current_quality
                    ),
                    1,
                )
                self.quality = _select_one(
                    qualities,
                    f"Quality [default {default_quality_index + 1}]: ",
                    default_index=default_quality_index,
                    label=lambda option: option.get("q_string"),
                )["q"]

                if download:
                    self.download_list_of_urls(final_url_list)

                return final_url_list
        except KeyboardInterrupt:
            logger.info(f"{YELLOW}Bye")
            return

    def download_lastfm_pl(self, playlist_url):
        # Apparently, last fm API doesn't have a playlist endpoint. If you
        # find out that it has, please fix this!
        try:
            html = http.get_text(playlist_url, timeout=10)
        except http.HttpError as e:
            logger.error(f"{RED}Playlist download failed: {e}")
            return
        parser = LastFmPlaylistParser()
        parser.feed(html)

        if not parser.tracks:
            logger.info(f"{OFF}Nothing found")
            return

        pl_title = sanitize_filename(parser.title)
        pl_directory = os.path.join(self.directory, pl_title)
        logger.info(
            f"{YELLOW}Downloading playlist: {pl_title} ({len(parser.tracks)} tracks)"
        )

        track_ids = []
        for track in parser.tracks:
            query = f"{track.artist} {track.title}"
            results = self.search_by_type(query, "track", 1, lucky=True)
            if not results:
                logger.info(f'{OFF}No Qobuz match for "{query}". Skipping')
                continue
            track_id = get_url_info(results[0])[1]
            if track_id:
                track_ids.append(track_id)

        occurrences = self._download_playlist_occurrences(
            track_ids,
            pl_directory,
            recover_existing=not self.no_m3u_for_playlists,
        )
        if not self.no_m3u_for_playlists:
            create_and_return_dir(pl_directory)
            make_m3u(pl_directory, self._playlist_finalized_paths(occurrences))
