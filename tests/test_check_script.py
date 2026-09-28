import hashlib
import os
import re
import signal
import sys
import time
from importlib import util
from pathlib import Path

import pytest

from qobuz_dl.console import Terminated

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check.py"
SPEC = util.spec_from_file_location("check_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_script = util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_script)

PYTHON = sys.executable


def _python(code):
    return (PYTHON, "-c", code)


@pytest.fixture
def stubbed_pipeline(tmp_path, monkeypatch):
    """Replace every real gate with a fast local command and a fake build."""
    monkeypatch.delenv("CHECK_DEBUG", raising=False)
    monkeypatch.setattr(check_script, "ROOT", tmp_path)
    monkeypatch.setattr(
        check_script, "SOURCE_GATES", (_python("print('gate output')"),)
    )
    monkeypatch.setattr(check_script, "CLI_PROBES", ())

    def fake_build(uv, output):
        output.mkdir(parents=True)
        wheel = output / "qobuz_dl-1.0.0-py3-none-any.whl"
        wheel.write_bytes(b"wheel bytes")
        source = output / "qobuz_dl-1.0.0.tar.gz"
        source.write_bytes(b"source bytes")
        return wheel, source

    monkeypatch.setattr(check_script, "build", fake_build)
    monkeypatch.setattr(check_script, "verify_wheel", lambda *args, **kwargs: None)
    return tmp_path


def _stderr(capture):
    # Verbose gates write straight to file descriptor 2, so a Windows child's
    # text output keeps its CRLF line endings.
    return capture.err.replace("\r\n", "\n")


def _success_line():
    digest = hashlib.sha256(b"wheel bytes").hexdigest()
    return f"{digest}  dist/qobuz_dl-1.0.0-py3-none-any.whl\n"


def test_success_prints_only_the_sha256_line(stubbed_pipeline, capfd):
    assert check_script.main([]) == 0

    output = capfd.readouterr()
    assert output.out == _success_line()
    assert output.err == ""
    published = stubbed_pipeline / "dist" / "qobuz_dl-1.0.0-py3-none-any.whl"
    assert published.read_bytes() == b"wheel bytes"


@pytest.mark.parametrize("flag", ["-v", "--verbose", "--debug"])
def test_verbosity_changes_only_stderr_on_success(stubbed_pipeline, capfd, flag):
    assert check_script.main([flag]) == 0

    output = capfd.readouterr()
    error = _stderr(output)
    assert output.out == _success_line()
    assert "+ " in error
    assert "gate output\n" in error
    assert "verified wheel sha256: " in error
    assert ("finished in " in error) is (flag == "--debug")


def test_check_debug_environment_enables_debug(stubbed_pipeline, capfd, monkeypatch):
    monkeypatch.setenv("CHECK_DEBUG", "1")

    assert check_script.main([]) == 0

    assert "finished in " in capfd.readouterr().err


@pytest.mark.parametrize("flags", [[], ["-v"], ["--debug"]])
def test_gate_failure_exits_1_with_output_then_rerun(
    stubbed_pipeline, capfd, monkeypatch, flags
):
    failing = _python("import sys; print('boom'); sys.exit(3)")
    monkeypatch.setattr(check_script, "SOURCE_GATES", (failing,))

    assert check_script.main(flags) == 1

    output = capfd.readouterr()
    error = _stderr(output)
    assert output.out == ""
    command = check_script.format_command(failing)
    failure = (
        f"check.py: `{command}` exited with status 3\n"
        f"rerun: uv run --frozen {command}\n"
    )
    assert "boom\n" in error
    assert error.endswith(failure)
    if not flags:
        assert error == "boom\n" + failure


def test_temporary_workspace_failures_rerun_the_durable_command(
    stubbed_pipeline, capfd, monkeypatch
):
    def failing_verify(uv, wheel, *, workspace, expected_version):
        check_script.run(_python("import sys; sys.exit(4)"), cwd=workspace)

    monkeypatch.setattr(check_script, "verify_wheel", failing_verify)

    assert check_script.main([]) == 1

    error = capfd.readouterr().err
    assert error.endswith("rerun: uv run --frozen python scripts/check.py --verbose\n")
    assert "qobuz-dl-check-" not in error.splitlines()[-1]


def test_unexpected_error_suggests_debug_and_debug_prints_the_trace(
    stubbed_pipeline, capfd, monkeypatch
):
    def broken(*args, **kwargs):
        raise RuntimeError("unexpected state")

    monkeypatch.setattr(check_script, "verify_wheel", broken)

    assert check_script.main([]) == 1
    quiet = capfd.readouterr()
    assert quiet.err == (
        "check.py: unexpected error: unexpected state\n"
        "rerun with a stack trace: uv run --frozen python scripts/check.py --debug\n"
    )

    assert check_script.main(["--debug"]) == 1
    debug = capfd.readouterr()
    assert debug.out == quiet.out == ""
    assert "Traceback (most recent call last)" in debug.err


@pytest.mark.parametrize(
    ("interruption", "code"), [(KeyboardInterrupt, 130), (Terminated, 143)]
)
def test_interruptions_exit_with_the_signal_code(
    stubbed_pipeline, capfd, monkeypatch, interruption, code
):
    def interrupted(*args, **kwargs):
        raise interruption

    monkeypatch.setattr(check_script, "verify_wheel", interrupted)

    assert check_script.main([]) == code

    output = capfd.readouterr()
    assert output.out == ""
    assert output.err == "check.py: interrupted\n"


def test_help_lists_examples_and_exit_codes_without_running_gates(capsys, monkeypatch):
    monkeypatch.setattr(
        check_script, "check", lambda: pytest.fail("--help ran the gates")
    )

    for argv in (["--help"], ["-h"], ["--bogus", "-vh"]):
        with pytest.raises(SystemExit) as help_exit:
            check_script.main(argv)
        assert help_exit.value.code == 0

    help_text = capsys.readouterr().out
    assert help_text.startswith("usage: check.py ")
    examples = help_text.split("Examples:\n", 1)[1].split("\n\n", 1)[0]
    assert 2 <= len(examples.splitlines()) <= 5
    for code in (0, 1, 2, 130, 143):
        assert re.search(rf"^  {code} +\S", help_text, re.MULTILINE)


@pytest.mark.parametrize("argv", [["--bogus"], ["--verb"], ["--", "-v"]])
def test_usage_errors_exit_2_with_a_help_hint(capsys, monkeypatch, argv):
    monkeypatch.setattr(
        check_script, "check", lambda: pytest.fail("a usage error ran the gates")
    )

    with pytest.raises(SystemExit) as usage_exit:
        check_script.main(argv)

    assert usage_exit.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("usage: check.py ")
    assert output.err.endswith(
        "run 'uv run --frozen python scripts/check.py --help' for usage\n"
    )


def test_every_short_flag_has_a_long_form():
    for action in check_script.build_parser()._actions:
        if any(len(option) == 2 for option in action.option_strings):
            assert any(option.startswith("--") for option in action.option_strings)


GROUP_DRIVER = """
import sys
from importlib import util
from pathlib import Path

import signal

signal.signal(signal.SIGINT, signal.default_int_handler)
workspace = Path(sys.argv[1])
spec = util.spec_from_file_location("check_script", sys.argv[2])
check_script = util.module_from_spec(spec)
spec.loader.exec_module(check_script)

SPAWNER = '''
import subprocess, sys, time
from pathlib import Path
workspace = Path(sys.argv[1])
grandchild = subprocess.Popen((sys.executable, "-c", "import time; time.sleep(600)"))
(workspace / "grandchild.pid").write_text(str(grandchild.pid))
(workspace / "ready").touch()
time.sleep(600)
'''
check_script.SOURCE_GATES = ((sys.executable, "-c", SPAWNER, str(workspace)),)
check_script.CLI_PROBES = ()
sys.exit(check_script.main([]))
"""


def _process_gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    status = Path(f"/proc/{pid}/stat")
    try:
        return status.read_text().split(") ", 1)[1].startswith("Z")
    except (OSError, IndexError):
        return False


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups and signals")
@pytest.mark.parametrize(
    ("signal_number", "code"), [(signal.SIGINT, 130), (signal.SIGTERM, 143)]
)
def test_parent_only_signal_stops_the_gate_and_its_descendants(
    tmp_path, signal_driver, signal_number, code
):
    status, out, err = signal_driver(GROUP_DRIVER, signal_number, str(SCRIPT))

    assert status == code
    assert out == ""
    assert err == "check.py: interrupted\n"
    grandchild = int((tmp_path / "grandchild.pid").read_text())
    deadline = time.monotonic() + 10
    while not _process_gone(grandchild) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _process_gone(grandchild), f"descendant {grandchild} survived"
