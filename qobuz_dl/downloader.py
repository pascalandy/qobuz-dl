import errno
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from typing import Literal, Tuple

import qobuz_dl.http as http
import qobuz_dl.metadata as metadata
from qobuz_dl.color import CYAN, GREEN, OFF, RED, YELLOW
from qobuz_dl.db import DownloadHistory, MediaProperties, VerifiedArtifact
from qobuz_dl.sanitize import filename_component, sanitize_filename, sanitize_filepath

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
DEFAULT_NAME_MAX = 255

logger = logging.getLogger(__name__)


def validate_cover_options(embed_art: bool, no_cover: bool) -> None:
    if embed_art and no_cover:
        raise ValueError("--embed-art cannot be used with --no-cover")


@dataclass(frozen=True)
class DownloadResult:
    state: Literal["finalized", "ignored", "failed"]
    reason: Literal[
        "downloaded",
        "verified_artifact",
        "existing_file",
        "database_duplicate",
        "type_filter",
        "quality_filter",
        "demo",
        "missing_url",
        "not_streamable",
        "request_error",
        "tagging_error",
        "path_conflict",
        "media_error",
        "publish_error",
        "empty_release",
    ]
    finalized_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class _DownloadPreparation:
    directory: str
    is_mp3: bool
    track_format: str


@dataclass(frozen=True)
class Create:
    pass


@dataclass(frozen=True)
class Reuse:
    artifact: VerifiedArtifact


@dataclass(frozen=True)
class Replace:
    artifact: VerifiedArtifact


@dataclass(frozen=True)
class Conflict:
    pass


DestinationDecision = Create | Reuse | Replace | Conflict


@dataclass(frozen=True)
class _ExpectedMedia:
    codec: Literal["flac", "mp3"]
    bit_depth: int | None
    sample_rate_hz: int | None
    bitrate_bps: int | None


class _TransactionFailure(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _same_artifact_content(first, second):
    return (
        first.track_id == second.track_id
        and first.requested_quality == second.requested_quality
        and first.media == second.media
        and first.size_bytes == second.size_bytes
        and first.sha256 == second.sha256
    )


@dataclass
class _DestinationTransaction:
    final_path: str
    directory: str
    staged_path: str
    backup_path: str
    backup_artifact: VerifiedArtifact | None = None
    public_may_be_owned: bool = False
    preserve_directory: bool = False
    completed: bool = False

    @classmethod
    def create(cls, final_path):
        parent = os.path.dirname(final_path)
        # This assumes a stable destination parent and excludes arbitrary mutation
        # by another process running as the same user.
        directory = tempfile.mkdtemp(prefix=".qdl-", dir=parent)
        suffix = os.path.splitext(final_path)[1]
        staged_path = os.path.join(directory, f"staged{suffix}")
        try:
            descriptor = os.open(
                staged_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o666,
            )
            os.close(descriptor)
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return cls(
            final_path=final_path,
            directory=directory,
            staged_path=staged_path,
            backup_path=os.path.join(directory, f"backup{suffix}"),
        )

    def fsync_staged(self):
        try:
            with open(self.staged_path, "r+b") as staged:
                os.fsync(staged.fileno())
        except OSError as error:
            raise _TransactionFailure("publish_error") from error

    def displace(self, expected):
        current = DownloadHistory.inspect_artifact(
            expected.track_id,
            self.final_path,
            expected.requested_quality,
        )
        if current is None or not _same_artifact_content(expected, current):
            raise _TransactionFailure("path_conflict")

        self.preserve_directory = True
        # Portable filesystems have no conditional rename. The post-move check
        # keeps a file swapped in after this recheck inside the private directory.
        try:
            os.rename(self.final_path, self.backup_path)
        except FileNotFoundError as error:
            raise _TransactionFailure("path_conflict") from error
        except OSError as error:
            raise _TransactionFailure("publish_error") from error
        moved = DownloadHistory.inspect_artifact(
            expected.track_id,
            self.backup_path,
            expected.requested_quality,
        )
        if moved is None or not _same_artifact_content(expected, moved):
            raise _TransactionFailure("path_conflict")
        self.backup_artifact = moved

    def publish(self):
        self.public_may_be_owned = True
        try:
            os.link(self.staged_path, self.final_path)
            return
        except FileExistsError as error:
            self.public_may_be_owned = False
            raise _TransactionFailure("path_conflict") from error
        except OSError as error:
            unsupported = {
                errno.EPERM,
                errno.EXDEV,
                getattr(errno, "ENOSYS", errno.EPERM),
                getattr(errno, "ENOTSUP", errno.EPERM),
                getattr(errno, "EOPNOTSUPP", errno.EPERM),
            }
            if error.errno not in unsupported:
                raise _TransactionFailure("publish_error") from error
        self._copy_no_clobber(self.staged_path, self.final_path)

    def prove_publication(self, staged_artifact):
        final_artifact = DownloadHistory.inspect_artifact(
            staged_artifact.track_id,
            self.final_path,
            staged_artifact.requested_quality,
        )
        if final_artifact is None or not _same_artifact_content(
            staged_artifact, final_artifact
        ):
            raise _TransactionFailure("publish_error")
        return final_artifact

    def commit(self):
        self.completed = True
        try:
            shutil.rmtree(self.directory)
        except OSError as error:
            logger.debug(
                "Could not remove completed transaction %s: %s", self.directory, error
            )

    def retain_recovery(self):
        self.completed = True
        self.preserve_directory = True
        logger.error("%sRecovery data was preserved at %s", RED, self.directory)

    def abort(self):
        if self.completed:
            return
        if not (self.preserve_directory or self.public_may_be_owned):
            shutil.rmtree(self.directory, ignore_errors=True)
            return

        self.preserve_directory = True
        try:
            if self.public_may_be_owned:
                self._quarantine_public()
            if self.backup_artifact is not None:
                try:
                    self._restore_backup()
                except Exception:
                    pass
        finally:
            logger.error("%sRecovery data was preserved at %s", RED, self.directory)

    def _quarantine_public(self):
        quarantine_path = os.path.join(self.directory, f"quarantine-{uuid.uuid4().hex}")
        try:
            os.rename(self.final_path, quarantine_path)
        except FileNotFoundError:
            pass
        except BaseException as error:
            logger.error("%sCould not quarantine failed publication: %s", RED, error)
            if not isinstance(error, Exception):
                raise
        else:
            self.public_may_be_owned = False

    def _restore_backup(self):
        if os.path.lexists(self.final_path):
            return
        try:
            self.public_may_be_owned = True
            self._copy_no_clobber(self.backup_path, self.final_path)
            restored = DownloadHistory.inspect_artifact(
                self.backup_artifact.track_id,
                self.final_path,
                self.backup_artifact.requested_quality,
            )
            if restored is None or not _same_artifact_content(
                self.backup_artifact, restored
            ):
                self._quarantine_public()
                return
            self.public_may_be_owned = False
        except BaseException as error:
            logger.error("%sCould not restore prior destination: %s", RED, error)
            if self.public_may_be_owned:
                self._quarantine_public()
            raise

    def _copy_no_clobber(self, source_path, destination_path):
        try:
            with (
                open(source_path, "rb") as source,
                open(destination_path, "xb") as destination,
            ):
                shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
        except FileExistsError as error:
            self.public_may_be_owned = False
            raise _TransactionFailure("path_conflict") from error
        except OSError as error:
            raise _TransactionFailure("publish_error") from error


def _destination_name_max(directory: str) -> int:
    pathconf = getattr(os, "pathconf", None)
    if pathconf is None:
        return DEFAULT_NAME_MAX

    try:
        name_max = pathconf(directory, "PC_NAME_MAX")
    except ValueError:
        return DEFAULT_NAME_MAX
    except OSError as error:
        unsupported_errors = {
            errno.EINVAL,
            getattr(errno, "ENOSYS", errno.EINVAL),
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if error.errno in unsupported_errors:
            return DEFAULT_NAME_MAX
        raise

    return name_max if name_max > 0 else DEFAULT_NAME_MAX


def _aggregate_download_results(results: list[DownloadResult]) -> DownloadResult:
    finalized_paths = tuple(
        path for result in results for path in result.finalized_paths
    )
    if not results:
        return DownloadResult("ignored", "empty_release")

    failed = next((result for result in results if result.state == "failed"), None)
    if failed:
        return DownloadResult("failed", failed.reason, finalized_paths)

    ignored = next((result for result in results if result.state == "ignored"), None)
    if ignored:
        return DownloadResult("ignored", ignored.reason, finalized_paths)

    if any(result.reason == "downloaded" for result in results):
        reason = "downloaded"
    elif any(result.reason == "verified_artifact" for result in results):
        reason = "verified_artifact"
    else:
        reason = "existing_file"
    return DownloadResult("finalized", reason, finalized_paths)


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
        download_history: DownloadHistory | None = None,
        verified_destinations: bool = False,
    ):
        validate_cover_options(embed_art, no_cover)
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
        self.download_history = download_history
        self.verified_destinations = verified_destinations

    def download_id_by_type(self, track=True):
        if track:
            return self.download_track()
        return self.download_release()

    def download_release(self):
        try:
            meta = self.client.get_album_meta(self.item_id)
        except (http.HttpError, ConnectionError) as error:
            logger.error(f"{RED}Error getting release: {error}. Skipping...")
            return DownloadResult("failed", "request_error")

        if not meta.get("streamable"):
            logger.error(f"{RED}This release is not streamable. Skipping...")
            return DownloadResult("failed", "not_streamable")

        if self.albums_only and (
            meta.get("release_type") != "album"
            or meta.get("artist", {}).get("name") == "Various Artists"
        ):
            logger.info(f"{OFF}Ignoring Single/EP/VA: {meta.get('title', 'n/a')}")
            return DownloadResult("ignored", "type_filter")

        tracks = meta["tracks"]["items"]
        if not tracks:
            return DownloadResult("ignored", "empty_release")

        album_title = _get_title(meta)

        first_track_url = None
        try:
            if self.verified_destinations or not self._is_mp3():
                first_track_url = self.client.get_track_url(
                    tracks[0]["id"], fmt_id=self.quality
                )
            preparation = self._prepare_release_download(
                meta, album_title, first_track_url
            )
        except (http.HttpError, ConnectionError) as error:
            logger.error(f"{RED}Error getting release: {error}. Skipping...")
            return DownloadResult("failed", "request_error")

        if "goodies" in meta:
            try:
                _get_extra(
                    meta["goodies"][0]["url"], preparation.directory, "booklet.pdf"
                )
            except Exception as error:
                logger.debug("Skipping booklet download: %s", error)
        media_numbers = [track["media_number"] for track in tracks]
        is_multiple = len(set(media_numbers)) > 1
        results = []
        for index, track in enumerate(tracks):
            try:
                parsed_url = (
                    first_track_url
                    if index == 0 and first_track_url is not None
                    else self.client.get_track_url(track["id"], fmt_id=self.quality)
                )
                if "sample" in parsed_url:
                    logger.info(f"{OFF}Demo. Skipping")
                    results.append(DownloadResult("ignored", "demo"))
                    continue
                _file_format, quality_met, bit_depth, sampling_rate = self._get_format(
                    parsed_url
                )
                if not self._quality_allows_download(_get_title(track), quality_met):
                    results.append(DownloadResult("ignored", "quality_filter"))
                    continue
                if parsed_url.get("url"):
                    quality = (
                        f"{bit_depth}-bit/{sampling_rate} kHz"
                        if bit_depth is not None and sampling_rate is not None
                        else "unknown"
                    )
                    logger.info(f"{OFF}Track quality: {quality}")
                result = self._download_prepared_track(
                    preparation,
                    parsed_url,
                    track,
                    meta,
                    False,
                    track["media_number"] if is_multiple else None,
                )
            except (http.HttpError, ConnectionError) as error:
                logger.error(f"{RED}Error getting release: {error}. Skipping...")
                results.append(DownloadResult("failed", "request_error"))
                break
            results.append(result)

        aggregate = _aggregate_download_results(results)
        if aggregate.state == "finalized":
            logger.info(f"{GREEN}Completed")
        return aggregate

    def download_track(self):
        try:
            parsed_url = self.client.get_track_url(self.item_id, self.quality)
            if "sample" in parsed_url:
                logger.info(f"{OFF}Demo. Skipping")
                return DownloadResult("ignored", "demo")

            meta = self.client.get_track_meta(self.item_id)
            track_title = _get_title(meta)
            artist = _safe_get(meta, "performer", "name")
            logger.info(f"\n{YELLOW}Downloading: {artist} - {track_title}")
            preparation = self._prepare_track_download(meta, parsed_url, track_title)
            if not preparation:
                return DownloadResult("ignored", "quality_filter")
            result = self._download_prepared_track(
                preparation,
                parsed_url,
                meta,
                meta,
                True,
                None,
            )
        except (http.HttpError, ConnectionError) as error:
            logger.error(f"{RED}Error getting release: {error}. Skipping...")
            return DownloadResult("failed", "request_error")

        if result.state == "finalized":
            logger.info(f"{GREEN}Completed")
        return result

    def _prepare_release_download(self, meta, album_title, first_track_url):
        file_format, _quality_met, bit_depth, sampling_rate = self._get_format(
            first_track_url
        )

        logger.info(
            f"\n{YELLOW}Downloading: {album_title}\nQuality: {file_format}"
            f" ({bit_depth}/{sampling_rate})\n"
        )
        album_attr = self._get_album_attr(
            meta, album_title, file_format, bit_depth, sampling_rate
        )
        preparation = self._prepare_destination(album_attr, file_format)
        self._download_cover(meta["image"]["large"], preparation.directory)
        return preparation

    def _prepare_track_download(self, meta, track_url_dict, track_title):
        file_format, quality_met, bit_depth, sampling_rate = self._get_format(
            track_url_dict
        )

        if not self._quality_allows_download(track_title, quality_met):
            return None

        track_attr = self._get_track_attr(meta, track_title, bit_depth, sampling_rate)
        preparation = self._prepare_destination(track_attr, file_format)
        self._download_cover(meta["album"]["image"]["large"], preparation.directory)
        return preparation

    def existing_track_path(self):
        track_url = self.client.get_track_url(self.item_id, fmt_id=self.quality)
        if "sample" in track_url:
            return None

        metadata = self.client.get_track_meta(self.item_id)
        track_title = _get_title(metadata)
        directory, quality_met, track_format = self._track_destination(
            metadata, track_url, track_title
        )
        if not (self.downgrade_quality or quality_met) or not os.path.isdir(directory):
            return None

        final_file = self._track_final_path(
            directory, metadata, self._is_mp3(), track_format
        )
        return final_file if os.path.isfile(final_file) else None

    def _track_destination(self, meta, track_url_dict, track_title):
        file_format, quality_met, bit_depth, sampling_rate = self._get_format(
            track_url_dict
        )
        track_attr = self._get_track_attr(meta, track_title, bit_depth, sampling_rate)
        folder_format, track_format = _clean_format_str(
            self.folder_format, self.track_format, file_format
        )
        directory = os.path.join(
            self.path, sanitize_filepath(folder_format.format(**track_attr))
        )
        return directory, quality_met, track_format

    def _quality_allows_download(self, item_title, quality_met):
        if self.downgrade_quality or quality_met:
            return True
        logger.info(
            f"{OFF}Skipping {item_title} as it doesn't meet quality requirement"
        )
        return False

    def _prepare_destination(self, folder_attr, file_format):
        folder_format, track_format = _clean_format_str(
            self.folder_format, self.track_format, file_format
        )
        sanitized_title = sanitize_filepath(folder_format.format(**folder_attr))
        directory = os.path.join(self.path, sanitized_title)
        os.makedirs(directory, exist_ok=True)
        return _DownloadPreparation(
            directory=directory,
            is_mp3=file_format == "MP3",
            track_format=track_format,
        )

    def _download_cover(self, cover_url, directory):
        if self.no_cover:
            logger.info(f"{OFF}Skipping cover")
            return
        _get_extra(cover_url, directory, og_quality=self.cover_og_quality)

    def _expected_media(self, track_url_dict) -> _ExpectedMedia | None:
        format_id = self._effective_format_id(track_url_dict)
        if format_id == 5:
            codec: Literal["flac", "mp3"] = "mp3"
        elif format_id in {6, 7, 27}:
            codec = "flac"
        else:
            return None

        mime_type = track_url_dict.get("mime_type")
        expected_mime = "audio/mpeg" if codec == "mp3" else "audio/flac"
        if mime_type is not None and (
            not isinstance(mime_type, str)
            or mime_type.split(";", 1)[0].strip().lower() != expected_mime
        ):
            return None
        sample_rate = track_url_dict.get("sampling_rate")
        if (
            not isinstance(sample_rate, bool)
            and isinstance(sample_rate, (int, float))
            and sample_rate > 0
        ):
            scaled_sample_rate = (
                sample_rate * 1000 if sample_rate < 1000 else sample_rate
            )
            sample_rate_hz = (
                int(scaled_sample_rate)
                if float(scaled_sample_rate).is_integer()
                else None
            )
        else:
            sample_rate_hz = None

        bit_depth = track_url_dict.get("bit_depth") if codec == "flac" else None
        if (
            isinstance(bit_depth, bool)
            or not isinstance(bit_depth, (int, float))
            or bit_depth <= 0
            or not float(bit_depth).is_integer()
        ):
            bit_depth = None
        elif bit_depth is not None:
            bit_depth = int(bit_depth)

        bitrate_bps = 320000 if codec == "mp3" else None
        return _ExpectedMedia(codec, bit_depth, sample_rate_hz, bitrate_bps)

    @staticmethod
    def _effective_format_id(track_url_dict) -> int | None:
        raw_format_id = track_url_dict.get("format_id")
        if isinstance(raw_format_id, bool):
            return None
        if isinstance(raw_format_id, float) and not raw_format_id.is_integer():
            return None
        try:
            return int(raw_format_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _media_matches(expected: _ExpectedMedia, actual: MediaProperties) -> bool:
        if expected.codec != actual.codec:
            return False
        if (
            expected.sample_rate_hz is not None
            and expected.sample_rate_hz != actual.sample_rate_hz
        ):
            return False
        if expected.codec == "flac":
            return (
                expected.sample_rate_hz is not None
                and expected.bit_depth is not None
                and expected.bit_depth == actual.bit_depth
            )
        return (
            actual.bitrate_bps is not None
            and expected.bitrate_bps is not None
            and abs(actual.bitrate_bps - expected.bitrate_bps) < 500
        )

    def _destination_decision(
        self,
        *,
        track_id,
        final_file,
        expected_media: _ExpectedMedia | None,
    ) -> DestinationDecision:
        artifact = None
        if self.download_history is not None:
            artifact = self.download_history.verified_artifact(track_id, final_file)
        if artifact is not None:
            if expected_media is not None and self._media_matches(
                expected_media, artifact.media
            ):
                return Reuse(artifact)
            return Replace(artifact)
        if os.path.lexists(final_file):
            return Conflict()
        return Create()

    def _download_prepared_track(
        self,
        preparation,
        track_url_dict,
        track_metadata,
        album_or_track_metadata,
        is_track,
        multiple=None,
    ):
        root_dir = preparation.directory

        if multiple:
            root_dir = os.path.join(root_dir, f"Disc {multiple}")
            os.makedirs(root_dir, exist_ok=True)

        track_title = track_metadata.get("title")
        expected_media = (
            self._expected_media(track_url_dict) if self.verified_destinations else None
        )
        is_mp3 = (
            expected_media.codec == "mp3"
            if expected_media is not None
            else preparation.is_mp3
        )
        final_file = self._track_final_path(
            root_dir,
            track_metadata,
            is_mp3,
            preparation.track_format,
        )

        if self.verified_destinations:
            return self._download_verified_track(
                root_dir=root_dir,
                final_file=final_file,
                track_url_dict=track_url_dict,
                track_metadata=track_metadata,
                album_or_track_metadata=album_or_track_metadata,
                is_track=is_track,
                expected_media=expected_media,
                is_mp3=is_mp3,
            )

        if os.path.isfile(final_file):
            logger.info(f"{OFF}{track_title} was already downloaded")
            return DownloadResult("finalized", "existing_file", (final_file,))

        url = track_url_dict.get("url")
        if not url:
            logger.info(f"{OFF}Track not available for download")
            return DownloadResult("failed", "missing_url")

        filename = os.path.join(root_dir, f".qdl-{uuid.uuid4().hex}.tmp")
        descriptor = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o666,
        )
        try:
            os.close(descriptor)
            download_with_progress(
                url,
                filename,
                filename,
                retry_rate_limited=True,
            )
            tag_function = metadata.tag_mp3 if preparation.is_mp3 else metadata.tag_flac
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
                finalized_paths = (final_file,) if os.path.isfile(final_file) else ()
                return DownloadResult("failed", "tagging_error", finalized_paths)

            if not os.path.isfile(final_file):
                logger.error(f"{RED}Error tagging the file: no final file produced")
                return DownloadResult("failed", "tagging_error")
            if self.download_history is not None:
                self.download_history.record_finalized(
                    track_id=track_metadata["id"],
                    path=final_file,
                    requested_quality=int(self.quality),
                )
            return DownloadResult("finalized", "downloaded", (final_file,))
        finally:
            try:
                os.remove(filename)
            except FileNotFoundError:
                pass
            except OSError as error:
                logger.debug(
                    "Could not remove temporary download %s: %s", filename, error
                )

    def _download_verified_track(
        self,
        *,
        root_dir,
        final_file,
        track_url_dict,
        track_metadata,
        album_or_track_metadata,
        is_track,
        expected_media,
        is_mp3,
    ):
        url = track_url_dict.get("url")
        if not url:
            logger.info(f"{OFF}Track not available for download")
            return DownloadResult("failed", "missing_url")

        if expected_media is None:
            logger.error(f"{RED}Media response did not identify a supported format")
            return DownloadResult("failed", "media_error")

        decision = self._destination_decision(
            track_id=track_metadata["id"],
            final_file=final_file,
            expected_media=expected_media,
        )
        if isinstance(decision, Reuse):
            logger.info(f"{OFF}{track_metadata.get('title')} was already downloaded")
            return DownloadResult("finalized", "verified_artifact", (final_file,))
        if isinstance(decision, Conflict):
            logger.error(f"{RED}Destination path is already occupied: {final_file}")
            return DownloadResult("failed", "path_conflict")

        try:
            transaction = _DestinationTransaction.create(final_file)
        except OSError as error:
            logger.error(f"{RED}Could not create private download directory: {error}")
            return DownloadResult("failed", "publish_error")
        try:
            download_with_progress(
                url,
                transaction.staged_path,
                transaction.staged_path,
                retry_rate_limited=True,
            )
            tag_function = metadata.tag_mp3 if is_mp3 else metadata.tag_flac
            try:
                tag_function(
                    transaction.staged_path,
                    root_dir,
                    final_file,
                    track_metadata,
                    album_or_track_metadata,
                    is_track,
                    self.embed_art,
                    finalize=False,
                )
            except Exception as error:
                logger.error(f"{RED}Error tagging the file: {error}", exc_info=True)
                raise _TransactionFailure("tagging_error") from error

            transaction.fsync_staged()
            staged_artifact = DownloadHistory.inspect_artifact(
                track_id=track_metadata["id"],
                path=transaction.staged_path,
                requested_quality=int(self.quality),
            )
            if staged_artifact is None or not self._media_matches(
                expected_media, staged_artifact.media
            ):
                logger.error(f"{RED}Downloaded media did not match the response")
                raise _TransactionFailure("media_error")

            if isinstance(decision, Replace):
                transaction.displace(decision.artifact)
            transaction.publish()
            final_artifact = transaction.prove_publication(staged_artifact)

        except _TransactionFailure as error:
            transaction.abort()
            return DownloadResult("failed", error.reason)
        except BaseException:
            transaction.abort()
            raise

        if self.download_history is not None:
            try:
                recorded = self.download_history.record_verified(final_artifact)
            except BaseException:
                transaction.retain_recovery()
                raise
            if recorded != final_artifact:
                transaction.retain_recovery()
                return DownloadResult("failed", "publish_error")

        transaction.commit()
        return DownloadResult("finalized", "downloaded", (final_file,))

    def _is_mp3(self):
        return int(self.quality) == 5

    def _track_final_path(self, root_dir, track_metadata, is_mp3, track_format=None):
        extension = ".mp3" if is_mp3 else ".flac"
        track_title = track_metadata.get("title")
        artist = _safe_get(track_metadata, "performer", "name")
        filename_attr = self._get_filename_attr(artist, track_metadata, track_title)
        if track_format is None:
            _folder_format, track_format = _clean_format_str(
                self.folder_format, self.track_format, "MP3" if is_mp3 else "FLAC"
            )
        component = filename_component(
            track_format.format(**filename_attr),
            extension,
            _destination_name_max(root_dir),
        )
        return os.path.join(root_dir, component)

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

    def _get_format(self, track_url_dict):
        quality_met = True
        format_id = (
            self._effective_format_id(track_url_dict)
            if isinstance(track_url_dict, dict)
            else None
        )
        requested_mp3_legacy = not self.verified_destinations and int(self.quality) == 5
        if not requested_mp3_legacy:
            restrictions = track_url_dict.get("restrictions")
            if isinstance(restrictions, list) and any(
                restriction.get("code") == QL_DOWNGRADE for restriction in restrictions
            ):
                quality_met = False

        if self.verified_destinations:
            if format_id == 5:
                return ("MP3", quality_met, None, None)
            if format_id not in {6, 7, 27}:
                return ("Unknown", quality_met, None, None)
        elif requested_mp3_legacy:
            return ("MP3", quality_met, None, None)

        try:
            return (
                "FLAC",
                quality_met,
                track_url_dict["bit_depth"],
                track_url_dict["sampling_rate"],
            )
        except KeyError:
            return ("Unknown", quality_met, None, None)


def download_with_progress(
    url, fname, desc, *, retry_rate_limited=False, after_write=None
):
    """Stream ``url`` to ``fname``, logging throttled progress updates."""
    next_report = PROGRESS_MIN_INTERVAL_BYTES

    def show_progress(size, downloaded, total):
        nonlocal next_report
        if after_write is not None:
            after_write(size, downloaded, total)
        if not total:
            return
        report_interval = max(total // 100, PROGRESS_MIN_INTERVAL_BYTES)
        if downloaded >= next_report or downloaded >= total:
            logger.info(f"{CYAN}{downloaded}/{total} /// {desc}")
            while next_report <= downloaded:
                next_report += report_interval

    try:
        http.stream_download(
            url,
            fname,
            progress=show_progress,
            retry_rate_limited=retry_rate_limited,
        )
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
