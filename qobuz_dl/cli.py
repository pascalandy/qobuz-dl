import configparser
import getpass
import hashlib
import logging
import os
import sys
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from io import StringIO

from qobuz_dl.bundle import Bundle
from qobuz_dl.color import GREEN, RED, YELLOW
from qobuz_dl.commands import QUALITY_CHOICES, RESET_COMMAND, qobuz_dl_args
from qobuz_dl.core import QobuzDL
from qobuz_dl.downloader import DEFAULT_FOLDER, DEFAULT_TRACK

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)

if os.name == "nt":
    OS_CONFIG = os.environ.get("APPDATA")
else:
    OS_CONFIG = os.path.join(os.path.expanduser("~"), ".config")

CONFIG_PATH = os.path.join(OS_CONFIG, "qobuz-dl")
CONFIG_FILE = os.path.join(CONFIG_PATH, "config.ini")
QOBUZ_DB = os.path.join(CONFIG_PATH, "qobuz_dl.db")
SENSITIVE_CONFIG_KEYS = {
    "app_id",
    "email",
    "password",
    "private_key",
    "secrets",
    "user_auth_token",
}


@dataclass(frozen=True)
class _StartupRequirements:
    needs_config: bool
    needs_auth: bool


class _ConfigStorageError(Exception):
    pass


class _ConfigValidationError(Exception):
    pass


_CONFIG_STRING_KEYS = (
    "email",
    "password",
    "default_folder",
    "app_id",
    "folder_format",
    "track_format",
    "secrets",
)
_CONFIG_BOOLEAN_KEYS = (
    "no_m3u",
    "albums_only",
    "no_fallback",
    "og_cover",
    "embed_art",
    "no_cover",
    "no_database",
    "smart_discography",
)


def _secure_config_path(config_file: str) -> None:
    try:
        directory = os.path.dirname(config_file)
        if directory:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            if os.name == "posix":
                os.chmod(directory, 0o700)
        if os.name == "posix":
            with suppress(FileNotFoundError):
                os.chmod(config_file, 0o600)
    except OSError:
        raise _ConfigStorageError from None


def _write_config(config_file: str, config: configparser.ConfigParser) -> None:
    _secure_config_path(config_file)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=os.path.dirname(config_file) or ".",
            prefix=f".{os.path.basename(config_file)}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = stream.name
            if os.name == "posix":
                os.chmod(temporary_path, 0o600)
            config.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, config_file)
        temporary_path = None
    except (OSError, ValueError, TypeError, configparser.Error):
        raise _ConfigStorageError from None
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                os.unlink(temporary_path)


def _classify_startup(arguments):
    if arguments.reset:
        return _StartupRequirements(needs_config=False, needs_auth=False)
    if arguments.purge:
        return _StartupRequirements(needs_config=False, needs_auth=False)
    if arguments.show_config:
        return _StartupRequirements(needs_config=True, needs_auth=False)

    if arguments.command is None:
        return _StartupRequirements(needs_config=True, needs_auth=False)

    command_needs_client = True
    return _StartupRequirements(
        needs_config=command_needs_client,
        needs_auth=command_needs_client,
    )


def _ensure_config_exists(config_file):
    _secure_config_path(config_file)
    if not os.path.isfile(config_file):
        _reset_config(config_file)


def _read_config(config_file):
    config = configparser.ConfigParser()
    try:
        with open(config_file) as stream:
            config.read_file(stream)
    except FileNotFoundError:
        # Preserve the existing --show-config --purge behavior when no config exists.
        return config
    except (OSError, UnicodeError, configparser.Error):
        raise _ConfigValidationError(
            "The configuration file could not be read safely."
        ) from None
    return config


def _required_config_value(config, key):
    try:
        return config[config.default_section][key]
    except KeyError:
        raise _ConfigValidationError(
            f"Required configuration option '{key}' is missing."
        ) from None
    except configparser.InterpolationError:
        raise _ConfigValidationError(
            f"Configuration option '{key}' could not be resolved."
        ) from None


def _load_config_values(config_file):
    config = _read_config(config_file)
    keys = (
        *_CONFIG_STRING_KEYS,
        *_CONFIG_BOOLEAN_KEYS,
        "default_quality",
        "default_limit",
    )
    values = {key: _required_config_value(config, key) for key in keys}

    for key in _CONFIG_BOOLEAN_KEYS:
        try:
            values[key] = config.getboolean(config.default_section, key)
        except ValueError:
            raise _ConfigValidationError(f"'{key}' must be a Boolean.") from None

    try:
        values["default_quality"] = int(values["default_quality"])
    except ValueError:
        raise _ConfigValidationError(
            "'default_quality' must be one of 5, 6, 7, 27."
        ) from None
    if values["default_quality"] not in QUALITY_CHOICES:
        raise _ConfigValidationError(
            "'default_quality' must be one of 5, 6, 7, 27."
        ) from None

    try:
        values["default_limit"] = int(values["default_limit"])
    except ValueError:
        raise _ConfigValidationError("'default_limit' must be an integer.") from None

    values["secrets"] = [secret for secret in values["secrets"].split(",") if secret]
    return values


def _redacted_config_text(config_file):
    try:
        config = _read_config(config_file)
        for section in [config.default_section, *config.sections()]:
            values = config[section]
            for key in SENSITIVE_CONFIG_KEYS:
                if key in values:
                    values[key] = "<redacted>"

        buffer = StringIO()
        config.write(buffer)
        return buffer.getvalue()
    except _ConfigValidationError:
        raise
    except (OSError, ValueError, TypeError, configparser.Error):
        raise _ConfigValidationError(
            "The configuration file could not be displayed safely."
        ) from None


def _reset_config(config_file):
    _secure_config_path(config_file)
    logging.info(f"{YELLOW}Creating config file: {config_file}")
    config = configparser.ConfigParser()
    config["DEFAULT"]["email"] = input("Enter your email:\n- ")
    password = getpass.getpass("Enter your password (input is hidden): ")
    config["DEFAULT"]["password"] = hashlib.md5(password.encode("utf-8")).hexdigest()
    config["DEFAULT"]["default_folder"] = (
        input("Folder for downloads (leave empty for default 'Qobuz Downloads')\n- ")
        or "Qobuz Downloads"
    )
    config["DEFAULT"]["default_quality"] = (
        input(
            "Download quality (5, 6, 7, 27) "
            "[320, LOSSLESS, 24B <96KHZ, 24B >96KHZ]"
            "\n(leave empty for default '6')\n- "
        )
        or "6"
    )
    config["DEFAULT"]["default_limit"] = "20"
    config["DEFAULT"]["no_m3u"] = "false"
    config["DEFAULT"]["albums_only"] = "false"
    config["DEFAULT"]["no_fallback"] = "false"
    config["DEFAULT"]["og_cover"] = "false"
    config["DEFAULT"]["embed_art"] = "false"
    config["DEFAULT"]["no_cover"] = "false"
    config["DEFAULT"]["no_database"] = "false"
    logging.info(f"{YELLOW}Getting tokens. Please wait...")
    bundle = Bundle()
    config["DEFAULT"]["app_id"] = str(bundle.get_app_id())
    config["DEFAULT"]["secrets"] = ",".join(bundle.get_secrets().values())
    config["DEFAULT"]["folder_format"] = DEFAULT_FOLDER
    config["DEFAULT"]["track_format"] = DEFAULT_TRACK
    config["DEFAULT"]["smart_discography"] = "false"
    _write_config(config_file, config)
    logging.info(
        f"{GREEN}Config file updated. Edit more options in {config_file}"
        "\nso you don't have to call custom flags every time you run "
        "a qobuz-dl command."
    )


def _quality_fallback_enabled(cli_no_fallback, config_no_fallback):
    return not (cli_no_fallback or config_no_fallback)


def _handle_commands(qobuz, arguments):
    try:
        if arguments.command == "dl":
            qobuz.download_list_of_urls(arguments.SOURCE)
        elif arguments.command == "lucky":
            query = " ".join(arguments.QUERY)
            qobuz.lucky_type = arguments.type
            qobuz.lucky_limit = arguments.number
            qobuz.lucky_mode(query)
        else:
            qobuz.interactive_limit = arguments.limit
            qobuz.interactive()

    except KeyboardInterrupt:
        logging.info(
            f"{RED}Interrupted by user\n{YELLOW}Already downloaded items will "
            "be skipped if you try to download the same releases again."
        )


def main():
    parser = qobuz_dl_args()
    arguments = parser.parse_args()
    startup = _classify_startup(arguments)

    config_values = None
    redacted_config = None
    try:
        if arguments.reset:
            sys.exit(_reset_config(CONFIG_FILE))
        if startup.needs_config:
            _ensure_config_exists(CONFIG_FILE)
            if startup.needs_auth or arguments.show_config:
                config_values = _load_config_values(CONFIG_FILE)
        if arguments.show_config:
            redacted_config = _redacted_config_text(CONFIG_FILE)
    except _ConfigStorageError:
        sys.exit(
            f"{RED}Unable to access configuration securely. "
            "Check its directory permissions and available disk space."
        )
    except _ConfigValidationError as error:
        sys.exit(
            f"{RED}Your config file is corrupted: {error}! "
            f"Run '{RESET_COMMAND}' to fix this "
            "(or 'qobuz-dl -r' if installed)."
        )

    if arguments.command is None and not arguments.show_config and not arguments.purge:
        parser.print_help()
        sys.exit(0)

    if arguments.show_config:
        print(f"Configuration: {CONFIG_FILE}\nDatabase: {QOBUZ_DB}\n---")
        print(redacted_config)
        sys.exit()

    if arguments.purge:
        try:
            os.remove(QOBUZ_DB)
        except FileNotFoundError:
            logging.warning(f"{GREEN}The database is already absent.")
            return
        except OSError:
            sys.exit(f"Unable to delete database at {QOBUZ_DB}. Check its permissions.")
        logging.warning(f"{GREEN}The database was deleted.")
        return

    if startup.needs_auth:
        arguments = qobuz_dl_args(
            config_values["default_quality"],
            config_values["default_limit"],
            config_values["default_folder"],
        ).parse_args()

    qobuz = QobuzDL(
        arguments.directory,
        arguments.quality,
        arguments.embed_art or config_values["embed_art"],
        ignore_singles_eps=arguments.albums_only or config_values["albums_only"],
        no_m3u_for_playlists=arguments.no_m3u or config_values["no_m3u"],
        quality_fallback=_quality_fallback_enabled(
            arguments.no_fallback,
            config_values["no_fallback"],
        ),
        cover_og_quality=arguments.og_cover or config_values["og_cover"],
        no_cover=arguments.no_cover or config_values["no_cover"],
        downloads_db=None
        if config_values["no_database"] or arguments.no_db
        else QOBUZ_DB,
        folder_format=arguments.folder_format or config_values["folder_format"],
        track_format=arguments.track_format or config_values["track_format"],
        smart_discography=(
            arguments.smart_discography or config_values["smart_discography"]
        ),
    )
    qobuz.initialize_client(
        config_values["email"],
        config_values["password"],
        config_values["app_id"],
        config_values["secrets"],
    )

    _handle_commands(qobuz, arguments)


if __name__ == "__main__":
    sys.exit(main())
