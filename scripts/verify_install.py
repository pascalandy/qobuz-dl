from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

FORK_REPOSITORY = "https://github.com/pascalandy/qobuz-dl.git"
FLOATING_SOURCE = f"git+{FORK_REPOSITORY}"
EXPECTED_VERSION = "1.0.0"
EXPECTED_ENTRY_POINTS = {
    "qdl": "qobuz_dl:main",
    "qobuz-dl": "qobuz_dl:main",
}
SUBPROCESS_TIMEOUT_SECONDS = 300
FULL_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
REQUIREMENT = re.compile(r"(?P<name>[A-Za-z0-9_.-]+)(?P<spec>[^;]*)(?P<marker>;.*)?\Z")
PROBE = r"""
import json
import platform
import sys
from importlib import metadata
from pathlib import Path

distribution = metadata.distribution("qobuz-dl")
direct_url_text = distribution.read_text("direct_url.json")
if direct_url_text is None:
    raise SystemExit("qobuz-dl has no direct_url.json provenance record")
entry_points = {
    entry_point.name: entry_point.value
    for entry_point in distribution.entry_points
    if entry_point.group == "console_scripts"
}
print(json.dumps({
    "name": distribution.metadata["Name"],
    "version": distribution.version,
    "entry_points": entry_points,
    "requirements": distribution.requires or [],
    "location": str(Path(distribution.locate_file("")).resolve()),
    "python_prefix": str(Path(sys.prefix).resolve()),
    "python_version": platform.python_version(),
    "direct_url": json.loads(direct_url_text),
}, sort_keys=True, separators=(",", ":")))
"""


class VerificationFailure(Exception):
    pass


def source_for_revision(revision: str | None) -> str:
    if revision is None:
        return FLOATING_SOURCE
    if FULL_SHA.fullmatch(revision) is None:
        raise VerificationFailure(
            "revision must be a full 40-character hexadecimal SHA"
        )
    return f"{FLOATING_SOURCE}@{revision.lower()}"


def _requirement_parts(requirement: str) -> tuple[str, frozenset[str]]:
    match = REQUIREMENT.fullmatch(requirement.replace(" ", ""))
    if match is None or match.group("marker"):
        raise VerificationFailure(f"unexpected requirement: {requirement!r}")
    name = match.group("name").lower().replace("_", "-").replace(".", "-")
    specifiers = frozenset(filter(None, match.group("spec").split(",")))
    return name, specifiers


def _path_belongs_to(path_value: object, root: Path, label: str) -> str:
    if not isinstance(path_value, (str, os.PathLike)):
        raise VerificationFailure(f"{label} location is not path-like")
    path = Path(path_value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise VerificationFailure(
            f"{label} location is outside the temporary root: {path}"
        ) from None
    return str(path)


def _lexical_path_belongs_to(path_value: object, root: Path, label: str) -> str:
    if not isinstance(path_value, (str, os.PathLike)):
        raise VerificationFailure(f"{label} location is not path-like")
    path = Path(os.path.abspath(path_value))
    lexical_root = Path(os.path.abspath(root))
    try:
        path.relative_to(lexical_root)
    except ValueError:
        raise VerificationFailure(
            f"{label} location is outside the temporary root: {path}"
        ) from None
    return str(path)


def validate_record(record: Mapping[str, Any], root: Path, label: str) -> str:
    if record.get("name") != "qobuz-dl":
        raise VerificationFailure(f"{label} distribution name is not qobuz-dl")
    if record.get("version") != EXPECTED_VERSION:
        raise VerificationFailure(
            f"{label} version is {record.get('version')!r}, expected {EXPECTED_VERSION!r}"
        )
    if record.get("entry_points") != EXPECTED_ENTRY_POINTS:
        raise VerificationFailure(
            f"{label} console scripts do not match the expected pair"
        )

    requirements = record.get("requirements")
    if not isinstance(requirements, list) or len(requirements) != 1:
        raise VerificationFailure(f"{label} must have exactly one runtime requirement")
    if _requirement_parts(requirements[0]) != (
        "mutagen",
        frozenset({">=1.47", "<2"}),
    ):
        raise VerificationFailure(
            f"{label} requirement must be exactly mutagen >=1.47,<2"
        )

    direct_url = record.get("direct_url")
    if not isinstance(direct_url, dict) or direct_url.get("url") != FORK_REPOSITORY:
        raise VerificationFailure(
            f"{label} provenance does not name the exact fork URL"
        )
    vcs_info = direct_url.get("vcs_info")
    if not isinstance(vcs_info, dict) or vcs_info.get("vcs") != "git":
        raise VerificationFailure(f"{label} provenance is not Git VCS provenance")
    commit = vcs_info.get("commit_id")
    if not isinstance(commit, str) or FULL_SHA.fullmatch(commit) is None:
        raise VerificationFailure(f"{label} provenance has no full resolved commit SHA")

    _path_belongs_to(record.get("location"), root, label)
    _path_belongs_to(record.get("python_prefix"), root, f"{label} Python prefix")
    python_version = record.get("python_version")
    if not isinstance(python_version, str) or not python_version:
        raise VerificationFailure(f"{label} has no probed Python version")
    return commit.lower()


def compare_records(one_shot: Mapping[str, Any], persistent: Mapping[str, Any]) -> None:
    comparable_fields = (
        "name",
        "version",
        "entry_points",
        "requirements",
        "python_version",
    )
    disagreements = [
        field
        for field in comparable_fields
        if one_shot.get(field) != persistent.get(field)
    ]
    one_shot_direct_url = one_shot.get("direct_url", {})
    persistent_direct_url = persistent.get("direct_url", {})
    one_shot_vcs = one_shot_direct_url.get("vcs_info", {})
    persistent_vcs = persistent_direct_url.get("vcs_info", {})
    if (
        one_shot_direct_url.get("url"),
        one_shot_vcs.get("vcs"),
        one_shot_vcs.get("commit_id"),
    ) != (
        persistent_direct_url.get("url"),
        persistent_vcs.get("vcs"),
        persistent_vcs.get("commit_id"),
    ):
        disagreements.append("provenance")
    if disagreements:
        raise VerificationFailure(
            "one-shot and persistent records disagree on: " + ", ".join(disagreements)
        )


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> str:
    print(f"+ {shlex.join(command)}", file=sys.stderr, flush=True)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise VerificationFailure(
            f"{command[0]} timed out after {SUBPROCESS_TIMEOUT_SECONDS} seconds"
        ) from None
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationFailure(
            f"{command[0]} exited with status {completed.returncode}: {detail}"
        )
    return completed.stdout


def _probe_with_uvx(
    uvx: str,
    source: str,
    *,
    workspace: Path,
    env: Mapping[str, str],
    refresh: bool = False,
) -> dict[str, Any]:
    options = ["--no-config", "--isolated", "--no-progress"]
    if refresh:
        options.append("--refresh")
    output = _run(
        (uvx, *options, "--from", source, "python", "-I", "-c", PROBE),
        cwd=workspace,
        env=env,
    )
    try:
        record = json.loads(output)
    except json.JSONDecodeError as error:
        raise VerificationFailure(
            f"one-shot metadata probe returned invalid JSON: {error}"
        ) from None
    if not isinstance(record, dict):
        raise VerificationFailure("one-shot metadata probe did not return an object")
    return record


def _probe_with_python(
    python: Path, *, workspace: Path, env: Mapping[str, str]
) -> dict[str, Any]:
    output = _run(
        (str(python), "-I", "-c", PROBE),
        cwd=workspace,
        env=env,
    )
    try:
        record = json.loads(output)
    except json.JSONDecodeError as error:
        raise VerificationFailure(
            f"persistent metadata probe returned invalid JSON: {error}"
        ) from None
    if not isinstance(record, dict):
        raise VerificationFailure("persistent metadata probe did not return an object")
    return record


def _smoke(
    executable: Sequence[str],
    *,
    workspace: Path,
    env: Mapping[str, str],
) -> dict[str, str]:
    help_output = _run((*executable, "--help"), cwd=workspace, env=env)
    if "usage: qobuz-dl" not in help_output:
        raise VerificationFailure(
            f"{executable[-1]} --help did not show qobuz-dl usage"
        )
    version_output = _run((*executable, "--version"), cwd=workspace, env=env).strip()
    expected = f"qobuz-dl {EXPECTED_VERSION}"
    if version_output != expected:
        raise VerificationFailure(
            f"{executable[-1]} --version printed {version_output!r}, expected {expected!r}"
        )
    return {"help": "ok", "version": version_output}


def _environment_command(environment: Path, name: str) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / f"{name}.exe"
    return environment / "bin" / name


def _clean_environment(root: Path) -> tuple[dict[str, str], dict[str, Path]]:
    paths = {
        name: root / name
        for name in (
            "cache",
            "tools",
            "bin",
            "python",
            "work",
            "tmp",
            "config",
            "data",
        )
    }
    for path in paths.values():
        path.mkdir()

    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("PYTHON", "UV_", "PIP_"))
        and name not in {"VIRTUAL_ENV", "CONDA_PREFIX", "APPDATA", "LOCALAPPDATA"}
    }
    env.update(
        {
            "APPDATA": str(paths["config"]),
            "LOCALAPPDATA": str(paths["data"]),
            "XDG_CACHE_HOME": str(paths["cache"]),
            "XDG_CONFIG_HOME": str(paths["config"]),
            "XDG_DATA_HOME": str(paths["data"]),
            "TMPDIR": str(paths["tmp"]),
            "PYTHONNOUSERSITE": "1",
            "UV_CACHE_DIR": str(paths["cache"] / "uv"),
            "UV_PYTHON_INSTALL_DIR": str(paths["python"]),
            "UV_TOOL_DIR": str(paths["tools"]),
            "UV_TOOL_BIN_DIR": str(paths["bin"]),
        }
    )
    return env, paths


def verify(revision: str | None = None) -> dict[str, Any]:
    uv = shutil.which("uv")
    uvx = shutil.which("uvx")
    if uv is None or uvx is None:
        missing = ", ".join(
            name for name, path in (("uv", uv), ("uvx", uvx)) if path is None
        )
        raise VerificationFailure(
            f"required executable(s) not found on process PATH: {missing}"
        )

    requested_source = source_for_revision(revision)
    with tempfile.TemporaryDirectory(
        prefix="qobuz-dl-install-verification-"
    ) as temporary:
        root = Path(temporary).resolve()
        env, paths = _clean_environment(root)

        one_shot = _probe_with_uvx(
            uvx,
            requested_source,
            workspace=paths["work"],
            env=env,
        )
        resolved_commit = validate_record(one_shot, root, "one-shot")
        if revision is not None and resolved_commit != revision.lower():
            raise VerificationFailure(
                "the requested revision did not resolve to the requested commit"
            )
        pinned_source = source_for_revision(resolved_commit)
        one_shot_commands = {
            "qobuz-dl": _smoke(
                (
                    uvx,
                    "--no-config",
                    "--isolated",
                    "--no-progress",
                    "--from",
                    requested_source,
                    "qobuz-dl",
                ),
                workspace=paths["work"],
                env=env,
            )
        }

        _run(
            (uv, "tool", "install", "--no-config", "--no-progress", pinned_source),
            cwd=paths["work"],
            env=env,
        )
        tool_environment = paths["tools"] / "qobuz-dl"
        python = _environment_command(tool_environment, "python")
        python_path = _lexical_path_belongs_to(python, root, "persistent interpreter")
        if not python.is_file():
            raise VerificationFailure(f"persistent interpreter is missing: {python}")
        persistent = _probe_with_python(python, workspace=paths["work"], env=env)
        persistent_commit = validate_record(persistent, root, "persistent")
        compare_records(one_shot, persistent)
        if persistent_commit != resolved_commit:
            raise VerificationFailure(
                "persistent install did not resolve to the observed commit"
            )

        persistent_commands = {}
        executable_paths = {}
        for name in sorted(EXPECTED_ENTRY_POINTS):
            executable_name = f"{name}.exe" if os.name == "nt" else name
            executable = paths["bin"] / executable_name
            executable_paths[name] = _path_belongs_to(executable, root, name)
            if not executable.is_file():
                raise VerificationFailure(
                    f"persistent executable is missing: {executable}"
                )
            persistent_commands[name] = _smoke(
                (str(executable),), workspace=paths["work"], env=env
            )
        if one_shot_commands["qobuz-dl"] != persistent_commands["qobuz-dl"]:
            raise VerificationFailure(
                "one-shot and persistent qobuz-dl command outcomes disagree"
            )

        if revision is None:
            final_record = _probe_with_uvx(
                uvx,
                FLOATING_SOURCE,
                workspace=paths["work"],
                env=env,
                refresh=True,
            )
            final_commit = validate_record(final_record, root, "final one-shot")
            if final_commit != resolved_commit:
                raise VerificationFailure(
                    "the floating source moved during verification; rerun to verify one commit"
                )

        return {
            "source": requested_source,
            "resolved_commit": resolved_commit,
            "tools": {
                "uv": _run((uv, "--version"), cwd=paths["work"], env=env).strip(),
                "uvx": _run((uvx, "--version"), cwd=paths["work"], env=env).strip(),
            },
            "one_shot": one_shot,
            "persistent": persistent,
            "commands": {
                "one_shot": one_shot_commands,
                "persistent": persistent_commands,
            },
            "persistent_interpreter": python_path,
            "persistent_executables": executable_paths,
        }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        print("usage: verify_install.py [FULL_40_HEX_REVISION]", file=sys.stderr)
        return 2
    try:
        evidence = verify(arguments[0] if arguments else None)
    except KeyboardInterrupt:
        print("install verification interrupted", file=sys.stderr)
        return 130
    except (OSError, VerificationFailure) as error:
        print(f"install verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
