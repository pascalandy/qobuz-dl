import argparse
from importlib import metadata

from qobuz_dl.console import (
    EXIT_CODE_MEANINGS,
    ExitCode,
    Parser,
    epilog,
    parse_duration,
)
from qobuz_dl.http import DEFAULT_TIMEOUT

QUALITY_HELP = "5=MP3 320, 6=FLAC lossless, 7=24-bit <=96kHz, 27=24-bit >96kHz"
QUALITY_CHOICES = (5, 6, 7, 27)
LUCKY_TYPE_CHOICES = ("artist", "album", "track", "playlist")
FORK_SOURCE = "git+https://github.com/pascalandy/qobuz-dl.git"
RUN_COMMAND = f"uvx --from {FORK_SOURCE} qobuz-dl"
RESET_COMMAND = f"{RUN_COMMAND} -r"
PROG = "qobuz-dl"
DEBUG_ENV = "QOBUZ_DL_DEBUG"
CONFIG_ENV = "QOBUZ_DL_CONFIG"
INSTALLED_NOTE = f"Installed users may replace '{RUN_COMMAND}' with 'qobuz-dl'."
DRY_RUN_NOTE = (
    "--dry-run prints candidate paths, and --json marks them 'planned' with an\n"
    "'exists' observation. It writes no folder, file, M3U, config, or history\n"
    "and reads no history, so the real run can still differ: transfers,\n"
    "verification, publication, history, and earlier items in the same run\n"
    "decide the final outcome."
)
COMMANDS = ("fun", "dl", "lucky", "help")

DOWNLOAD_EXIT_CODES = {
    ExitCode.OK: "every item finalized or skipped by your own filter",
    ExitCode.FAILURE: "an item failed for a lasting reason, or login failed",
    ExitCode.USAGE: EXIT_CODE_MEANINGS[ExitCode.USAGE]
    + ", including an invalid source",
    ExitCode.TEMPORARY: "every failure was temporary; safe to retry",
    ExitCode.INTERRUPTED: EXIT_CODE_MEANINGS[ExitCode.INTERRUPTED],
    ExitCode.TERMINATED: EXIT_CODE_MEANINGS[ExitCode.TERMINATED],
}
TOP_LEVEL_EXIT_CODES = {
    ExitCode.OK: "success",
    ExitCode.FAILURE: "runtime failure, such as a failed item, login, or config",
    ExitCode.USAGE: "usage error, including an invalid source or a bare invocation",
    ExitCode.TEMPORARY: "temporary failure; safe to retry",
    ExitCode.INTERRUPTED: EXIT_CODE_MEANINGS[ExitCode.INTERRUPTED],
    ExitCode.TERMINATED: EXIT_CODE_MEANINGS[ExitCode.TERMINATED],
}


def _package_version():
    try:
        return metadata.version("qobuz-dl")
    except metadata.PackageNotFoundError:
        return "unknown"


def positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid count {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"the count must be at least 1, not {value}")
    return value


def add_global_options(parser, *, suppress_defaults):
    """Register the options every command accepts, before or after its name.

    Subcommand parsers use ``SUPPRESS`` defaults so an option given before
    the command is not reset when the subcommand parser runs.
    """
    default = argparse.SUPPRESS if suppress_defaults else False
    options = parser.add_argument_group("global options")
    options.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=default,
        help="show progress on stderr",
    )
    options.add_argument(
        "--debug",
        action="store_true",
        default=default,
        help=f"show debug logs and stack traces on stderr; also {DEBUG_ENV}=1",
    )
    options.add_argument(
        "--no-color",
        action="store_true",
        default=default,
        help="never color output; also NO_COLOR, TERM=dumb, or a non-terminal",
    )
    options.add_argument(
        "--no-input",
        action="store_true",
        default=default,
        help="never prompt; exit 2 when input is needed",
    )
    options.add_argument(
        "--json",
        action="store_true",
        default=default,
        help="print one JSON object on stdout instead of paths; implies --no-input",
    )
    options.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        default=default,
        help=(
            "log in and look up metadata, then print where each track would go, "
            "writing nothing"
        ),
    )
    options.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        default=default if suppress_defaults else None,
        help=(f"use this config file, and the database beside it; also {CONFIG_ENV}"),
    )
    options.add_argument(
        "--timeout",
        metavar="DURATION",
        type=parse_duration,
        default=default if suppress_defaults else DEFAULT_TIMEOUT,
        help=(
            "time limit for each network request, such as 30, 45s, or 2m "
            f"(default: {DEFAULT_TIMEOUT}s)"
        ),
    )
    options.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {_package_version()}",
        help="show the version and exit",
    )


def fun_args(subparsers, default_limit):
    interactive = subparsers.add_parser(
        "fun",
        description=(
            "Interactively search Qobuz, select albums/tracks/artists/playlists, "
            "queue results, choose quality, and download the queue."
        ),
        help="interactively search Qobuz and queue downloads",
        epilog=epilog(
            (f"{RUN_COMMAND} fun", f"{RUN_COMMAND} fun --limit 10"),
            DOWNLOAD_EXIT_CODES,
            notes=(
                INSTALLED_NOTE,
                "Interactive selection accepts comma-separated numbers and ranges, "
                "for example: 1,3-5.",
                "Prompts and menus use stderr; finalized paths go to stdout.",
                "fun needs a terminal: with --no-input or piped stdin it exits 2.",
            ),
        ),
    )
    interactive.add_argument(
        "-l",
        "--limit",
        metavar="COUNT",
        type=positive_int,
        default=default_limit,
        help="maximum search results to show per query (default: 20)",
    )
    return interactive


def lucky_args(subparsers):
    lucky = subparsers.add_parser(
        "lucky",
        description=(
            "Search Qobuz and download the first N results for the selected "
            "type. Useful for scripted best-match downloads."
        ),
        help="search Qobuz and download the first matching results",
        epilog=epilog(
            (
                f'{RUN_COMMAND} lucky "playboi carti die lit"',
                f'{RUN_COMMAND} lucky --type track --limit 3 "artist song"',
                f'{RUN_COMMAND} lucky --type playlist --limit 1 "jazz classics"',
            ),
            DOWNLOAD_EXIT_CODES,
            notes=(
                INSTALLED_NOTE,
                "A query with no results exits 1; a query under 3 characters exits 2.",
                "-n now means --dry-run; use -l/--limit for the result count.",
                "",
                DRY_RUN_NOTE,
            ),
        ),
    )
    lucky.add_argument(
        "-t",
        "--type",
        metavar="TYPE",
        choices=LUCKY_TYPE_CHOICES,
        default="album",
        help="result type to search: artist, album, track, playlist (default: album)",
    )
    lucky.add_argument(
        "-l",
        "--limit",
        metavar="COUNT",
        type=positive_int,
        default=1,
        help="number of search results to download (default: 1)",
    )
    lucky.add_argument(
        "--number",
        dest="limit",
        type=positive_int,
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    lucky.add_argument("QUERY", nargs="+", help="search query words")
    return lucky


def dl_args(subparsers):
    download = subparsers.add_parser(
        "dl",
        description=(
            "Download Qobuz album, track, artist, label, or playlist URLs; "
            "Last.fm playlist URLs; or URLs listed in a local text file."
        ),
        help="download Qobuz/Last.fm URLs or URLs from a text file",
        epilog=epilog(
            (
                f"{RUN_COMMAND} dl https://play.qobuz.com/album/qxjbxh1dc3xyb",
                f"{RUN_COMMAND} dl urls.txt --no-cover",
                f"{RUN_COMMAND} dl https://www.last.fm/user/example/playlists/123 "
                "--quality 6",
            ),
            DOWNLOAD_EXIT_CODES,
            notes=(
                "Accepted SOURCE values:",
                "  - https Qobuz album/track/artist/label/playlist URLs on "
                "play, open, or www.qobuz.com",
                "  - https Last.fm playlist URLs",
                "  - local text files containing one URL per line; lines starting "
                "with # are ignored",
                "Every source is checked before login; an invalid one exits 2 and "
                "names its file and line.",
                "Each finalized audio path is printed on stdout.",
                "",
                DRY_RUN_NOTE,
                "",
                INSTALLED_NOTE,
            ),
        ),
    )
    download.add_argument(
        "SOURCE",
        metavar="SOURCE",
        nargs="+",
        help="one or more URLs, or a local text file of URLs",
    )
    return download


def help_args(subparsers):
    help_command = subparsers.add_parser(
        "help",
        description="Show help for qobuz-dl or one of its commands.",
        help="show help for a command",
        epilog=epilog(
            (f"{RUN_COMMAND} help", f"{RUN_COMMAND} help dl"),
            (ExitCode.OK, ExitCode.USAGE),
            notes=("'help COMMAND' prints the same text as 'COMMAND --help'.",),
        ),
    )
    help_command.add_argument(
        "topic",
        metavar="COMMAND",
        nargs="?",
        choices=COMMANDS,
        help="command to describe: fun, dl, lucky, or help",
    )
    return help_command


def add_common_arg(custom_parser, default_folder, default_quality):
    custom_parser.add_argument(
        "-d",
        "--directory",
        metavar="PATH",
        default=default_folder,
        help=f'download directory (default: "{default_folder}")',
    )
    custom_parser.add_argument(
        "-q",
        "--quality",
        metavar="QUALITY",
        type=int,
        choices=QUALITY_CHOICES,
        default=default_quality,
        help=f"audio quality: {QUALITY_HELP} (default: {default_quality})",
    )
    # Each switch has a --no- form and defaults to None, which keeps the
    # saved config value; either form overrides the config for this run.
    custom_parser.add_argument(
        "--albums-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="for artist/label downloads, skip singles, EPs, and Various Artists releases",
    )
    custom_parser.add_argument(
        "--m3u",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="create .m3u playlist files when downloading playlists (default: on)",
    )
    custom_parser.add_argument(
        "--fallback",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "fall back to a lower quality when the requested one is unavailable; "
            "--no-fallback skips those tracks (default: on)"
        ),
    )
    custom_parser.add_argument(
        "-e",
        "--embed-art",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="embed cover art into audio files",
    )
    custom_parser.add_argument(
        "--og-cover",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="download cover art at original quality when available (larger file)",
    )
    custom_parser.add_argument(
        "--cover",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="download cover.jpg (default: on)",
    )
    custom_parser.add_argument(
        "--db",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "use the local download database; --no-db disables duplicate "
            "tracking for this run and neither reads nor updates it (default: on)"
        ),
    )
    custom_parser.add_argument(
        "--folder-format",
        metavar="PATTERN",
        help=(
            "folder naming pattern; keys include artist, albumartist, album, year, "
            "sampling_rate, bit_depth, tracktitle, version"
        ),
    )
    custom_parser.add_argument(
        "--track-format",
        metavar="PATTERN",
        help=(
            "track naming pattern; keys include artist, albumartist, tracknumber, "
            "tracktitle, sampling_rate, bit_depth, version"
        ),
    )
    custom_parser.add_argument(
        "-s",
        "--smart-discography",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "for artist discographies, filter likely spam/extras and prefer practical "
            "remaster/quality choices"
        ),
    )


def qobuz_dl_args(
    default_quality=6, default_limit=20, default_folder="Qobuz Downloads"
):
    parser = Parser(
        prog=PROG,
        description=(
            "Download and organize Qobuz music from direct URLs, text files, "
            "interactive search, or best-match search."
        ),
        epilog=epilog(
            (
                f"{RUN_COMMAND} dl https://play.qobuz.com/album/qxjbxh1dc3xyb "
                "--quality 7",
                f"{RUN_COMMAND} dl urls.txt --directory Music --no-cover",
                f"{RUN_COMMAND} fun --limit 10",
                f'{RUN_COMMAND} lucky --type track --limit 3 "artist song"',
                f"{RUN_COMMAND} --reset --email me@example.com --password-file -",
            ),
            TOP_LEVEL_EXIT_CODES,
            notes=(
                INSTALLED_NOTE,
                f"Use '{RUN_COMMAND} help <command>' for command-specific options.",
                "For first-time setup, run --reset; with --email and --password-file",
                "it needs no terminal and uses the default folder and quality.",
                f"Config lookup: --config, then {CONFIG_ENV}, then",
                "$XDG_CONFIG_HOME/qobuz-dl/config.ini, ~/.config/qobuz-dl/config.ini,",
                "or %APPDATA%\\qobuz-dl\\config.ini; the database sits beside the config.",
                "--json prints one object for dl, lucky, --show-config, --purge, and --reset.",
                "Docs: https://github.com/pascalandy/qobuz-dl",
            ),
        ),
    )
    actions = parser.add_argument_group("actions")
    actions.add_argument(
        "-r", "--reset", action="store_true", help="create or reset the config file"
    )
    actions.add_argument(
        "-p",
        "--purge",
        action="store_true",
        help=(
            "delete the downloaded-IDs database; previously tracked releases may "
            "download again"
        ),
    )
    actions.add_argument(
        "--show-config",
        action="store_true",
        help="show config path, database path, and redacted config values",
    )
    setup = parser.add_argument_group("setup without prompts (with --reset)")
    setup.add_argument("--email", metavar="EMAIL", help="Qobuz account email")
    setup.add_argument(
        "--password-file",
        metavar="PATH",
        help="file whose first line is the password, or - to read stdin",
    )
    add_global_options(parser, suppress_defaults=False)

    subparsers = parser.add_subparsers(
        title="commands",
        description=(
            f"choose one command; use {RUN_COMMAND} help <command> for details"
        ),
        dest="command",
    )

    interactive = fun_args(subparsers, default_limit)
    download = dl_args(subparsers)
    lucky = lucky_args(subparsers)
    help_command = help_args(subparsers)
    for subparser in (interactive, download, lucky):
        add_common_arg(subparser, default_folder, default_quality)
    for subparser in (interactive, download, lucky, help_command):
        add_global_options(subparser, suppress_defaults=True)

    return parser
