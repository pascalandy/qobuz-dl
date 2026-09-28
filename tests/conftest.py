import subprocess
import sys
import time

import pytest


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
