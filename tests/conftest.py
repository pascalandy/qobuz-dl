import io
import os
import subprocess
import sys
import time

import pytest

# Variables from the developer's shell that would change what a test observes
# or, for config lookup, point a test at the real user config and database.
_HOST_VARIABLES = (
    "NO_COLOR",
    "TERM",
    "QOBUZ_DL_DEBUG",
    "QOBUZ_DL_CONFIG",
    "XDG_CONFIG_HOME",
    "CHECK_DEBUG",
    "VERIFY_INSTALL_DEBUG",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Clear host variables; child processes inherit the cleaned environment."""
    for name in _HOST_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name in list(os.environ):
        if name.startswith("QOBUZ_DL_LIVE"):
            monkeypatch.delenv(name)


class _Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def terminal_stdin(monkeypatch):
    """Make stdin an interactive terminal, so commands may prompt."""
    stdin = _Terminal()
    monkeypatch.setattr(sys, "stdin", stdin)
    return stdin


@pytest.fixture
def signal_driver(tmp_path):
    """Run Python ``source`` in a child, then signal it once it is ready.

    The driver receives ``tmp_path`` as ``sys.argv[1]`` and must create
    ``tmp_path / "ready"`` when it is blocked in the code under test. The
    fixture returns the child's exit status, stdout, and stderr.
    """

    def run(source, signal_number, *arguments, timeout=30):
        ready = tmp_path / "ready"
        process = subprocess.Popen(
            (sys.executable, "-c", source, str(tmp_path), *arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + timeout
            while not ready.exists():
                if process.poll() is not None:
                    pytest.fail(f"the driver exited early: {process.communicate()}")
                if time.monotonic() > deadline:
                    pytest.fail("the driver never became ready")
                time.sleep(0.02)
            process.send_signal(signal_number)
            out, err = process.communicate(timeout=timeout)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        return process.returncode, out, err

    return run
