import io
import json
import os
import stat
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import qobuz_dl.cli as cli
from qobuz_dl import downloader, http
from qobuz_dl.core import QobuzDL, RunItem, RunProblem
from qobuz_dl.downloader import DownloadResult
from qobuz_dl.exceptions import AuthenticationError

FIXTURES = Path(__file__).parent / "fixtures"
ALBUM = "https://play.qobuz.com/album/alb1"
PLAYLIST = "https://play.qobuz.com/playlist/pl1"
LASTFM = "https://www.last.fm/user/example/playlists/9"
URL = ALBUM


def _write_config(path, **overrides):
    values = {
        "email": "user@example.com",
        "password": "hashed-password",
        "default_folder": str(path.parent.parent / "Music"),
        "default_limit": "20",
        "default_quality": "6",
        "no_m3u": "false",
        "albums_only": "false",
        "no_fallback": "false",
        "og_cover": "false",
        "embed_art": "false",
        "no_cover": "false",
        "no_database": "false",
        "app_id": "123456",
        "smart_discography": "false",
        "folder_format": "{albumartist} - {album}",
        "track_format": "{tracknumber}. {tracktitle}",
        "secrets": "secret-one",
    }
    values.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[DEFAULT]\n" + "".join(f"{key} = {value}\n" for key, value in values.items())
    )
    return path


def _paths(monkeypatch, tmp_path):
    config_file = tmp_path / "config" / "config.ini"
    database = tmp_path / "config" / "qobuz_dl.db"
    monkeypatch.setattr(
        cli, "_resolve_config_paths", lambda: (str(config_file), str(database))
    )
    return config_file, database


def _scripted(outcomes):
    class Runtime:
        def __init__(self, directory, *args, **kwargs):
            self.directory = directory

        def initialize_client(self, *args):
            pass

        def download_sources(self, sources):
            for entry in outcomes:
                if isinstance(entry, BaseException):
                    raise entry
                if isinstance(entry, RunItem):
                    self.run_result.add_item(entry)
                else:
                    self.run_result.add_problem(entry)
            return self.run_result

        def lucky_mode(self, query, download=True):
            return ["https://play.qobuz.com/album/r1"]

    return Runtime


def _json_run(argv, capsys):
    try:
        code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code
    output = capsys.readouterr()
    assert output.out.count("\n") == 1, output.out
    document = json.loads(output.out)
    assert isinstance(document, dict)
    assert set(document) == {
        "schema_version",
        "operation",
        "status",
        "data",
        "problems",
    }
    assert document["schema_version"] == 1
    return code, document, output.err


def _item(state, reason, paths=(), retryable=False, item_id="1"):
    return RunItem(
        URL, "track", item_id, DownloadResult(state, reason, tuple(paths), retryable)
    )


def test_dl_json_is_one_object_with_items_and_totals(monkeypatch, tmp_path, capsys):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    monkeypatch.setattr(
        cli,
        "QobuzDL",
        _scripted(
            [
                _item("finalized", "downloaded", ["M/01.flac"]),
                _item("finalized", "existing_file", ["M/02.flac"], item_id="2"),
                _item("ignored", "type_filter", item_id="3"),
            ]
        ),
    )

    code, document, error = _json_run(["dl", URL, "--json"], capsys)

    assert (code, error) == (0, "")
    assert document["operation"] == "dl"
    assert document["status"] == "ok"
    assert document["problems"] == []
    assert document["data"]["dry_run"] is False
    assert document["data"]["items"][0] == {
        "source": URL,
        "kind": "track",
        "item_id": "1",
        "state": "finalized",
        "reason": "downloaded",
        "retryable": False,
        "paths": ["M/01.flac"],
        "evidence": "published",
        "exists": None,
    }
    assert document["data"]["items"][1]["evidence"] == "filename_only"
    assert document["data"]["totals"] == {
        "items": 3,
        "finalized": 2,
        "planned": 0,
        "ignored": 1,
        "failed": 0,
        "retryable": 0,
        "problems": 0,
    }


@pytest.mark.parametrize(
    ("outcomes", "code", "retryable"),
    [
        (
            [_item("finalized", "downloaded", ["a"]), _item("failed", "path_conflict")],
            1,
            False,
        ),
        (
            [
                _item("finalized", "downloaded", ["a"]),
                RunProblem("rate_limited", "limit", URL, retryable=True),
            ],
            75,
            True,
        ),
    ],
    ids=["permanent", "temporary"],
)
def test_dl_json_reports_partial_failures(
    monkeypatch, tmp_path, capsys, outcomes, code, retryable
):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    monkeypatch.setattr(cli, "QobuzDL", _scripted(outcomes))

    exit_code, document, _error = _json_run(["dl", URL, "--json"], capsys)

    assert exit_code == code
    assert document["status"] == "failed"
    assert document["data"]["items"][0]["state"] == "finalized"
    if retryable:
        assert document["problems"] == [
            {
                "code": "rate_limited",
                "severity": "error",
                "message": "limit",
                "source": URL,
                "retryable": True,
                "hint": f"qobuz-dl dl {URL} --json",
            }
        ]


def test_interrupted_json_run_reports_partial_items(monkeypatch, tmp_path, capsys):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    monkeypatch.setattr(
        cli,
        "QobuzDL",
        _scripted(
            [_item("finalized", "downloaded", ["M/01.flac"]), KeyboardInterrupt()]
        ),
    )

    code, document, _error = _json_run(["dl", URL, "--json"], capsys)

    assert code == 130
    assert document["status"] == "interrupted"
    assert [item["paths"] for item in document["data"]["items"]] == [["M/01.flac"]]
    assert document["problems"][-1]["code"] == "interrupted"


def test_lucky_json_names_its_operation(monkeypatch, tmp_path, capsys):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    monkeypatch.setattr(
        cli, "QobuzDL", _scripted([_item("finalized", "downloaded", ["a.flac"])])
    )

    code, document, _error = _json_run(["--json", "lucky", "some query"], capsys)

    assert (code, document["operation"], document["status"]) == (0, "lucky", "ok")


def test_show_config_json_holds_paths_and_redacted_settings(
    monkeypatch, tmp_path, capsys
):
    config_file, database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)

    code, document, _error = _json_run(["--show-config", "--json"], capsys)

    assert (code, document["operation"], document["status"]) == (0, "show-config", "ok")
    data = document["data"]
    assert data["config_path"] == str(config_file)
    assert data["database_path"] == str(database)
    assert data["settings"]["email"] == "<redacted>"
    assert data["settings"]["password"] == "<redacted>"
    assert data["settings"]["secrets"] == "<redacted>"
    assert data["settings"]["default_quality"] == "6"
    assert "user@example.com" not in json.dumps(document)


@pytest.mark.parametrize("exists", [True, False])
def test_purge_json_reports_path_and_deletion(monkeypatch, tmp_path, capsys, exists):
    _config_file, database = _paths(monkeypatch, tmp_path)
    database.parent.mkdir(parents=True)
    if exists:
        database.write_bytes(b"history")

    code, document, error = _json_run(["--purge", "--json"], capsys)

    assert (code, error) == (0, "")
    assert document["operation"] == "purge"
    assert document["data"] == {"database_path": str(database), "deleted": exists}
    assert not database.exists()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--json"], "choose a command"),
        (["fun", "--json"], "fun needs an interactive terminal"),
        (["--reset", "--json"], "--reset without a terminal needs --email and"),
        (["dl", "https://evil.invalid/track/1", "--json"], "not a supported Qobuz"),
        (["--json", "dll", URL], "unknown command 'dll'"),
        (["--json", "--purge", "--show-config"], "cannot be combined"),
        (["--json", "lucky", "ab"], "at least 3 characters"),
    ],
)
def test_usage_errors_with_json_are_one_usage_error_object(
    monkeypatch, capsys, terminal_stdin, argv, message
):
    monkeypatch.setattr(
        cli, "_resolve_config_paths", lambda: pytest.fail("reached config")
    )
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("prompted"))

    code, document, error = _json_run(argv, capsys)

    assert code == 2
    assert document["operation"] is None
    assert document["status"] == "usage_error"
    assert document["data"] is None
    (problem,) = document["problems"]
    assert problem["code"] == "usage_error"
    assert message in problem["message"]
    assert problem["hint"].startswith("run 'qobuz-dl")
    assert message in error


def test_runtime_failure_with_json_reports_the_problem(monkeypatch, tmp_path, capsys):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    runtime = _scripted([])

    def initialize_client(self, *args):
        raise AuthenticationError("Invalid credentials.")

    runtime.initialize_client = initialize_client
    monkeypatch.setattr(cli, "QobuzDL", runtime)

    code, document, _error = _json_run(["dl", URL, "--json"], capsys)

    assert code == 1
    assert document["status"] == "failed"
    assert [p["code"] for p in document["problems"]] == ["login_failed"]


@pytest.mark.parametrize("argv", [["--json", "--help"], ["dl", "--json", "-h"]])
def test_help_wins_over_json(capsys, argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("usage: qobuz-dl")


def test_version_wins_over_json(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--json", "--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("qobuz-dl ")


def test_json_after_double_dash_is_a_source(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["dl", "--", "--json"])

    output = capsys.readouterr()
    assert exc.value.code == 2
    assert output.out == ""
    assert "no such file: '--json'" in output.err


@pytest.mark.parametrize("argv", [["lucky", "-n", "3", "q"], ["lucky", "-n3", "query"]])
def test_old_lucky_count_flag_is_rejected_with_guidance(monkeypatch, capsys, argv):
    monkeypatch.setattr(
        cli, "_resolve_config_paths", lambda: pytest.fail("reached config")
    )

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert "qobuz-dl lucky: error: -n now means --dry-run; use --limit N" in (
        capsys.readouterr().err
    )


def test_n_is_dry_run_everywhere_else():
    from qobuz_dl.commands import qobuz_dl_args

    parser = qobuz_dl_args()

    assert parser.parse_args(["lucky", "query", "-n"]).dry_run is True
    assert parser.parse_args(["-n", "dl", URL]).dry_run is True
    assert parser.parse_args(["lucky", "--number", "3", "q"]).limit == 3


@pytest.mark.parametrize("argv", [["--dry-run", "--reset"], ["fun", "-n"]])
def test_dry_run_rejects_commands_that_would_write_or_prompt(
    monkeypatch, capsys, terminal_stdin, argv
):
    monkeypatch.setattr(
        cli, "_resolve_config_paths", lambda: pytest.fail("reached config")
    )

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert "--dry-run cannot be combined with" in capsys.readouterr().err


def test_dry_run_with_missing_config_exits_2_without_creating_it(
    monkeypatch, tmp_path, capsys, terminal_stdin
):
    config_file, _database = _paths(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "_reset_config", lambda path: pytest.fail("prompted"))

    with pytest.raises(SystemExit) as exc:
        cli.main(["dl", URL, "--dry-run"])

    assert exc.value.code == 2
    assert f"no config file at {config_file}" in capsys.readouterr().err
    assert not config_file.parent.exists()


@pytest.mark.parametrize("exists", [True, False])
def test_purge_dry_run_prints_the_database_path_and_deletes_nothing(
    monkeypatch, tmp_path, capsys, exists
):
    _config_file, database = _paths(monkeypatch, tmp_path)
    database.parent.mkdir(parents=True)
    if exists:
        database.write_bytes(b"history")

    assert cli.main(["--purge", "--dry-run"]) == 0

    assert capsys.readouterr() == (f"{database}\n", "")
    assert database.exists() is exists

    code, document, _error = _json_run(["--purge", "-n", "--json"], capsys)
    assert code == 0
    assert document["data"] == {
        "database_path": str(database),
        "deleted": False,
        "exists": exists,
        "dry_run": True,
    }


def test_constructor_does_not_create_the_download_root(tmp_path):
    root = tmp_path / "not-yet" / "Music"

    qobuz = QobuzDL(directory=root, no_cover=True)

    assert qobuz.directory == str(root)
    assert not root.exists()


def test_name_limit_comes_from_the_nearest_existing_ancestor(tmp_path, monkeypatch):
    seen = []

    def fake_pathconf(path, name):
        seen.append(path)
        return 99

    monkeypatch.setattr(os, "pathconf", fake_pathconf, raising=False)

    missing = tmp_path / "a" / "b" / "c"
    assert downloader._destination_name_max(str(missing)) == 99
    assert seen == [str(tmp_path)]


def _track_url(track_id):
    return {
        "url": f"https://media.example.test/{track_id}.flac",
        "format_id": 6,
        "mime_type": "audio/flac",
        "sampling_rate": 44.1,
        "bit_depth": 16,
    }


def _track(track_id, number, title):
    return {
        "id": track_id,
        "title": title,
        "performer": {"name": "Artist"},
        "track_number": number,
        "media_number": 1,
        "maximum_bit_depth": 16,
        "maximum_sampling_rate": 44.1,
        "version": None,
        "duration": 180,
        "hires_streamable": False,
        "album": {
            "title": "Singles",
            "artist": {"name": "Artist"},
            "release_date_original": "2024-01-02",
            "image": {"large": "https://images.example.test/cover.jpg"},
        },
    }


class FakeQobuzApi:
    """A read-only Qobuz and Last.fm server; media requests fail the test."""

    ALLOWED = {
        "user/login",
        "track/getFileUrl",
        "track/get",
        "album/get",
        "playlist/get",
        "track/search",
    }

    def __init__(self):
        self.endpoints = []
        self.tracks = {
            "t1": _track("t1", 1, "One"),
            "t2": _track("t2", 2, "Two"),
            "t9": _track("t9", 3, "Nine"),
        }

    def urlopen(self, request, timeout):
        parts = urlsplit(request.full_url)
        if parts.netloc == "www.last.fm":
            self.endpoints.append("last.fm")
            return _Response((FIXTURES / "lastfm_playlist.html").read_bytes())
        if parts.netloc != "www.qobuz.com":
            pytest.fail(f"dry run requested {request.full_url}")
        endpoint = parts.path.split("/api.json/0.2/", 1)[1]
        self.endpoints.append(endpoint)
        assert endpoint in self.ALLOWED, endpoint
        params = {key: values[0] for key, values in parse_qs(parts.query).items()}
        return _Response(json.dumps(self._payload(endpoint, params)).encode())

    def _payload(self, endpoint, params):
        if endpoint == "user/login":
            return {
                "user": {"credential": {"parameters": {"short_label": "Studio"}}},
                "user_auth_token": "token",
            }
        if endpoint == "track/getFileUrl":
            return _track_url(params["track_id"])
        if endpoint == "track/get":
            return self.tracks[params["track_id"]]
        if endpoint == "album/get":
            return {
                "id": "alb1",
                "streamable": True,
                "release_type": "album",
                "title": "Record",
                "artist": {"name": "Artist"},
                "release_date_original": "2024-01-02",
                "image": {"large": "https://images.example.test/cover.jpg"},
                "tracks": {"items": [self.tracks["t1"], self.tracks["t2"]]},
            }
        if endpoint == "playlist/get":
            return {
                "name": "Parity",
                "tracks_count": 3,
                "tracks": {
                    "items": [self.tracks["t1"], self.tracks["t2"], self.tracks["t1"]]
                },
            }
        if endpoint == "track/search":
            return {"tracks": {"items": [self.tracks["t9"]]}}
        pytest.fail(endpoint)


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        body, self.body = self.body, b""
        return body


def _snapshot(root):
    state = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        content = path.read_bytes() if path.is_file() else None
        state[str(path.relative_to(root))] = (stat.S_IMODE(info.st_mode), content)
    return state


@pytest.fixture
def dry_run_world(monkeypatch, tmp_path):
    config_file, database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    if os.name == "posix":
        # Loose modes that a real run would repair; a dry run must leave them.
        config_file.chmod(0o644)
        config_file.parent.chmod(0o755)
    music = tmp_path / "Music"
    existing = music / "Artist - Record" / "01. One.flac"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"already here")
    playlist_m3u = music / "Parity" / "Parity.m3u"
    playlist_m3u.parent.mkdir(parents=True)
    playlist_m3u.write_text("#EXTM3U\n")
    api = FakeQobuzApi()
    monkeypatch.setattr(http, "urlopen", api.urlopen)
    monkeypatch.setattr(
        downloader,
        "download_with_progress",
        lambda *args, **kwargs: pytest.fail("a dry run transferred media"),
    )
    return tmp_path, database, api, existing


def test_dry_run_writes_nothing_and_uses_only_read_only_endpoints(
    dry_run_world, capsys
):
    root, database, api, existing = dry_run_world
    before = _snapshot(root)

    code, document, error = _json_run(
        ["dl", ALBUM, PLAYLIST, LASTFM, "--dry-run", "--json"], capsys
    )

    assert (code, error) == (0, "")
    assert _snapshot(root) == before
    assert not database.exists()
    assert set(api.endpoints) <= FakeQobuzApi.ALLOWED | {"last.fm"}
    assert {"user/login", "album/get", "playlist/get", "track/search"} <= set(
        api.endpoints
    )
    assert document["data"]["dry_run"] is True
    planned = [
        (item["source"], item["item_id"], item["paths"][0], item["exists"])
        for item in document["data"]["items"]
    ]
    music = root / "Music"
    assert planned == [
        (ALBUM, "t1", str(existing), True),
        (ALBUM, "t2", str(music / "Artist - Record" / "02. Two.flac"), False),
        (
            PLAYLIST,
            "t1",
            str(music / "Parity" / "Artist - Singles" / "01. One.flac"),
            False,
        ),
        (
            PLAYLIST,
            "t2",
            str(music / "Parity" / "Artist - Singles" / "02. Two.flac"),
            False,
        ),
        (
            PLAYLIST,
            "t1",
            str(music / "Parity" / "Artist - Singles" / "01. One.flac"),
            False,
        ),
        (
            LASTFM,
            "t9",
            str(music / "My Lastfm Playlist" / "Artist - Singles" / "03. Nine.flac"),
            False,
        ),
        (
            LASTFM,
            "t9",
            str(music / "My Lastfm Playlist" / "Artist - Singles" / "03. Nine.flac"),
            False,
        ),
    ]
    assert {item["state"] for item in document["data"]["items"]} == {"planned"}


def test_plain_dry_run_prints_candidate_paths_once(dry_run_world, capsys):
    root, _database, _api, existing = dry_run_world
    before = _snapshot(root)

    assert cli.main(["dl", ALBUM, PLAYLIST, "-n"]) == 0

    output = capsys.readouterr()
    music = root / "Music"
    assert output.out.splitlines() == [
        str(existing),
        str(music / "Artist - Record" / "02. Two.flac"),
        str(music / "Parity" / "Artist - Singles" / "01. One.flac"),
        str(music / "Parity" / "Artist - Singles" / "02. Two.flac"),
    ]
    assert output.err == ""
    assert _snapshot(root) == before


def test_json_sources_are_redacted(monkeypatch, tmp_path, capsys):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    secret_url = f"{URL}?user_auth_token=SECRET_SENTINEL"
    monkeypatch.setattr(
        cli,
        "QobuzDL",
        _scripted(
            [
                RunItem(
                    secret_url, "track", "1", DownloadResult("failed", "path_conflict")
                ),
                RunProblem("no_tracks", "empty", secret_url),
            ]
        ),
    )

    _code, document, error = _json_run(["dl", secret_url, "--json"], capsys)

    serialized = json.dumps(document)
    assert "SECRET_SENTINEL" not in serialized + error
    assert document["data"]["items"][0]["source"] == f"{URL}?user_auth_token=<redacted>"


def test_json_stays_one_writable_object_on_an_ascii_stdout(monkeypatch, tmp_path):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    monkeypatch.setattr(
        cli,
        "QobuzDL",
        _scripted([_item("finalized", "downloaded", ["Música/01. Canción.flac"])]),
    )
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="ascii"))

    assert cli.main(["dl", URL, "--json"]) == 0

    sys.stdout.flush()
    document = json.loads(raw.getvalue().decode("ascii"))
    assert document["data"]["items"][0]["paths"] == ["Música/01. Canción.flac"]


@pytest.mark.parametrize("failure", ["temporary", "unexpected"])
def test_json_stdout_is_identical_at_every_verbosity(
    monkeypatch, tmp_path, capsys, failure
):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)
    if failure == "temporary":
        runtime = _scripted([RunProblem("rate_limited", "limit", URL, retryable=True)])
    else:
        runtime = _scripted([RuntimeError("unexpected state")])
    monkeypatch.setattr(cli, "QobuzDL", runtime)

    outputs = set()
    for flags in ([], ["-v"], ["--debug"], ["-v", "--no-color"]):
        code, document, _error = _json_run(["dl", URL, "--json", *flags], capsys)
        outputs.add((code, json.dumps(document, sort_keys=True)))

    assert len(outputs) == 1
    ((code, serialized),) = outputs
    hint = json.loads(serialized)["problems"][-1]["hint"]
    if failure == "temporary":
        assert (code, hint) == (75, f"qobuz-dl dl {URL} --json")
    else:
        assert (code, hint) == (1, f"qobuz-dl --debug dl {URL} --json")


@pytest.mark.parametrize(
    "argv",
    [
        ["lucky", "-vn", "3", "query"],
        ["lucky", "-vn3", "query"],
        ["lucky", "query", "-en", "2"],
    ],
)
def test_clustered_old_count_flag_is_rejected(monkeypatch, capsys, argv):
    monkeypatch.setattr(
        cli, "_resolve_config_paths", lambda: pytest.fail("reached config")
    )

    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 2
    assert "-n now means --dry-run; use --limit N" in capsys.readouterr().err


def test_clusters_with_n_as_dry_run_still_parse():
    from qobuz_dl.commands import qobuz_dl_args

    parser = qobuz_dl_args()

    arguments = parser.parse_args(["-vn", "dl", URL])
    assert (arguments.verbose, arguments.dry_run) == (True, True)
    arguments = parser.parse_args(["lucky", "3", "feet", "-vn"])
    assert (arguments.dry_run, arguments.QUERY) == (True, ["3", "feet"])


def test_dry_run_failure_summary_says_would(monkeypatch, tmp_path, capsys):
    config_file, _database = _paths(monkeypatch, tmp_path)
    _write_config(config_file)

    class Previewing:
        def __init__(self, *args, **kwargs):
            pass

        def initialize_client(self, *args):
            pass

        def preview_sources(self, sources):
            self.run_result.add_item(_item("ignored", "demo"))
            return self.run_result

    monkeypatch.setattr(cli, "QobuzDL", Previewing)

    assert cli.main(["dl", URL, "--dry-run"]) == 1

    assert capsys.readouterr().err == (
        "qobuz-dl: 1 of 1 items would not be downloaded: demo\n"
        f"see why: qobuz-dl --verbose dl {URL} --dry-run\n"
    )
