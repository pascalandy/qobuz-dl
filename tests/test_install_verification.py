import json
import os
import re
import signal
from copy import deepcopy
from importlib import util
from pathlib import Path

import pytest

from qobuz_dl.console import Terminated

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_install.py"
SPEC = util.spec_from_file_location("verify_install", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verify_install = util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_install)

EXPECTED_ENTRY_POINTS = verify_install.EXPECTED_ENTRY_POINTS
FLOATING_SOURCE = verify_install.FLOATING_SOURCE
FORK_REPOSITORY = verify_install.FORK_REPOSITORY
VerificationFailure = verify_install.VerificationFailure
_clean_environment = verify_install._clean_environment
_lexical_path_belongs_to = verify_install._lexical_path_belongs_to
_run = verify_install._run
compare_records = verify_install.compare_records
source_for_revision = verify_install.source_for_revision
validate_record = verify_install.validate_record

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _record(root: Path):
    location = root / "cache" / "environment" / "site-packages"
    location.mkdir(parents=True)
    return {
        "name": "qobuz-dl",
        "version": "1.0.0",
        "entry_points": EXPECTED_ENTRY_POINTS.copy(),
        "requirements": ["mutagen<2,>=1.47"],
        "location": str(location),
        "python_prefix": str(root / "cache" / "environment"),
        "python_version": "3.13.7",
        "direct_url": {
            "url": FORK_REPOSITORY,
            "vcs_info": {"vcs": "git", "commit_id": COMMIT},
        },
    }


def test_source_accepts_only_an_optional_full_sha():
    assert source_for_revision(None) == FLOATING_SOURCE
    assert source_for_revision(COMMIT.upper()) == f"{FLOATING_SOURCE}@{COMMIT}"

    for revision in ("main", COMMIT[:-1], f"{COMMIT}; touch nope"):
        with pytest.raises(VerificationFailure, match="full 40-character"):
            source_for_revision(revision)


def test_valid_metadata_record_returns_resolved_commit(tmp_path):
    assert validate_record(_record(tmp_path), tmp_path, "test") == COMMIT


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda record: record["direct_url"].update(
                url="https://github.com/vitiko98/Qobuz-DL"
            ),
            "fork URL",
        ),
        (lambda record: record["direct_url"]["vcs_info"].update(vcs="hg"), "Git VCS"),
        (
            lambda record: record["direct_url"]["vcs_info"].update(commit_id="abc123"),
            "full resolved",
        ),
        (lambda record: record.update(version="9.9.9"), "version"),
        (lambda record: record["entry_points"].pop("qdl"), "console scripts"),
        (lambda record: record.update(requirements=["mutagen>=1"]), "requirement"),
    ],
)
def test_invalid_metadata_is_rejected(tmp_path, mutation, message):
    record = _record(tmp_path)
    mutation(record)

    with pytest.raises(VerificationFailure, match=message):
        validate_record(record, tmp_path, "test")


def test_metadata_location_must_be_under_temporary_root(tmp_path):
    record = _record(tmp_path)
    record["location"] = str(tmp_path.parent / "daily-environment")

    with pytest.raises(VerificationFailure, match="outside the temporary root"):
        validate_record(record, tmp_path, "test")


def test_python_prefix_must_be_under_temporary_root(tmp_path):
    record = _record(tmp_path)
    record["python_prefix"] = str(tmp_path.parent / "daily-environment")

    with pytest.raises(VerificationFailure, match="Python prefix"):
        validate_record(record, tmp_path, "test")


@pytest.mark.skipif(os.name == "nt", reason="POSIX venv Python symlink behavior")
def test_lexical_venv_python_path_allows_an_external_symlink_target(tmp_path):
    root = tmp_path / "verification"
    interpreter = root / "tools" / "qobuz-dl" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    external_python = tmp_path / "system-python"
    external_python.write_text("")
    interpreter.symlink_to(external_python)

    assert _lexical_path_belongs_to(interpreter, root, "interpreter") == str(
        interpreter
    )


def test_one_shot_and_persistent_records_must_agree(tmp_path):
    one_shot = _record(tmp_path / "one-shot")
    persistent = deepcopy(one_shot)
    persistent["location"] = str(tmp_path / "persistent" / "site-packages")
    persistent["direct_url"]["vcs_info"]["commit_id"] = "f" * 40

    with pytest.raises(VerificationFailure, match="provenance"):
        compare_records(one_shot, persistent)


def test_requested_revision_detail_does_not_create_a_false_disagreement(tmp_path):
    one_shot = _record(tmp_path / "one-shot")
    persistent = deepcopy(one_shot)
    persistent["location"] = str(tmp_path / "persistent" / "site-packages")
    persistent["direct_url"]["vcs_info"]["requested_revision"] = COMMIT

    compare_records(one_shot, persistent)


def test_verify_rejects_an_explicit_revision_that_resolves_elsewhere(
    monkeypatch,
):
    monkeypatch.setattr(verify_install.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(verify_install, "_probe_with_uvx", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        verify_install,
        "validate_record",
        lambda *args, **kwargs: "f" * 40,
    )
    monkeypatch.setattr(
        verify_install,
        "_smoke",
        lambda *args, **kwargs: pytest.fail("must reject before command smoke"),
    )

    with pytest.raises(VerificationFailure, match="requested revision"):
        verify_install.verify(COMMIT.upper())


def test_verify_compares_an_explicit_revision_case_insensitively(monkeypatch):
    monkeypatch.setattr(verify_install.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(verify_install, "_probe_with_uvx", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        verify_install,
        "validate_record",
        lambda *args, **kwargs: COMMIT,
    )

    def reached_smoke(*args, **kwargs):
        raise RuntimeError("revision comparison passed")

    monkeypatch.setattr(verify_install, "_smoke", reached_smoke)

    with pytest.raises(RuntimeError, match="revision comparison passed"):
        verify_install.verify(COMMIT.upper())


def test_clean_environment_preserves_home_and_isolates_task_paths(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", "/daily/home")

    env, paths = _clean_environment(tmp_path)

    assert env["HOME"] == "/daily/home"
    assert "home" not in paths
    assert env["UV_TOOL_DIR"] == str(tmp_path / "tools")
    assert env["UV_PYTHON_INSTALL_DIR"] == str(tmp_path / "python")
    assert env["XDG_CONFIG_HOME"] == str(tmp_path / "config")


def test_subprocess_timeout_has_a_fixed_failure(monkeypatch, tmp_path):
    def time_out(*args, **kwargs):
        assert kwargs["timeout"] == 300
        raise verify_install.subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(verify_install.subprocess, "run", time_out)

    with pytest.raises(VerificationFailure, match="timed out after 300 seconds"):
        _run(("uv", "--version"), cwd=tmp_path, env={})


EVIDENCE = {"resolved_commit": COMMIT, "source": FLOATING_SOURCE}
RERUN = "uv run --frozen python scripts/verify_install.py --verbose"


@pytest.fixture
def quiet_environment(monkeypatch):
    monkeypatch.delenv("VERIFY_INSTALL_DEBUG", raising=False)


def _logging_verify(monkeypatch, *, result=None, error=None):
    calls = []

    def fake_verify(revision=None, *, timeout):
        calls.append((revision, timeout))
        verify_install.logger.info("+ uv --version")
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(verify_install, "verify", fake_verify)
    return calls


@pytest.mark.parametrize("flags", [[], ["-v"], ["--debug"]])
def test_success_prints_one_json_object_and_quiet_stderr(
    monkeypatch, capsys, quiet_environment, flags
):
    _logging_verify(monkeypatch, result=EVIDENCE)

    assert verify_install.main(flags) == 0

    output = capsys.readouterr()
    assert json.loads(output.out) == EVIDENCE
    assert output.out.count("\n") == 1
    assert output.err == ("" if not flags else "+ uv --version\n")


@pytest.mark.parametrize("flags", [[], ["-v"]])
def test_failure_prints_evidence_then_failure_then_rerun(
    monkeypatch, capsys, quiet_environment, flags
):
    failure = VerificationFailure(
        "`uv tool install` exited with status 2", output="uv: network is down"
    )
    _logging_verify(monkeypatch, error=failure)

    assert verify_install.main([*flags, COMMIT]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.endswith(
        "uv: network is down\n"
        "verify_install.py: install verification failed: "
        "`uv tool install` exited with status 2\n"
        f"rerun: {RERUN} {COMMIT}\n"
    )


def test_nonzero_command_keeps_its_output_as_evidence(monkeypatch, tmp_path):
    def failed_run(command, **kwargs):
        return verify_install.subprocess.CompletedProcess(command, 2, "", "boom\n")

    monkeypatch.setattr(verify_install.subprocess, "run", failed_run)

    with pytest.raises(VerificationFailure) as failure:
        _run(("uv", "tool", "install"), cwd=tmp_path, env={})

    assert str(failure.value) == "`uv tool install` exited with status 2"
    assert failure.value.output == "boom"
    assert failure.value.temporary is False


def test_timeout_is_temporary_and_suggests_a_retry(
    monkeypatch, capsys, quiet_environment
):
    def time_out(*args, **kwargs):
        raise verify_install.subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(verify_install.subprocess, "run", time_out)

    def fake_verify(revision=None, *, timeout):
        return _run(("uvx", "--version"), cwd=Path("."), env={}, timeout=timeout)

    monkeypatch.setattr(verify_install, "verify", fake_verify)

    assert verify_install.main(["--timeout=90s"]) == 75

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "verify_install.py: install verification failed: "
        "uvx timed out after 90 seconds\n"
        f"retry: {RERUN} --timeout 90s\n"
    )


def test_floating_source_moving_during_verification_is_temporary(
    monkeypatch, capsys, quiet_environment
):
    commits = iter([COMMIT, COMMIT, "f" * 40])
    monkeypatch.setattr(verify_install.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(verify_install, "_probe_with_uvx", lambda *a, **k: {})
    monkeypatch.setattr(verify_install, "_probe_with_python", lambda *a, **k: {})
    monkeypatch.setattr(verify_install, "validate_record", lambda *a: next(commits))
    monkeypatch.setattr(verify_install, "compare_records", lambda *a: None)
    monkeypatch.setattr(
        verify_install,
        "_smoke",
        lambda *a, **k: {"help": "ok", "version": "qobuz-dl 1.0.0"},
    )

    def fake_run(command, *, cwd, env, timeout):
        if command[1:3] == ("tool", "install"):
            python = verify_install._environment_command(
                Path(env["UV_TOOL_DIR"]) / "qobuz-dl", "python"
            )
            python.parent.mkdir(parents=True)
            python.touch()
            for name in EXPECTED_ENTRY_POINTS:
                executable = f"{name}.exe" if os.name == "nt" else name
                (Path(env["UV_TOOL_BIN_DIR"]) / executable).touch()
        return ""

    monkeypatch.setattr(verify_install, "_run", fake_run)

    assert verify_install.main([]) == 75

    assert capsys.readouterr().err == (
        "verify_install.py: install verification failed: the floating source "
        "moved during verification; rerun to verify one commit\n"
        f"retry: {RERUN}\n"
    )


def test_unexpected_error_suggests_debug_and_debug_prints_the_trace(
    monkeypatch, capsys, quiet_environment
):
    _logging_verify(monkeypatch, error=RuntimeError("unexpected state"))

    assert verify_install.main([]) == 1
    assert capsys.readouterr().err == (
        "verify_install.py: unexpected error: unexpected state\n"
        "rerun with a stack trace: "
        "uv run --frozen python scripts/verify_install.py --debug\n"
    )

    monkeypatch.setenv("VERIFY_INSTALL_DEBUG", "1")
    assert verify_install.main([]) == 1
    assert "Traceback (most recent call last)" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("interruption", "code"), [(KeyboardInterrupt, 130), (Terminated, 143)]
)
def test_interruptions_exit_with_the_signal_code(
    monkeypatch, capsys, quiet_environment, interruption, code
):
    _logging_verify(monkeypatch, error=interruption())

    assert verify_install.main([]) == code

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "verify_install.py: interrupted\n"


@pytest.mark.parametrize(
    "argv", [["main"], [COMMIT[:-1]], [COMMIT, COMMIT], ["--timeout", "soon"]]
)
def test_invalid_input_is_a_usage_error(monkeypatch, capsys, argv):
    monkeypatch.setattr(
        verify_install, "verify", lambda *a, **k: pytest.fail("verification ran")
    )

    with pytest.raises(SystemExit) as usage_exit:
        verify_install.main(argv)

    assert usage_exit.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("usage: verify_install.py ")
    assert output.err.endswith(
        "run 'uv run --frozen python scripts/verify_install.py --help' for usage\n"
    )


def test_help_wins_and_lists_examples_and_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(
        verify_install, "verify", lambda *a, **k: pytest.fail("verification ran")
    )

    with pytest.raises(SystemExit) as help_exit:
        verify_install.main(["not-a-sha", "--timeout", "soon", "-vh"])

    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    assert help_text.startswith("usage: verify_install.py ")
    examples = help_text.split("Examples:\n", 1)[1].split("\n\n", 1)[0]
    assert 2 <= len(examples.splitlines()) <= 5
    for code in (0, 1, 2, 75, 130, 143):
        assert re.search(rf"^  {code} +\S", help_text, re.MULTILINE)


def test_options_follow_posix_parsing_rules(monkeypatch, capsys, quiet_environment):
    calls = _logging_verify(monkeypatch, result=EVIDENCE)

    assert verify_install.main(["--timeout=10m", "--", COMMIT]) == 0
    assert verify_install.main(["--timeout", "10m", COMMIT]) == 0

    assert calls == [(COMMIT, 600.0), (COMMIT, 600.0)]


def test_every_short_flag_has_a_long_form():
    for action in verify_install.build_parser()._actions:
        if any(len(option) == 2 for option in action.option_strings):
            assert any(option.startswith("--") for option in action.option_strings)


SIGNAL_DRIVER = """
import signal
import sys
import time
from importlib import util
from pathlib import Path

signal.signal(signal.SIGINT, signal.default_int_handler)
workspace = Path(sys.argv[1])
spec = util.spec_from_file_location("verify_install", sys.argv[2])
verify_install = util.module_from_spec(spec)
spec.loader.exec_module(verify_install)


def blocking_verify(revision=None, *, timeout):
    (workspace / "ready").touch()
    while True:
        time.sleep(0.05)


verify_install.verify = blocking_verify
sys.exit(verify_install.main([]))
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal delivery")
@pytest.mark.parametrize(
    ("signal_number", "code"), [(signal.SIGINT, 130), (signal.SIGTERM, 143)]
)
def test_real_signal_exits_with_the_signal_code(signal_driver, signal_number, code):
    status, out, err = signal_driver(SIGNAL_DRIVER, signal_number, str(MODULE_PATH))

    assert (status, out, err) == (code, "", "verify_install.py: interrupted\n")
