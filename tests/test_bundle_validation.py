import base64
import configparser
import sys
import traceback

import pytest

import qobuz_dl.cli as cli
from qobuz_dl.bundle import Bundle
from qobuz_dl.exceptions import BundleError
from qobuz_dl.http import HttpStatusError

BUNDLE_URL = "https://play.qobuz.com/resources/1.2.3-a123/bundle.js"
APP_ID = "987654321"


class FakeResponse:
    def __init__(self, text="", error=None):
        self.text = text
        self.error = error

    def raise_for_status(self):
        if self.error is not None:
            raise self.error


def install_fake_http(monkeypatch, bundle_js, *, login_error=None, bundle_error=None):
    expected_urls = iter(["https://play.qobuz.com/login", BUNDLE_URL])
    responses = [
        FakeResponse(
            '<script src="/resources/1.2.3-a123/bundle.js"></script>',
            login_error,
        ),
        FakeResponse(bundle_js, bundle_error),
    ]

    class FakeHttpClient:
        def get(self, url):
            assert url == next(expected_urls)
            return responses.pop(0)

    monkeypatch.setattr("qobuz_dl.bundle.HttpClient", FakeHttpClient)


def encoded_parts(value):
    encoded = base64.standard_b64encode(value).decode("ascii") + ("A" * 44)
    return encoded[:4], encoded[4:8], encoded[8:]


def seed(timezone, value):
    return f'a.initialSeed("{value}",window.utimezone.{timezone});'


def fragments(timezone, info, extras):
    return f'name:"x/{timezone.capitalize()}",info:"{info}",extras:"{extras}";'


def credential_records(credentials):
    records = [seed(timezone, parts[0]) for timezone, parts in credentials]
    records.extend(
        fragments(timezone, parts[1], parts[2]) for timezone, parts in credentials
    )
    return records


def bundle_js(*records):
    prefix = (
        f'production:{{api:{{appId:"{APP_ID}",'
        'appSecret:"0123456789abcdef0123456789abcdef"}};'
    )
    return prefix + "".join(records)


def extract_secrets(monkeypatch, records):
    install_fake_http(monkeypatch, bundle_js(*records))
    return Bundle().get_secrets()


def assert_safe_bundle_error(exc_info, category, *private_values):
    message = str(exc_info.value)
    assert category in message.lower()
    for private_value in private_values:
        assert private_value not in message


def test_two_distinct_seeds_without_fragment_pairs_are_rejected(monkeypatch):
    america = encoded_parts(b"america-secret")
    europe = encoded_parts(b"europe-secret")

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(
            monkeypatch,
            [seed("america", america[0]), seed("europe", europe[0])],
        )

    assert_safe_bundle_error(exc_info, "incomplete", america[0], europe[0])


def test_one_incomplete_seeded_timezone_is_rejected(monkeypatch):
    america = encoded_parts(b"america-secret")
    europe = encoded_parts(b"europe-secret")
    records = [
        seed("america", america[0]),
        seed("europe", europe[0]),
        fragments("america", america[1], america[2]),
    ]

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(monkeypatch, records)

    assert_safe_bundle_error(exc_info, "incomplete", "america", "europe")


@pytest.mark.parametrize("empty_component", ["seed", "info", "extras"])
def test_empty_secret_components_are_rejected(monkeypatch, empty_component):
    america = dict(zip(("seed", "info", "extras"), encoded_parts(b"america")))
    europe = encoded_parts(b"europe")
    america[empty_component] = ""
    records = credential_records(
        [
            ("america", tuple(america.values())),
            ("europe", europe),
        ]
    )

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(monkeypatch, records)

    assert_safe_bundle_error(exc_info, "incomplete", "america", "europe")


def test_components_too_short_for_the_suffix_are_rejected(monkeypatch):
    short = ("A", "A", "A" * 42)
    europe = encoded_parts(b"europe")

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(
            monkeypatch,
            credential_records([("america", short), ("europe", europe)]),
        )

    assert_safe_bundle_error(exc_info, "encoding")


def test_invalid_standard_base64_is_rejected_without_decoder_details(monkeypatch):
    america = list(encoded_parts(b"america"))
    europe = encoded_parts(b"europe")
    america[0] = "%" + america[0][1:]

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(
            monkeypatch,
            credential_records([("america", tuple(america)), ("europe", europe)]),
        )

    assert_safe_bundle_error(exc_info, "encoding", america[0])
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    assert "binascii" not in "".join(traceback.format_exception(exc_info.value))


def test_invalid_utf8_is_rejected_without_decoder_details(monkeypatch):
    invalid_utf8 = encoded_parts(b"\xff")
    europe = encoded_parts(b"europe")

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(
            monkeypatch,
            credential_records([("america", invalid_utf8), ("europe", europe)]),
        )

    assert_safe_bundle_error(exc_info, "encoding", invalid_utf8[0])
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    assert "UnicodeDecodeError" not in "".join(
        traceback.format_exception(exc_info.value)
    )


@pytest.mark.parametrize("value", ["\U0001f600", "\u083f"])
def test_valid_standard_base64_with_plus_or_slash_is_accepted(monkeypatch, value):
    america = encoded_parts(value.encode("utf-8"))
    europe = encoded_parts(b"europe")
    encoded = "".join(america)[:-44]
    assert "+" in encoded or "/" in encoded

    secrets = extract_secrets(
        monkeypatch,
        credential_records([("america", america), ("europe", europe)]),
    )

    assert secrets == {"europe": "europe", "america": value}


def test_identical_duplicate_declarations_are_accepted(monkeypatch):
    america = encoded_parts(b"america")
    europe = encoded_parts(b"europe")
    records = [
        seed("america", america[0]),
        seed("america", america[0]),
        seed("europe", europe[0]),
        fragments("america", america[1], america[2]),
        fragments("america", america[1], america[2]),
        fragments("europe", europe[1], europe[2]),
    ]

    assert extract_secrets(monkeypatch, records) == {
        "europe": "europe",
        "america": "america",
    }


@pytest.mark.parametrize("declaration", ["seed", "fragments"])
def test_conflicting_duplicate_declarations_are_rejected(monkeypatch, declaration):
    america = encoded_parts(b"america")
    europe = encoded_parts(b"europe")
    records = credential_records([("america", america), ("europe", europe)])
    if declaration == "seed":
        records.insert(1, seed("america", "conflicting-seed-sentinel"))
    else:
        records.append(
            fragments(
                "america",
                america[1],
                "conflicting-fragment-sentinel",
            )
        )

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(monkeypatch, records)

    assert_safe_bundle_error(
        exc_info,
        "conflict",
        "america",
        "conflicting-seed-sentinel",
        "conflicting-fragment-sentinel",
    )


def test_mismatched_fragment_timezone_does_not_complete_a_seed(monkeypatch):
    america = encoded_parts(b"america")
    europe = encoded_parts(b"europe")
    records = [
        seed("america", america[0]),
        seed("europe", europe[0]),
        fragments("america", america[1], america[2]),
        fragments("asia", europe[1], europe[2]),
    ]

    with pytest.raises(BundleError) as exc_info:
        extract_secrets(monkeypatch, records)

    assert_safe_bundle_error(exc_info, "incomplete", "america", "europe", "asia")


def test_three_seed_order_starts_with_second_then_preserves_discovery(monkeypatch):
    credentials = [
        ("america", encoded_parts("\U0001f600".encode("utf-8"))),
        ("europe", encoded_parts(b"europe-secret")),
        ("asia", encoded_parts(b"asia-secret")),
    ]

    secrets = extract_secrets(monkeypatch, credential_records(credentials))

    assert list(secrets.items()) == [
        ("europe", "europe-secret"),
        ("america", "\U0001f600"),
        ("asia", "asia-secret"),
    ]


def configure_cli(monkeypatch, tmp_path, records, arguments):
    config_file = tmp_path / "qobuz-dl" / "config.ini"
    database = config_file.parent / "qobuz_dl.db"
    monkeypatch.setattr(
        cli,
        "_resolve_config_paths",
        lambda: (str(config_file), str(database)),
    )
    monkeypatch.setattr(sys, "argv", ["qobuz-dl", *arguments])
    answers = iter(["user@example.com", "My Music", "27"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "password")
    install_fake_http(monkeypatch, bundle_js(*records))

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("configuration creation must not initialize the client")

    monkeypatch.setattr(cli, "QobuzDL", UnexpectedClient)
    return config_file, database


def invalid_bundle_records(sentinel):
    america = list(encoded_parts(b"america"))
    america[0] = sentinel
    europe = encoded_parts(b"europe")
    return credential_records([("america", tuple(america)), ("europe", europe)])


def test_invalid_first_run_does_not_create_configuration(monkeypatch, tmp_path):
    records = invalid_bundle_records("invalid-first-run-sentinel")
    config_file, database = configure_cli(monkeypatch, tmp_path, records, [])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code not in (None, 0)
    assert "Unable to create configuration from the Qobuz web bundle:" in str(
        exc_info.value
    )
    assert not config_file.exists()
    assert not database.exists()


def test_invalid_reset_preserves_bytes_and_reports_safe_bundle_failure(
    monkeypatch, tmp_path, caplog
):
    sentinel = "private-bundle-sentinel"
    records = invalid_bundle_records(sentinel)
    config_file, database = configure_cli(monkeypatch, tmp_path, records, ["--reset"])
    config_file.parent.mkdir()
    config_bytes = b"# exact config bytes\n[DEFAULT]\ncustom = keep me\n"
    database_bytes = b"exact database bytes\x00\xff"
    config_file.write_bytes(config_bytes)
    database.write_bytes(database_bytes)

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    rendered = "".join(traceback.format_exception(exc_info.value))
    diagnostic = f"{exc_info.value}\n{caplog.text}\n{rendered}"
    assert exc_info.value.code not in (None, 0)
    assert "Unable to create configuration from the Qobuz web bundle:" in diagnostic
    assert "Configuration was not saved." in diagnostic
    assert "Config file updated" not in diagnostic
    assert sentinel not in diagnostic
    assert "outage" not in diagnostic.lower()
    assert "qobuz is down" not in diagnostic.lower()
    assert config_file.read_bytes() == config_bytes
    assert database.read_bytes() == database_bytes


def test_valid_bundle_persists_exact_app_id_and_ordered_secrets(monkeypatch, tmp_path):
    credentials = [
        ("america", encoded_parts("\U0001f600".encode("utf-8"))),
        ("europe", encoded_parts(b"europe-secret")),
        ("asia", encoded_parts("\u083f".encode("utf-8"))),
    ]
    config_file, _database = configure_cli(
        monkeypatch,
        tmp_path,
        credential_records(credentials),
        ["--reset"],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code in (None, 0)
    config = configparser.ConfigParser()
    config.read(config_file)
    assert config["DEFAULT"]["app_id"] == APP_ID
    assert config["DEFAULT"]["secrets"] == "europe-secret,\U0001f600,\u083f"


@pytest.mark.parametrize("stage", ["login", "bundle"])
def test_bundle_http_status_error_is_not_wrapped(monkeypatch, stage):
    error = HttpStatusError(503, b"synthetic body")
    install_fake_http(
        monkeypatch,
        "",
        login_error=error if stage == "login" else None,
        bundle_error=error if stage == "bundle" else None,
    )

    with pytest.raises(HttpStatusError) as exc_info:
        Bundle()

    assert exc_info.value is error
