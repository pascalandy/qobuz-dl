import os
from copy import deepcopy
from importlib import util
from pathlib import Path

import pytest

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
