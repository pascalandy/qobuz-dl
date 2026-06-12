import argparse
from importlib import metadata

QUALITY_HELP = "5=MP3 320, 6=FLAC lossless, 7=24-bit <=96kHz, 27=24-bit >96kHz"
QUALITY_CHOICES = (5, 6, 7, 27)
LUCKY_TYPE_CHOICES = ("artist", "album", "track", "playlist")


def _package_version():
    try:
        return metadata.version("qobuz-dl")
    except metadata.PackageNotFoundError:
        return "unknown"


def fun_args(subparsers, default_limit):
    interactive = subparsers.add_parser(
        "fun",
        description=(
            "Interactively search Qobuz, select albums/tracks/artists/playlists, "
            "queue results, choose quality, and download the queue."
        ),
        help="interactively search Qobuz and queue downloads",
        epilog=(
            "Examples:\n"
            "  uvx qobuz-dl fun\n"
            "  uvx qobuz-dl fun --limit 10\n\n"
            "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'.\n"
            "Interactive selection accepts comma-separated numbers and ranges, "
            "for example: 1,3-5."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    interactive.add_argument(
        "-l",
        "--limit",
        metavar="COUNT",
        type=int,
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
        epilog=(
            "Examples:\n"
            '  uvx qobuz-dl lucky "playboi carti die lit"\n'
            '  uvx qobuz-dl lucky --type track --number 3 "artist song"\n'
            '  uvx qobuz-dl lucky --type playlist --number 1 "jazz classics"\n\n'
            "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "-n",
        "--number",
        metavar="COUNT",
        type=int,
        default=1,
        help="number of search results to download (default: 1)",
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
        epilog=(
            "Accepted SOURCE values:\n"
            "  - Qobuz album/track/artist/label/playlist URLs\n"
            "  - Last.fm playlist URLs\n"
            "  - local text files containing one URL per line; lines starting "
            "with # are ignored\n\n"
            "Examples:\n"
            "  uvx qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb\n"
            "  uvx qobuz-dl dl urls.txt --no-cover\n"
            "  uvx qobuz-dl dl https://www.last.fm/user/example/playlists/123 --quality 6\n\n"
            "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    download.add_argument(
        "SOURCE",
        metavar="SOURCE",
        nargs="+",
        help="one or more URLs, or a local text file of URLs",
    )
    return download


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
    custom_parser.add_argument(
        "--albums-only",
        action="store_true",
        help="for artist/label downloads, skip singles, EPs, and Various Artists releases",
    )
    custom_parser.add_argument(
        "--no-m3u",
        action="store_true",
        help="do not create .m3u playlist files when downloading playlists",
    )
    custom_parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="disable quality fallback; skip releases unavailable at the requested quality",
    )
    custom_parser.add_argument(
        "-e",
        "--embed-art",
        action="store_true",
        help="embed cover art into audio files",
    )
    custom_parser.add_argument(
        "--og-cover",
        action="store_true",
        help="download cover art at original quality when available (larger file)",
    )
    custom_parser.add_argument(
        "--no-cover", action="store_true", help="do not download cover.jpg"
    )
    custom_parser.add_argument(
        "--no-db",
        action="store_true",
        help="disable duplicate tracking for this run; do not read or update the local database",
    )
    custom_parser.add_argument(
        "-ff",
        "--folder-format",
        metavar="PATTERN",
        help=(
            "folder naming pattern; keys include artist, albumartist, album, year, "
            "sampling_rate, bit_depth, tracktitle, version"
        ),
    )
    custom_parser.add_argument(
        "-tf",
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
        action="store_true",
        help=(
            "for artist discographies, filter likely spam/extras and prefer practical "
            "remaster/quality choices"
        ),
    )


def qobuz_dl_args(
    default_quality=6, default_limit=20, default_folder="Qobuz Downloads"
):
    parser = argparse.ArgumentParser(
        prog="qobuz-dl",
        description=(
            "Download and organize Qobuz music from direct URLs, text files, "
            "interactive search, or best-match search."
        ),
        epilog=(
            "Examples:\n"
            "  uvx qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb --quality 7\n"
            "  uvx qobuz-dl dl urls.txt --directory Music --no-cover\n"
            "  uvx qobuz-dl fun --limit 10\n"
            '  uvx qobuz-dl lucky --type track --number 3 "artist song"\n\n'
            "Installed users may replace 'uvx qobuz-dl' with 'qobuz-dl'.\n"
            "Use 'uvx qobuz-dl <command> --help' for command-specific options.\n"
            "Docs: https://github.com/pascalandy/qobuz-dl"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
        help="show version and exit",
    )
    parser.add_argument(
        "-r", "--reset", action="store_true", help="create or reset the config file"
    )
    parser.add_argument(
        "-p",
        "--purge",
        action="store_true",
        help=(
            "delete the downloaded-IDs database; previously tracked releases may "
            "download again"
        ),
    )
    parser.add_argument(
        "-sc",
        "--show-config",
        action="store_true",
        help="show config path, database path, and redacted config values",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        description="choose one command; use uvx qobuz-dl <command> --help for details",
        dest="command",
    )

    interactive = fun_args(subparsers, default_limit)
    download = dl_args(subparsers)
    lucky = lucky_args(subparsers)
    for subparser in (interactive, download, lucky):
        add_common_arg(subparser, default_folder, default_quality)

    return parser
