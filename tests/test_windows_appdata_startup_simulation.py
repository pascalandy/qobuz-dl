"""Portable Windows startup simulation for issue 41.

This is not native Windows coverage. The child import hook gives only
``qobuz_dl.cli`` an ``os`` proxy backed by ``ntpath``.
"""

import ntpath
import os
import posixpath
import subprocess
import sys

import pytest

import qobuz_dl.cli as cli

APPDATA_DIAGNOSTIC = (
    "APPDATA is not set. Set APPDATA to your Windows application-data "
    "directory and retry."
)

SIMULATED_WINDOWS_CHILD = r"""
import builtins
import importlib
import ntpath
import os as real_os
import sys


class CliOsProxy:
    name = "nt"
    path = ntpath
    environ = real_os.environ

    def __getattr__(self, attribute):
        return getattr(real_os, attribute)


real_import = builtins.__import__
cli_os = CliOsProxy()


def import_with_cli_os(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "os" and globals and globals.get("__name__") == "qobuz_dl.cli":
        return cli_os
    return real_import(name, globals, locals, fromlist, level)


builtins.__import__ = import_with_cli_os
try:
    package = importlib.import_module("qobuz_dl")
    cli = importlib.import_module("qobuz_dl.cli")
finally:
    builtins.__import__ = real_import

if not callable(package.main) or package.main is not cli.main:
    raise AssertionError("package and CLI entry points did not import")


def unexpected(*args, **kwargs):
    raise AssertionError("prompt, config, or network work ran")


builtins.input = unexpected
cli.getpass.getpass = unexpected
cli._ensure_config_exists = unexpected
cli._load_config_values = unexpected
cli._reset_config = unexpected
cli.Bundle = unexpected
cli.QobuzDL = unexpected
sys.argv = ["qobuz-dl", *sys.argv[1:]]
package.main()
"""


class _CliOsProxy:
    def __init__(self, *, name, path, environ):
        self.name = name
        self.path = path
        self.environ = environ


def _resolver_contract():
    resolver = getattr(cli, "_resolve_config_paths", None)
    error_type = getattr(cli, "_ConfigPathError", None)
    if resolver is None or error_type is None:
        pytest.fail("qobuz_dl.cli has no config path resolver contract")
    return resolver, error_type


def _run_simulated_windows_cli(tmp_path, argv, appdata):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    environment = {
        **os.environ,
        "HOME": str(sandbox),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if appdata is None:
        environment.pop("APPDATA", None)
    else:
        environment["APPDATA"] = appdata

    result = subprocess.run(
        [sys.executable, "-I", "-c", SIMULATED_WINDOWS_CHILD, *argv],
        cwd=sandbox,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    side_effects = sorted(str(path.relative_to(sandbox)) for path in sandbox.rglob("*"))
    return result, side_effects


@pytest.mark.parametrize("appdata", [None, ""], ids=["missing", "empty"])
@pytest.mark.parametrize(
    ("argv", "expected_output"),
    [
        (["--help"], "Download and organize Qobuz music"),
        (["--version"], "qobuz-dl 1.0.0"),
        (["dl", "--help"], "Download Qobuz album, track, artist"),
        (["fun", "--help"], "Interactively search Qobuz"),
        (["lucky", "--help"], "Search Qobuz and download the first"),
    ],
    ids=["root-help", "version", "dl-help", "fun-help", "lucky-help"],
)
def test_simulated_windows_metadata_routes_ignore_missing_appdata(
    tmp_path, appdata, argv, expected_output
):
    result, side_effects = _run_simulated_windows_cli(tmp_path, argv, appdata)

    assert (
        result.returncode,
        result.stderr,
        expected_output in result.stdout,
        side_effects,
    ) == (0, "", True, [])


@pytest.mark.parametrize("appdata", [None, ""], ids=["missing", "empty"])
def test_simulated_windows_continuing_command_reports_missing_appdata_safely(
    tmp_path, appdata
):
    result, side_effects = _run_simulated_windows_cli(
        tmp_path,
        ["dl", "https://play.qobuz.com/album/example"],
        appdata,
    )

    assert (
        result.returncode,
        result.stdout,
        result.stderr,
        side_effects,
    ) == (1, "", f"{APPDATA_DIAGNOSTIC}\n", [])


def test_simulated_windows_resolver_preserves_present_appdata(monkeypatch):
    resolver, _ = _resolver_contract()
    monkeypatch.setattr(
        cli,
        "os",
        _CliOsProxy(
            name="nt",
            path=ntpath,
            environ={"APPDATA": r"R:\Roaming Data"},
        ),
    )

    assert resolver() == (
        r"R:\Roaming Data\qobuz-dl\config.ini",
        r"R:\Roaming Data\qobuz-dl\qobuz_dl.db",
    )


@pytest.mark.parametrize(
    "environment",
    [{}, {"APPDATA": ""}],
    ids=["missing", "empty"],
)
def test_simulated_windows_resolver_rejects_missing_appdata(monkeypatch, environment):
    resolver, error_type = _resolver_contract()
    monkeypatch.setattr(
        cli,
        "os",
        _CliOsProxy(name="nt", path=ntpath, environ=environment),
    )

    with pytest.raises(error_type):
        resolver()


def test_simulated_posix_resolver_keeps_existing_paths(monkeypatch, tmp_path):
    resolver, _ = _resolver_contract()
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        cli,
        "os",
        _CliOsProxy(name="posix", path=posixpath, environ={"HOME": str(home)}),
    )

    assert resolver() == (
        str(home / ".config" / "qobuz-dl" / "config.ini"),
        str(home / ".config" / "qobuz-dl" / "qobuz_dl.db"),
    )
