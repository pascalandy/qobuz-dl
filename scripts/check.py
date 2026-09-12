from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from importlib.metadata import version
from pathlib import Path

Command = tuple[str, ...]

ROOT = Path(__file__).resolve().parents[1]
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
    def __init__(self, message: str, returncode: int = 1) -> None:
        super().__init__(message)
        self.returncode = returncode if 1 <= returncode <= 255 else 1


def run(
    command: Command,
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    expected_stdout: str | None = None,
) -> str:
    print(f"+ {subprocess.list2cmdline(command)}", flush=True)
    print(f"  cwd: {cwd}", flush=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE if expected_stdout is not None else None,
        text=True,
        check=False,
    )
    stdout = completed.stdout or ""
    if expected_stdout is not None:
        print(stdout, end="")
    if completed.returncode:
        raise CheckFailure(
            f"{command[0]} exited with status {completed.returncode}",
            completed.returncode,
        )
    if expected_stdout is not None and stdout != expected_stdout:
        raise CheckFailure(
            f"{subprocess.list2cmdline(command)} printed {stdout!r}; "
            f"expected {expected_stdout!r}"
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


def publish_artifacts(artifacts: tuple[Path, Path]) -> None:
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    for artifact in artifacts:
        target = destination / artifact.name
        if target.is_symlink():
            raise CheckFailure(f"refusing to replace artifact symlink: {target}")
        shutil.copy2(artifact, target)


def check() -> None:
    expected_version = version("qobuz-dl")
    expected_version_output = f"qobuz-dl {expected_version}\n"

    for command in SOURCE_GATES:
        run(command, cwd=ROOT)
    for command in CLI_PROBES:
        run(
            command,
            cwd=ROOT,
            expected_stdout=(
                expected_version_output if command[1:] == ("--version",) else None
            ),
        )

    uv = shutil.which("uv")
    if uv is None:
        raise CheckFailure("uv is not available on PATH")
    with tempfile.TemporaryDirectory(prefix="qobuz-dl-check-") as temporary:
        workspace = Path(temporary).resolve()
        try:
            workspace.relative_to(ROOT)
        except ValueError:
            pass
        else:
            raise CheckFailure("temporary workspace must be outside the checkout")

        artifacts = build(uv, workspace / "build")
        verify_wheel(
            uv,
            artifacts[0],
            workspace=workspace,
            expected_version=expected_version,
        )
        print(f"verified wheel sha256: {wheel_sha256(artifacts[0])}")
        publish_artifacts(artifacts)


def main() -> int:
    try:
        check()
    except KeyboardInterrupt:
        print("check interrupted", file=sys.stderr)
        return 130
    except (CheckFailure, OSError) as error:
        print(f"check failed: {error}", file=sys.stderr)
        return error.returncode if isinstance(error, CheckFailure) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
