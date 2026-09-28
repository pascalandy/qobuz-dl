import logging
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlsplit

from qobuz_dl import downloader, http, qopy
from qobuz_dl.bundle import Bundle
from qobuz_dl.color import CYAN, OFF, RED, RESET, YELLOW
from qobuz_dl.console import ExitCode, prompt, say
from qobuz_dl.db import DownloadHistory
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


@dataclass(frozen=True)
class Source:
    """One validated download source.

    ``location`` names where the source came from, such as ``urls.txt:3``;
    it is ``None`` for a command-line argument.
    """

    kind: Literal["qobuz", "lastfm"]
    url: str
    location: str | None = None
    url_type: str | None = None
    item_id: str | None = None


class SourceError(ValueError):
    """A source that is neither a supported URL nor a readable text file."""


@dataclass(frozen=True)
class _UrlShape:
    kind: Literal["qobuz", "lastfm"]
    hosts: frozenset[str]
    path: re.Pattern


# Every URL the command line accepts. Only https, only these hosts, and only
# these paths; a query string or fragment is allowed and ignored.
URL_SHAPES = (
    _UrlShape(
        "qobuz",
        frozenset({"play.qobuz.com", "open.qobuz.com", "www.qobuz.com"}),
        re.compile(
            r"(?:/[a-z]{2}-[a-z]{2})?"
            r"/(?P<type>album|artist|track|playlist|label)"
            r"(?:/[^/]+)?"
            r"/(?P<id>[A-Za-z0-9]+)/?"
        ),
    ),
    _UrlShape(
        "lastfm",
        frozenset({"last.fm", "www.last.fm"}),
        re.compile(r"(?:/[a-z]{2}(?:-[a-z]{2})?)?/user/[^/]+/playlists/[A-Za-z0-9]+/?"),
    ),
)


def parse_source_url(text: str, location: str | None = None) -> Source | None:
    """Return the ``Source`` for a supported URL, or ``None`` for anything else."""
    try:
        parts = urlsplit(text)
        hostname = parts.hostname
    except ValueError:
        return None
    if parts.scheme != "https" or hostname is None or parts.netloc.lower() != hostname:
        return None
    for shape in URL_SHAPES:
        if hostname not in shape.hosts:
            continue
        match = shape.path.fullmatch(parts.path)
        if match is None:
            return None
        if shape.kind == "lastfm":
            return Source("lastfm", text, location)
        return Source("qobuz", text, location, match["type"], match["id"])
    return None


def _source_lines(path: str, location: str | None) -> list[str]:
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "not UTF-8 text"
        raise SourceError(
            _source_message(location, f"cannot read text file {path!r}: {reason}")
        ) from None


def _source_message(location: str | None, message: str) -> str:
    return message if location is None else f"{location}: {message}"


def expand_sources(texts: Iterable[str], *, origin: str | None = None) -> list[Source]:
    """Validate command-line sources and expand text files, before any login.

    Each text is a supported Qobuz or Last.fm URL, or an existing UTF-8 text
    file with one source per line; blank lines and ``#`` comments are skipped.
    Files may include other files. A file that includes itself, directly or
    through others, is an error; including one file twice is not.
    ``origin`` labels the texts, for example ``<stdin>``, so errors can name
    ``<stdin>:2``.
    """
    sources: list[Source] = []

    def expand(text: str, location: str | None, active: tuple[str, ...]):
        text = text.strip()
        source = parse_source_url(text, location)
        if source is not None:
            sources.append(source)
            return
        if "://" not in text and os.path.isfile(text):
            identity = os.path.realpath(text)
            if identity in active:
                raise SourceError(
                    _source_message(location, f"{text!r} includes itself")
                )
            for number, line in enumerate(_source_lines(text, location), start=1):
                line = line.strip()
                if line and not line.startswith("#"):
                    expand(line, f"{text}:{number}", (*active, identity))
            return
        reason = (
            "not a supported Qobuz or Last.fm URL"
            if "://" in text
            else "not a supported Qobuz or Last.fm URL, and no such file"
        )
        raise SourceError(_source_message(location, f"{reason}: {text!r}"))

    for number, text in enumerate(texts, start=1):
        expand(text, None if origin is None else f"{origin}:{number}", ())
    return sources


Classification = Literal["satisfied", "no_op", "permanent", "temporary"]

# Ignored outcomes that follow the user's own policy rather than a failure.
_POLICY_NO_OPS = frozenset({"type_filter", "empty_release"})


@dataclass(frozen=True)
class RunItem:
    """One track or album outcome, and the source that asked for it."""

    source: str
    kind: Literal["album", "track"]
    item_id: str
    result: downloader.DownloadResult

    @property
    def classification(self) -> Classification:
        result = self.result
        if result.state == "finalized":
            return "satisfied"
        if result.state == "ignored" and result.reason in _POLICY_NO_OPS:
            return "no_op"
        if result.state == "failed" and result.retryable:
            return "temporary"
        return "permanent"


@dataclass(frozen=True)
class RunProblem:
    """A source that produced no items, such as a search with no match."""

    code: str
    message: str
    source: str
    retryable: bool = False

    @property
    def classification(self) -> Classification:
        return "temporary" if self.retryable else "permanent"


@dataclass
class RunResult:
    """Every outcome of one run; stdout paths and the exit code derive from it.

    ``on_path`` receives each finalized path once, as soon as it is final.
    """

    on_path: Callable[[str], None] | None = None
    items: list[RunItem] = field(default_factory=list)
    problems: list[RunProblem] = field(default_factory=list)
    _reported_paths: set[str] = field(default_factory=set, repr=False)

    def add_item(self, item: RunItem) -> None:
        self.items.append(item)
        if item.result.state != "finalized":
            return
        for path in item.result.finalized_paths:
            if path not in self._reported_paths:
                self._reported_paths.add(path)
                if self.on_path is not None:
                    self.on_path(path)

    def add_problem(self, problem: RunProblem) -> None:
        self.problems.append(problem)

    def exit_code(self) -> ExitCode:
        """``1`` for any permanent failure, else ``75`` for temporary ones."""
        classes = {entry.classification for entry in (*self.items, *self.problems)}
        if "permanent" in classes:
            return ExitCode.FAILURE
        if "temporary" in classes:
            return ExitCode.TEMPORARY
        return ExitCode.OK


def _normalize_search_query(query):
    if not isinstance(query, str):
        return ""
    return query.strip()


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


def _select_one(options, question, *, label=str, default_index=None):
    for index, option in enumerate(options, start=1):
        default_marker = " [default]" if default_index == index - 1 else ""
        say(f"{index}. {label(option)}{default_marker}")
    while True:
        choice = prompt(question).strip()
        if not choice and default_index is not None:
            return options[default_index]
        try:
            index = int(choice)
        except ValueError:
            say("Enter a number from the list.")
            continue
        if 1 <= index <= len(options):
            return options[index - 1]
        say("Enter a number from the list.")


def _select_many(options, question, *, label=str):
    for index, option in enumerate(options, start=1):
        say(f"{index}. {label(option)}")
    while True:
        raw = prompt(question).strip()
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
            say("Enter comma-separated numbers or ranges like 1,3-5.")
            continue
        if all(1 <= index <= len(options) for index in selected):
            deduped = []
            for index in selected:
                if index not in deduped:
                    deduped.append(index)
            return [options[index - 1] for index in deduped]
        say("Enter numbers from the list.")


def _confirm(question):
    while True:
        answer = prompt(f"{question} [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"", "n", "no"}:
            return False
        say("Enter yes or no.")


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
    ):
        downloader.validate_cover_options(embed_art, no_cover)
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
        self.download_history = DownloadHistory.open(downloads_db)
        self.folder_format = folder_format
        self.track_format = track_format
        self.smart_discography = smart_discography
        self.run_result = RunResult()
        self._current_source = ""

    def initialize_client(self, email, pwd, app_id, secrets):
        self.client = qopy.Client(email, pwd, app_id, secrets)
        logger.info(f"{YELLOW}Set max quality: {QUALITIES[int(self.quality)]}\n")

    @property
    def downloads_db(self):
        return self.download_history.path

    def get_tokens(self):
        bundle = Bundle()
        self.app_id = bundle.get_app_id()
        self.secrets = [
            secret for secret in bundle.get_secrets().values() if secret
        ]  # avoid empty fields

    def download_from_id(self, item_id, album=True, alt_path=None):
        kind = "album" if album else "track"
        try:
            dloader = self._new_downloader(item_id, alt_path)
            if album:
                result = dloader.download_release()
            else:
                result = dloader.download_track()
        except (http.HttpError, ConnectionError) as error:
            result = downloader.DownloadResult(
                "failed", "request_error", retryable=http.is_retryable(error)
            )
            self._record_outcome(kind, item_id, result)
        except NonStreamable:
            result = downloader.DownloadResult("failed", "not_streamable")
            self._record_outcome(kind, item_id, result)

        if result.state == "finalized":
            self.download_history.record_legacy_id(item_id)
        return result

    def _record_outcome(self, kind, item_id, result):
        self.run_result.add_item(
            RunItem(self._current_source, kind, str(item_id), result)
        )

    def _record_problem(self, code, message, *, retryable=False, source=None):
        self.run_result.add_problem(
            RunProblem(
                code,
                message,
                self._current_source if source is None else source,
                retryable,
            )
        )

    def _new_downloader(self, item_id, alt_path=None, *, verified_destinations=True):
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
            download_history=self.download_history,
            verified_destinations=verified_destinations,
            on_outcome=self._record_outcome,
        )

    def _resolve_url_download_plan(self, url):
        try:
            url_type, item_id = get_url_info(url)
        except (KeyError, ValueError):
            logger.info(
                f'{RED}Invalid url: "{url}". Use urls from https://play.qobuz.com!'
            )
            return
        return self._resolve_download_plan(url, url_type, item_id)

    def _resolve_download_plan(self, url, url_type, item_id):
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
            occurrences = self._download_playlist_occurrences(plan.item_ids, new_path)
            if plan.create_m3u:
                make_m3u(new_path, self._playlist_finalized_paths(occurrences))
            return occurrences

        for item_id in plan.item_ids:
            self.download_from_id(item_id, plan.album, new_path)

    def _download_playlist_occurrences(self, item_ids, destination):
        return tuple(
            _PlaylistOccurrence(
                item_id,
                self.download_from_id(item_id, False, destination),
            )
            for item_id in item_ids
        )

    @staticmethod
    def _playlist_finalized_paths(occurrences):
        return tuple(
            path
            for occurrence in occurrences
            if occurrence.result.state == "finalized"
            for path in occurrence.result.finalized_paths
        )

    def handle_url(self, url):
        plan = self._resolve_url_download_plan(url)
        if plan:
            self._execute_url_download_plan(plan)

    def download_sources(self, sources: Iterable[Source]) -> RunResult:
        """Download validated sources in order and return the run's outcomes.

        A failed source is recorded as a problem and the run continues with
        the next one. A Qobuz rate-limit abort still propagates.
        """
        for source in sources:
            self._current_source = source.url
            try:
                if source.kind == "lastfm":
                    self.download_lastfm_pl(source.url)
                    continue
                plan = self._resolve_download_plan(
                    source.url, source.url_type, source.item_id
                )
                if plan:
                    self._execute_url_download_plan(plan)
            except http.HttpError as error:
                logger.error(f"{RED}Could not read {source.url}: {error}")
                self._record_problem(
                    "request_error",
                    f"could not read the source: {error}",
                    retryable=http.is_retryable(error),
                )
        return self.run_result

    def download_list_of_urls(self, urls):
        if not urls or not isinstance(urls, list):
            logger.info(f"{OFF}Nothing to download")
            return
        for url in urls:
            self._current_source = url
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

        item_types = ["Albums", "Tracks", "Artists", "Playlists"]
        selected_type = _select_one(
            item_types,
            "I'll search for [number]: ",
        )[:-1].lower()
        say(f"{YELLOW}Ok, we'll search for {selected_type}s{RESET}")
        final_url_list = []
        while True:
            query = prompt(f"{CYAN}Enter your search: [Ctrl + c to quit]{RESET}\n- ")
            say(f"{YELLOW}Searching...{RESET}")
            options = self.search_by_type(query, selected_type, self.interactive_limit)
            if not options:
                say(f"{OFF}Nothing found{RESET}")
                continue
            say(
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
                say(f"{YELLOW}Ok, try again...{RESET}")
                continue
        if final_url_list:
            say(
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

    def download_lastfm_pl(self, playlist_url):
        # Apparently, last fm API doesn't have a playlist endpoint. If you
        # find out that it has, please fix this!
        try:
            html = http.get_text(playlist_url, timeout=10)
        except http.HttpError as e:
            logger.error(f"{RED}Playlist download failed: {e}")
            self._record_problem(
                "request_error",
                f"could not read the Last.fm playlist: {e}",
                retryable=http.is_retryable(e),
                source=playlist_url,
            )
            return
        parser = LastFmPlaylistParser()
        parser.feed(html)

        if not parser.tracks:
            logger.info(f"{OFF}Nothing found")
            self._record_problem(
                "no_tracks",
                "the Last.fm playlist has no readable tracks",
                source=playlist_url,
            )
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
                self._record_problem(
                    "no_match",
                    f'no Qobuz track matches the Last.fm row "{query}"',
                    source=playlist_url,
                )
                continue
            track_id = get_url_info(results[0])[1]
            if track_id:
                track_ids.append(track_id)

        occurrences = self._download_playlist_occurrences(track_ids, pl_directory)
        if not self.no_m3u_for_playlists:
            create_and_return_dir(pl_directory)
            make_m3u(pl_directory, self._playlist_finalized_paths(occurrences))
