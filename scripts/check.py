from __future__ import annotations

import hashlib
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Mapping, Sequence
from contextlib import suppress
from importlib.metadata import version
from pathlib import Path

from qobuz_dl.console import (
    ExitCode,
    Parser,
    configure_stderr_logging,
    env_flag,
    epilog,
    format_command,
    interruption_exit_code,
    sigterm_raises,
)

Command = tuple[str, ...]

ROOT = Path(__file__).resolve().parents[1]
PROG = "check.py"
DEBUG_ENV = "CHECK_DEBUG"
COMMAND = "uv run --frozen python scripts/check.py"
RERUN = f"{COMMAND} --verbose"
GROUP_STOP_GRACE_SECONDS = 5.0
STDERR_FD = 2
logger = logging.getLogger("qobuz_dl.check")
SOURCE_GATES: tuple[Command, ...] = (
    ("ruff", "format", "--check", "."),
    ("ruff", "check", "."),
    ("pytest",),
)
CLI_PROBES: tuple[Command, ...] = (
    ("qobuz-dl", "--help"),
    ("qobuz-dl", "--version"),
    ("qobuz-dl", "dl", "--help"),
    ("qobuz-dl", "fun", "--help"),
    ("qobuz-dl", "lucky", "--help"),
    ("qobuz-dl", "help", "dl"),
    ("qdl", "--help"),
    ("qdl", "--version"),
)
IMPORT_PROBE = """\
import sys
from importlib.metadata import version
from pathlib import Path

import qobuz_dl

expected_version = sys.argv[1]
environment = Path(sys.argv[2]).resolve()
module_path = Path(qobuz_dl.__file__).resolve()
try:
    module_path.relative_to(environment)
except ValueError:
    raise SystemExit(f"qobuz_dl imported outside the isolated environment: {module_path}")
installed_version = version("qobuz-dl")
if installed_version != expected_version:
    raise SystemExit(
        f"installed version {installed_version!r} does not match {expected_version!r}"
    )
print(f"isolated import: {module_path}")
"""


class CheckFailure(Exception):
    def __init__(self, message: str, *, output: str = "", rerun: str = RERUN) -> None:
        super().__init__(message)
        self.output = output
        self.rerun = rerun


def _process_group_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _group_alive(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_process_group(process: subprocess.Popen) -> None:
    """Stop a gate and every process it started, such as tools run by pytest."""
    if os.name == "nt":
        with suppress(OSError):
            process.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            process.wait(GROUP_STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        subprocess.run(
            ("taskkill", "/F", "/T", "/PID", str(process.pid)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        with suppress(subprocess.TimeoutExpired):
            process.wait(GROUP_STOP_GRACE_SECONDS)
        return

    group = process.pid
    with suppress(ProcessLookupError):
        os.killpg(group, signal.SIGTERM)
    deadline = time.monotonic() + GROUP_STOP_GRACE_SECONDS
    with suppress(subprocess.TimeoutExpired):
        process.wait(GROUP_STOP_GRACE_SECONDS)
    while _group_alive(group) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _group_alive(group):
        with suppress(ProcessLookupError):
            os.killpg(group, signal.SIGKILL)
    with suppress(subprocess.TimeoutExpired):
        process.wait(GROUP_STOP_GRACE_SECONDS)


def run_gate(
    command: Command, *, cwd: Path, env: Mapping[str, str] | None, stdout, stderr
) -> subprocess.CompletedProcess:
    """Run one gate in its own process group and stop the group on interrupt."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=stdout,
        stderr=stderr,
        text=True,
        **_process_group_options(),
    )
    try:
        output, errors = process.communicate()
    except BaseException:
        stop_process_group(process)
        raise
    return subprocess.CompletedProcess(command, process.returncode, output, errors)


def run(
    command: Command,
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    expected_stdout: str | None = None,
    rerun: str = RERUN,
) -> str:
    command_line = format_command(command)
    logger.info("+ %s", command_line)
    logger.info("  cwd: %s", cwd)
    verbose = logger.isEnabledFor(logging.INFO)
    if verbose and expected_stdout is None:
        streams = {"stdout": STDERR_FD, "stderr": None}
    elif verbose:
        streams = {"stdout": subprocess.PIPE, "stderr": None}
    elif expected_stdout is None:
        streams = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}
    else:
        streams = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if verbose:
        sys.stderr.flush()
    started = time.monotonic()
    completed = run_gate(command, cwd=cwd, env=env, **streams)
    logger.debug("  finished in %.1fs", time.monotonic() - started)
    stdout = completed.stdout or ""
    if verbose and expected_stdout is not None:
        sys.stderr.write(stdout)
    captured = "" if verbose else stdout + (completed.stderr or "")
    if completed.returncode:
        raise CheckFailure(
            f"`{command_line}` exited with status {completed.returncode}",
            output=captured,
            rerun=rerun,
        )
    if expected_stdout is not None and stdout != expected_stdout:
        raise CheckFailure(
            f"`{command_line}` printed {stdout!r}; expected {expected_stdout!r}",
            output=captured,
            rerun=rerun,
        )
    return stdout


def build(uv: str, output: Path) -> tuple[Path, Path]:
    run(
        (uv, "build", "--out-dir", str(output), "--no-create-gitignore"),
        cwd=ROOT,
    )
    wheels = tuple(output.glob("*.whl"))
    source_distributions = tuple(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(source_distributions) != 1:
        raise CheckFailure(
            "build must produce exactly one wheel and one source distribution; "
            f"found {len(wheels)} wheel(s) and "
            f"{len(source_distributions)} source distribution(s)"
        )
    return wheels[0].resolve(), source_distributions[0].resolve()


def environment_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def environment_command(environment: Path, name: str) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / f"{name}.exe"
    return environment / "bin" / name


def verify_wheel(
    uv: str,
    wheel: Path,
    *,
    workspace: Path,
    expected_version: str,
) -> None:
    environment = workspace / "venv"
    probe_directory = workspace / "probe"
    probe_directory.mkdir()
    run(
        (uv, "venv", "--python", sys.executable, str(environment)),
        cwd=workspace,
    )
    python = environment_python(environment)
    run(
        (uv, "pip", "install", "--python", str(python), str(wheel)),
        cwd=workspace,
    )

    clean_env = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        clean_env.pop(name, None)
    clean_env["PYTHONNOUSERSITE"] = "1"

    run(
        (
            str(python),
            "-I",
            "-c",
            IMPORT_PROBE,
            expected_version,
            str(environment),
        ),
        cwd=probe_directory,
        env=clean_env,
    )
    for probe in CLI_PROBES:
        executable = environment_command(environment, probe[0])
        command = (str(executable), *probe[1:])
        expected_stdout = (
            f"qobuz-dl {expected_version}\n" if probe[1:] == ("--version",) else None
        )
        run(
            command,
            cwd=probe_directory,
            env=clean_env,
            expected_stdout=expected_stdout,
        )


def wheel_sha256(wheel: Path) -> str:
    digest = hashlib.sha256()
    with wheel.open("rb") as wheel_file:
        for chunk in iter(lambda: wheel_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_artifacts(artifacts: tuple[Path, Path]) -> Path:
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    published = []
    for artifact in artifacts:
        target = destination / artifact.name
        if target.is_symlink():
            raise CheckFailure(
                f"refusing to replace artifact symlink: {target}",
                rerun=f"{format_command(('rm', str(target)))} && {RERUN}",
            )
        shutil.copy2(artifact, target)
        published.append(target)
    return published[0]


def gate_rerun(command: Command) -> str:
    return f"uv run --frozen {format_command(command)}"


def check() -> tuple[Path, str]:
    expected_version = version("qobuz-dl")
    expected_version_output = f"qobuz-dl {expected_version}\n"

    for command in SOURCE_GATES:
        run(command, cwd=ROOT, rerun=gate_rerun(command))
    for command in CLI_PROBES:
        run(
            command,
            cwd=ROOT,
            expected_stdout=(
                expected_version_output if command[1:] == ("--version",) else None
            ),
            rerun=gate_rerun(command),
        )

    uv = shutil.which("uv")
    if uv is None:
        raise CheckFailure(
            "uv is not available on PATH",
            rerun="install uv (https://docs.astral.sh/uv/), then run: just ci",
        )
    with tempfile.TemporaryDirectory(prefix="qobuz-dl-check-") as temporary:
        workspace = Path(temporary).resolve()
        try:
            workspace.relative_to(ROOT)
        except ValueError:
            pass
        else:
            raise CheckFailure(
                "temporary workspace must be outside the checkout",
                rerun=f"TMPDIR=/tmp {RERUN}",
            )

        artifacts = build(uv, workspace / "build")
        verify_wheel(
            uv,
            artifacts[0],
            workspace=workspace,
            expected_version=expected_version,
        )
        digest = wheel_sha256(artifacts[0])
        logger.info("verified wheel sha256: %s", digest)
        return publish_artifacts(artifacts), digest


def build_parser() -> Parser:
    parser = Parser(
        prog=PROG,
        command=COMMAND,
        description=(
            "Run the repository quality gates: formatting, lint, tests, CLI "
            "probes, and an isolated wheel build and install. On success, print "
            "the verified wheel's SHA-256 and its dist/ path, and nothing else."
        ),
        epilog=epilog(
            (
                "just ci",
                COMMAND,
                f"{COMMAND} --verbose",
                f"{COMMAND} | sha256sum --check",
            ),
            {
                ExitCode.OK: "every gate passed",
                ExitCode.FAILURE: "a gate failed; its output and rerun command "
                "are on stderr",
                ExitCode.USAGE: "usage error",
                ExitCode.INTERRUPTED: "interrupted (SIGINT)",
                ExitCode.TERMINATED: "terminated (SIGTERM)",
            },
            notes=(
                "Without --verbose, only a failing gate's captured output is",
                "printed to stderr, followed by the command that reruns it.",
                "Each gate runs in its own process group; an interrupt stops the",
                "whole group.",
            ),
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="stream each gate's command and output to stderr",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "like --verbose, plus gate timings and stack traces for unexpected "
            f"errors; also enabled by {DEBUG_ENV}=1"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    debug = arguments.debug or env_flag(DEBUG_ENV)
    if debug:
        level = logging.DEBUG
    elif arguments.verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    configure_stderr_logging(logger, level)

    try:
        with sigterm_raises():
            wheel, digest = check()
    except KeyboardInterrupt as interruption:
        print(f"{PROG}: interrupted", file=sys.stderr)
        return interruption_exit_code(interruption)
    except CheckFailure as failure:
        if failure.output:
            sys.stderr.write(failure.output)
            if not failure.output.endswith("\n"):
                sys.stderr.write("\n")
        print(f"{PROG}: {failure}\nrerun: {failure.rerun}", file=sys.stderr)
        return ExitCode.FAILURE
    except Exception as error:
        if debug:
            traceback.print_exc()
        print(
            f"{PROG}: unexpected error: {error}\n"
            f"rerun with a stack trace: {COMMAND} --debug",
            file=sys.stderr,
        )
        return ExitCode.FAILURE
    print(f"{digest}  {wheel.relative_to(ROOT).as_posix()}")
    return ExitCode.OK


if __name__ == "__main__":
    raise SystemExit(main())
