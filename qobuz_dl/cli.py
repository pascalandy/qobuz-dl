import configparser
import getpass
import glob
import hashlib
import logging
import os
import sys
from dataclasses import dataclass
from io import StringIO

from qobuz_dl.bundle import Bundle
from qobuz_dl.color import GREEN, RED, YELLOW
from qobuz_dl.commands import qobuz_dl_args
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


def _classify_startup(arguments):
    if arguments.reset:
        return _StartupRequirements(needs_config=False, needs_auth=False)
    if arguments.purge:
        return _StartupRequirements(needs_config=False, needs_auth=False)
    if arguments.show_config:
        return _StartupRequirements(needs_config=True, needs_auth=False)

    command_needs_client = arguments.command is not None
    return _StartupRequirements(
        needs_config=command_needs_client,
        needs_auth=command_needs_client,
    )


def _ensure_config_exists(config_file):
    if not os.path.isdir(CONFIG_PATH) or not os.path.isfile(config_file):
        _reset_config(config_file)


def _load_config_values(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)

    values = {
        "email": config["DEFAULT"]["email"],
        "password": config["DEFAULT"]["password"],
        "default_folder": config["DEFAULT"]["default_folder"],
        "default_limit": config["DEFAULT"]["default_limit"],
        "default_quality": config["DEFAULT"]["default_quality"],
        "no_m3u": config.getboolean("DEFAULT", "no_m3u"),
        "albums_only": config.getboolean("DEFAULT", "albums_only"),
        "no_fallback": config.getboolean("DEFAULT", "no_fallback"),
        "og_cover": config.getboolean("DEFAULT", "og_cover"),
        "embed_art": config.getboolean("DEFAULT", "embed_art"),
        "no_cover": config.getboolean("DEFAULT", "no_cover"),
        "no_database": config.getboolean("DEFAULT", "no_database"),
        "app_id": config["DEFAULT"]["app_id"],
        "smart_discography": config.getboolean("DEFAULT", "smart_discography"),
        "folder_format": config["DEFAULT"]["folder_format"],
        "track_format": config["DEFAULT"]["track_format"],
    }
    values["secrets"] = [
        secret for secret in config["DEFAULT"]["secrets"].split(",") if secret
    ]
    return values


def _redacted_config_text(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)
    for section in [config.default_section, *config.sections()]:
        values = config[section]
        for key in SENSITIVE_CONFIG_KEYS:
            if key in values:
                values[key] = "<redacted>"

    buffer = StringIO()
    config.write(buffer)
    return buffer.getvalue()


def _reset_config(config_file):
    logging.info(f"{YELLOW}Creating config file: {config_file}")
    config_directory = os.path.dirname(config_file)
    if config_directory:
        os.makedirs(config_directory, exist_ok=True)
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
    with open(config_file, "w") as configfile:
        config.write(configfile)
    logging.info(
        f"{GREEN}Config file updated. Edit more options in {config_file}"
        "\nso you don't have to call custom flags every time you run "
        "a qobuz-dl command."
    )


def _quality_fallback_enabled(cli_no_fallback, config_no_fallback):
    return not (cli_no_fallback or config_no_fallback)


def _remove_leftovers(directory):
    directory = os.path.join(directory, "**", ".*.tmp")
    for i in glob.glob(directory, recursive=True):
        try:
            os.remove(i)
        except OSError:
            pass


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

    finally:
        _remove_leftovers(qobuz.directory)


def main():
    parser = qobuz_dl_args()
    arguments = parser.parse_args()
    startup = _classify_startup(arguments)

    if arguments.reset:
        sys.exit(_reset_config(CONFIG_FILE))

    if arguments.command is None and not arguments.show_config and not arguments.purge:
        parser.print_help()
        sys.exit(0)

    config_values = None
    if startup.needs_config:
        try:
            _ensure_config_exists(CONFIG_FILE)
            config_values = _load_config_values(CONFIG_FILE)
        except (KeyError, UnicodeDecodeError, configparser.Error) as error:
            sys.exit(
                f"{RED}Your config file is corrupted: {error}! "
                "Run 'uvx qobuz-dl -r' to fix this "
                "(or 'qobuz-dl -r' if installed)."
            )

    if arguments.show_config:
        print(f"Configuration: {CONFIG_FILE}\nDatabase: {QOBUZ_DB}\n---")
        print(_redacted_config_text(CONFIG_FILE))
        sys.exit()

    if arguments.purge:
        try:
            os.remove(QOBUZ_DB)
        except FileNotFoundError:
            pass
        sys.exit(f"{GREEN}The database was deleted.")

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
