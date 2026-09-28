import configparser
import getpass
import hashlib
import logging
import os
import sys
import tempfile
import traceback
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass, field
from io import StringIO

from qobuz_dl import envelope, http
from qobuz_dl.bundle import Bundle
from qobuz_dl.color import GREEN, RED, YELLOW
from qobuz_dl.commands import (
    DEBUG_ENV,
    PROG,
    QUALITY_CHOICES,
    RESET_COMMAND,
    qobuz_dl_args,
)
from qobuz_dl.console import (
    DIAGNOSTIC_FLAGS,
    HELP_FLAGS,
    ExitCode,
    color_enabled,
    configure_prompts,
    env_flag,
    format_command,
    interruption_exit_code,
    prompt,
    redact,
    render,
    scan_options,
    set_usage_error_hook,
    sigterm_raises,
    stderr_logging,
    subcommand_parsers,
    without_flags,
)
from qobuz_dl.core import (
    QobuzDL,
    RunProblem,
    RunResult,
    SourceError,
    expand_sources,
    parse_source_url,
)
from qobuz_dl.downloader import DEFAULT_FOLDER, DEFAULT_TRACK, validate_cover_options
from qobuz_dl.exceptions import (
    ApiRateLimitError,
    AuthenticationError,
    BundleError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
)

logger = logging.getLogger(__name__)
PACKAGE_LOGGER = "qobuz_dl"

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


class _ConfigPathError(Exception):
    pass


def _resolve_config_paths() -> tuple[str, str]:
    if os.name == "nt":
        config_root = os.environ.get("APPDATA")
        if not config_root:
            raise _ConfigPathError
    else:
        config_root = os.path.join(os.path.expanduser("~"), ".config")

    config_path = os.path.join(config_root, "qobuz-dl")
    return (
        os.path.join(config_path, "config.ini"),
        os.path.join(config_path, "qobuz_dl.db"),
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
            encoding="utf-8",
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


class _Failure(Exception):
    """Ends the run with ``qobuz-dl: message``; a temporary one suggests a retry.

    ``problem`` is the machine-readable code that ``--json`` reports.
    """

    def __init__(self, message, *, problem, code=ExitCode.FAILURE):
        super().__init__(message)
        self.problem = problem
        self.code = code


class _MissingConfig(Exception):
    pass


def _ensure_config_exists(config_file, *, interactive=True):
    _secure_config_path(config_file)
    if not os.path.isfile(config_file):
        if not interactive:
            raise _MissingConfig
        _reset_config(config_file)


def _read_config(config_file):
    config = configparser.ConfigParser()
    try:
        with open(config_file, encoding="utf-8") as stream:
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


def _redacted_config(config_file):
    try:
        config = _read_config(config_file)
        for section in [config.default_section, *config.sections()]:
            values = config[section]
            for key in SENSITIVE_CONFIG_KEYS:
                if key in values:
                    values[key] = "<redacted>"
        return config
    except _ConfigValidationError:
        raise
    except (OSError, ValueError, TypeError, configparser.Error):
        raise _ConfigValidationError(
            "The configuration file could not be displayed safely."
        ) from None


def _redacted_config_text(config_file):
    config = _redacted_config(config_file)
    try:
        buffer = StringIO()
        config.write(buffer)
        return buffer.getvalue()
    except (ValueError, TypeError, configparser.Error):
        raise _ConfigValidationError(
            "The configuration file could not be displayed safely."
        ) from None


def _redacted_config_values(config_file):
    config = _redacted_config(config_file)
    try:
        values = dict(config[config.default_section])
        for section in config.sections():
            values[section] = {
                key: value
                for key, value in config[section].items()
                if key not in config.defaults()
            }
        return values
    except (ValueError, TypeError, configparser.Error):
        raise _ConfigValidationError(
            "The configuration file could not be displayed safely."
        ) from None


def _reset_config(config_file):
    _secure_config_path(config_file)
    logger.info(f"{YELLOW}Creating config file: {config_file}")
    config = configparser.ConfigParser()
    config["DEFAULT"]["email"] = prompt("Enter your email:\n- ")
    password = getpass.getpass("Enter your password (input is hidden): ")
    config["DEFAULT"]["password"] = hashlib.md5(password.encode("utf-8")).hexdigest()
    config["DEFAULT"]["default_folder"] = (
        prompt("Folder for downloads (leave empty for default 'Qobuz Downloads')\n- ")
        or "Qobuz Downloads"
    )
    config["DEFAULT"]["default_quality"] = (
        prompt(
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
    logger.info(f"{YELLOW}Getting tokens. Please wait...")
    bundle = Bundle()
    config["DEFAULT"]["app_id"] = str(bundle.get_app_id())
    config["DEFAULT"]["secrets"] = ",".join(bundle.get_secrets().values())
    config["DEFAULT"]["folder_format"] = DEFAULT_FOLDER
    config["DEFAULT"]["track_format"] = DEFAULT_TRACK
    config["DEFAULT"]["smart_discography"] = "false"
    _write_config(config_file, config)
    logger.info(
        f"{GREEN}Config file updated. Edit more options in {config_file}"
        "\nso you don't have to call custom flags every time you run "
        "a qobuz-dl command."
    )


def _choose(cli_value, config_value):
    """A ``--flag``/``--no-flag`` value wins; ``None`` keeps the config value."""
    return config_value if cli_value is None else cli_value


def _quality_fallback_enabled(cli_fallback, config_no_fallback):
    return _choose(cli_fallback, not config_no_fallback)


MIN_QUERY_LENGTH = 3


@dataclass
class _Session:
    """What one invocation asked for, and what it produced so far."""

    argv: list
    json: bool = False
    dry_run: bool = False
    operation: str | None = None
    run: RunResult | None = None
    data: dict | None = None

    # The argument list without options that only change diagnostics, so a
    # printed or JSON hint is the same at every verbosity.
    portable_argv: list = field(default_factory=list)

    @property
    def retry_command(self):
        return format_command((PROG, *self.portable_argv))

    def command_with(self, option):
        return format_command((PROG, option, *self.portable_argv))


def _print_path(path):
    """Print one finalized path; a stdout that cannot encode it gets escapes."""
    line = f"{path}\n"
    try:
        sys.stdout.write(line)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        sys.stdout.write(line.encode(encoding, "backslashreplace").decode(encoding))
        logger.warning(
            "stdout cannot encode a finalized path, so it was printed with "
            "escapes; set PYTHONUTF8=1 to print it exactly"
        )
    sys.stdout.flush()


def _download_search_results(qobuz, urls, query, *, preview=False):
    if not urls:
        qobuz.run_result.add_problem(
            RunProblem("no_match", f'no results for "{query}"', query)
        )
        return
    sources = []
    for url in urls:
        source = parse_source_url(url)
        if source is None:
            qobuz.run_result.add_problem(
                RunProblem(
                    "unsupported_result", f"unsupported result URL: {url}", query
                )
            )
        else:
            sources.append(source)
    if preview:
        qobuz.preview_sources(sources)
    else:
        qobuz.download_sources(sources)


def _handle_commands(qobuz, arguments, sources=(), run=None):
    """Run the command and return the exit code its outcomes call for."""
    run = RunResult(on_path=_print_path) if run is None else run
    qobuz.run_result = run
    query = " ".join(getattr(arguments, "QUERY", None) or ())
    preview = getattr(arguments, "dry_run", False)
    try:
        if arguments.command == "dl":
            if preview:
                qobuz.preview_sources(sources)
            else:
                qobuz.download_sources(sources)
        elif arguments.command == "lucky":
            qobuz.lucky_type = arguments.type
            qobuz.lucky_limit = arguments.limit
            _download_search_results(
                qobuz, qobuz.lucky_mode(query, download=False), query, preview=preview
            )
        else:
            qobuz.interactive_limit = arguments.limit
            urls = qobuz.interactive(download=False)
            if urls:
                _download_search_results(qobuz, urls, "interactive selection")

    except ApiRateLimitError as error:
        logger.error(f"{RED}{error}")
        run.add_problem(RunProblem("rate_limited", str(error), query, retryable=True))
    except http.HttpError as error:
        logger.error(f"{RED}Request failed: {error}")
        run.add_problem(
            RunProblem(
                "request_error", str(error), query, retryable=http.is_retryable(error)
            )
        )
    return run.exit_code()


def _validate_operands(parser, arguments):
    """Reject invalid sources and queries before config, login, or writes."""
    if arguments.command == "dl":
        try:
            return expand_sources(arguments.SOURCE)
        except SourceError as error:
            subcommand_parsers(parser)["dl"].error(str(error))
    if arguments.command == "lucky":
        if len(" ".join(arguments.QUERY).strip()) < MIN_QUERY_LENGTH:
            subcommand_parsers(parser)["lucky"].error(
                f"the search query needs at least {MIN_QUERY_LENGTH} characters"
            )
    return ()


def _old_count_flag(lucky, token, following):
    """Whether ``token`` uses -n with a count, alone or in a short cluster."""
    if not token.startswith("-") or token.startswith("--") or len(token) < 2:
        return False
    letters = token[1:]
    for position, letter in enumerate(letters):
        action = lucky._option_string_actions.get(f"-{letter}")
        if action is None or action.nargs != 0:
            return False
        if letter == "n":
            rest = letters[position + 1 :]
            return rest.isdigit() if rest else following.isdigit()
    return False


def _reject_old_number_flag(parser, argv):
    """``lucky -n 3`` once meant three results; -n is now --dry-run."""
    lucky = subcommand_parsers(parser)["lucky"]
    tokens = argv[: argv.index("--")] if "--" in argv else argv
    for index, token in enumerate(tokens):
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if _old_count_flag(lucky, token, following):
            lucky.error("-n now means --dry-run; use --limit N")


def _operation(arguments):
    if arguments.reset:
        return "reset"
    if arguments.purge:
        return "purge"
    if arguments.show_config:
        return "show-config"
    return arguments.command


def _interactive(arguments):
    stdin = sys.stdin
    wants_input = not (arguments.no_input or arguments.json)
    return wants_input and bool(stdin and stdin.isatty())


def _check_usage(parser, arguments, interactive):
    """Reject every usage error before config, login, or writes."""
    actions = [
        flag
        for flag, chosen in (
            ("--reset", arguments.reset),
            ("--purge", arguments.purge),
            ("--show-config", arguments.show_config),
            (f"'{arguments.command}'", arguments.command is not None),
        )
        if chosen
    ]
    if len(actions) > 1:
        parser.error(f"{actions[0]} cannot be combined with {actions[1]}")
    if not actions:
        parser.error(
            "choose a command, such as 'qobuz-dl dl URL'; "
            "for first-time setup, run 'qobuz-dl --reset'"
        )
    if arguments.dry_run and (arguments.reset or arguments.command == "fun"):
        parser.error(f"--dry-run cannot be combined with {actions[0]}")
    if arguments.reset and not interactive:
        parser.error("--reset prompts for your account; run it in a terminal")
    if arguments.command == "fun" and not interactive:
        subcommand_parsers(parser)["fun"].error(
            "fun needs an interactive terminal; use 'qobuz-dl lucky QUERY' "
            "or 'qobuz-dl dl URL' instead"
        )
    if arguments.command is None:
        return ()
    try:
        validate_cover_options(arguments.embed_art is True, arguments.cover is False)
    except ValueError as error:
        parser.error(str(error))
    return _validate_operands(parser, arguments)


def _login(qobuz, config_values):
    try:
        qobuz.initialize_client(
            config_values["email"],
            config_values["password"],
            config_values["app_id"],
            config_values["secrets"],
        )
    except (
        AuthenticationError,
        IneligibleError,
        InvalidAppIdError,
        InvalidAppSecretError,
    ) as error:
        raise _Failure(f"login failed: {error}", problem="login_failed") from None
    except ApiRateLimitError as error:
        raise _Failure(
            str(error), problem="rate_limited", code=ExitCode.TEMPORARY
        ) from None
    except http.HttpError as error:
        code = ExitCode.TEMPORARY if http.is_retryable(error) else ExitCode.FAILURE
        raise _Failure(
            f"login failed: {error}", problem="login_failed", code=code
        ) from None


def _purge(session, database_file):
    exists = os.path.lexists(database_file)
    if session.dry_run:
        session.data = {
            "database_path": database_file,
            "deleted": False,
            "exists": exists,
            "dry_run": True,
        }
        if not session.json:
            print(database_file)
        return ExitCode.OK
    try:
        os.remove(database_file)
    except FileNotFoundError:
        logger.info(f"{GREEN}The database is already absent.")
        session.data = {"database_path": database_file, "deleted": False}
        return ExitCode.OK
    except OSError:
        raise _Failure(
            f"Unable to delete database at {database_file}. Check its permissions.",
            problem="purge_failed",
        ) from None
    logger.info(f"{GREEN}The database was deleted.")
    session.data = {"database_path": database_file, "deleted": True}
    return ExitCode.OK


def _failure_lines(run, *, dry_run=False):
    """Describe the unsatisfied items and problems of a run, one line each."""
    unsatisfied = [
        item for item in run.items if item.classification in ("permanent", "temporary")
    ]
    lines = []
    if unsatisfied:
        counts = Counter(item.result.reason for item in unsatisfied)
        reasons = ", ".join(
            reason if count == 1 else f"{reason} ({count})"
            for reason, count in counts.items()
        )
        verb = "would not be downloaded" if dry_run else "could not be downloaded"
        lines.append(f"{len(unsatisfied)} of {len(run.items)} items {verb}: {reasons}")
    lines.extend(problem.message for problem in run.problems)
    return lines


def _report_run(color, session, code, arguments):
    """Say what failed in a run that exits 1 or 75, then what to run next."""
    if session.run is None or code not in (ExitCode.FAILURE, ExitCode.TEMPORARY):
        return
    if code == ExitCode.TEMPORARY:
        hint = f"retry: {session.retry_command}"
    elif arguments.verbose or arguments.debug:
        hint = None
    else:
        hint = f"see why: {session.command_with('--verbose')}"
    lines = [
        f"{PROG}: {line}"
        for line in _failure_lines(session.run, dry_run=session.dry_run)
    ]
    if hint:
        lines.append(hint)
    sys.stderr.write(render(redact("\n".join(lines)), color) + "\n")
    sys.stderr.flush()


def _run(parser, arguments, session):
    interactive = _interactive(arguments)
    sources = _check_usage(parser, arguments, interactive)
    try:
        config_file, database_file = _resolve_config_paths()
    except _ConfigPathError:
        raise _Failure(
            "APPDATA is not set. Set APPDATA to your Windows application-data "
            "directory and retry.",
            problem="appdata_missing",
        ) from None
    startup = _classify_startup(arguments)

    config_values = None
    try:
        if arguments.reset:
            _reset_config(config_file)
            return ExitCode.OK
        if startup.needs_config:
            if not arguments.dry_run:
                _ensure_config_exists(config_file, interactive=interactive)
            elif not os.path.isfile(config_file):
                # A dry run never creates, prompts for, or repairs config.
                raise _MissingConfig
            if startup.needs_auth or arguments.show_config:
                config_values = _load_config_values(config_file)
        if arguments.show_config and session.json:
            settings = _redacted_config_values(config_file)
        elif arguments.show_config:
            settings = _redacted_config_text(config_file)
    except _MissingConfig:
        parser.error(
            f"no config file at {config_file}; create it in a terminal with "
            "'qobuz-dl --reset'"
        )
    except _ConfigStorageError:
        raise _Failure(
            "Unable to access configuration securely. "
            "Check its directory permissions and available disk space.",
            problem="config_storage",
        ) from None
    except BundleError as error:
        raise _Failure(
            "Unable to create configuration from the Qobuz web bundle: "
            f"{error}. Configuration was not saved.",
            problem="bundle_invalid",
        ) from None
    except http.HttpError as error:
        raise _Failure(
            f"Unable to read the Qobuz web bundle: {error}. "
            "Configuration was not saved.",
            problem="bundle_unavailable",
            code=(ExitCode.TEMPORARY if http.is_retryable(error) else ExitCode.FAILURE),
        ) from None
    except _ConfigValidationError as error:
        raise _Failure(
            f"Your config file is corrupted: {error}! "
            f"Run '{RESET_COMMAND}' to fix this "
            "(or 'qobuz-dl -r' if installed).",
            problem="config_corrupt",
        ) from None

    if arguments.show_config:
        session.data = {
            "config_path": config_file,
            "database_path": database_file,
            "settings": settings,
        }
        if not session.json:
            print(f"Configuration: {config_file}\nDatabase: {database_file}\n---")
            print(settings)
        return ExitCode.OK

    if arguments.purge:
        return _purge(session, database_file)

    arguments = qobuz_dl_args(
        config_values["default_quality"],
        config_values["default_limit"],
        config_values["default_folder"],
    ).parse_args(session.argv)

    embed_art = _choose(arguments.embed_art, config_values["embed_art"])
    no_cover = not _choose(arguments.cover, not config_values["no_cover"])
    try:
        validate_cover_options(embed_art, no_cover)
    except ValueError as error:
        parser.error(str(error))

    use_database = _choose(arguments.db, not config_values["no_database"])
    qobuz = QobuzDL(
        arguments.directory,
        arguments.quality,
        embed_art,
        ignore_singles_eps=_choose(arguments.albums_only, config_values["albums_only"]),
        no_m3u_for_playlists=not _choose(arguments.m3u, not config_values["no_m3u"]),
        quality_fallback=_quality_fallback_enabled(
            arguments.fallback,
            config_values["no_fallback"],
        ),
        cover_og_quality=_choose(arguments.og_cover, config_values["og_cover"]),
        no_cover=no_cover,
        # A dry run reads no history, so it never opens the database.
        downloads_db=database_file if use_database and not arguments.dry_run else None,
        folder_format=arguments.folder_format or config_values["folder_format"],
        track_format=arguments.track_format or config_values["track_format"],
        smart_discography=_choose(
            arguments.smart_discography, config_values["smart_discography"]
        ),
    )
    _login(qobuz, config_values)
    session.run = RunResult(on_path=None if session.json else _print_path)
    return _handle_commands(qobuz, arguments, sources, session.run)


def _report(color, message, hint=None):
    lines = [f"{PROG}: {message}"]
    if hint:
        lines.append(hint)
    sys.stderr.write(render(redact("\n".join(lines)), color) + "\n")
    sys.stderr.flush()


def _write_json(session, code, problems=()):
    data = session.data
    problems = list(problems)
    if session.run is not None:
        data = envelope.run_data(session.run, dry_run=session.dry_run)
        problems = [
            *envelope.run_problems(session.run, session.retry_command),
            *problems,
        ]
    envelope.write(
        envelope.document(
            session.operation, envelope.STATUS_BY_EXIT[code], data, problems
        )
    )


def main(argv=None):
    """Run qobuz-dl and return its exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = qobuz_dl_args()
    scan = scan_options(parser, argv, HELP_FLAGS | {"--json"})
    if "--json" in scan.found:
        set_usage_error_hook(
            parser,
            lambda message, hint: envelope.write(envelope.usage_error(message, hint)),
        )
    if scan.subcommand == "lucky" and not scan.found & HELP_FLAGS:
        _reject_old_number_flag(parser, argv)
    arguments = parser.parse_args(argv)
    if arguments.command == "help":
        topic = arguments.topic
        target = subcommand_parsers(parser)[topic] if topic else parser
        target.print_help()
        return ExitCode.OK

    session = _Session(
        argv,
        json=arguments.json,
        dry_run=arguments.dry_run,
        operation=_operation(arguments),
        portable_argv=without_flags(parser, argv, DIAGNOSTIC_FLAGS),
    )
    debug = arguments.debug or env_flag(DEBUG_ENV)
    if debug:
        level = logging.DEBUG
    elif arguments.verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    color = not arguments.no_color and color_enabled(sys.stderr)
    configure_prompts(color=color)
    with stderr_logging(logging.getLogger(PACKAGE_LOGGER), level, color):
        problems = []
        try:
            with sigterm_raises():
                code = _run(parser, arguments, session)
            _report_run(color, session, code, arguments)
        except KeyboardInterrupt as interruption:
            message = "interrupted; finished files were kept"
            _report(color, message)
            code = interruption_exit_code(interruption)
            problems.append(envelope.problem("interrupted", message))
        except _Failure as failure:
            code = failure.code
            retry = session.retry_command if code == ExitCode.TEMPORARY else None
            _report(color, str(failure), f"retry: {retry}" if retry else None)
            problems.append(
                envelope.problem(
                    failure.problem,
                    str(failure),
                    retryable=retry is not None,
                    hint=retry,
                )
            )
        except EOFError:
            message = "input ended before the prompt was answered"
            _report(color, message)
            code = ExitCode.USAGE
            problems.append(envelope.problem("input_ended", message))
        except Exception as error:
            if debug:
                trace = "".join(traceback.format_exception(error))
                sys.stderr.write(render(redact(trace), color))
            rerun = session.command_with("--debug")
            _report(
                color,
                f"unexpected error: {error}",
                f"rerun with a stack trace: {rerun}",
            )
            code = ExitCode.FAILURE
            problems.append(
                envelope.problem("unexpected_error", str(error), hint=rerun)
            )
        if session.json:
            try:
                _write_json(session, code, problems)
            except OSError as error:
                _report(color, f"could not write the JSON result: {error}")
        return code


if __name__ == "__main__":
    sys.exit(main())
