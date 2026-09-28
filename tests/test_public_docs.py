import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACCESS_DECISION = Path("docs/qobuz-access.md")
MAINTAINED_PUBLIC_DOCS = (
    Path("README.md"),
    Path("docs/installation.md"),
    Path("docs/examples.md"),
    Path("docs/cli.md"),
    Path("docs/use-cases.md"),
)
BARE_PUBLIC_COMMANDS = (
    re.compile(r"\buvx\s+(?:qobuz-dl|qdl)(?=$|[^\w-])"),
    re.compile(r"\buv\s+tool\s+install\s+qobuz-dl(?=$|[^\w-])"),
)
EXPLANATORY_WARNING = re.compile(
    r"(?:\b(?:avoid|do not use|don't use|never use|instead of)\s+[`'\"]?"
    r"(?:uvx\s+(?:qobuz-dl|qdl)|uv\s+tool\s+install\s+qobuz-dl)"
    r"|\b(?:uvx\s+(?:qobuz-dl|qdl)|uv\s+tool\s+install\s+qobuz-dl)"
    r".{0,80}\b(?:ambiguous|not recommended|unqualified)\b)",
    re.IGNORECASE,
)


def test_public_docs_do_not_recommend_bare_install_commands():
    failures = []

    for relative_path in MAINTAINED_PUBLIC_DOCS:
        text = (PROJECT_ROOT / relative_path).read_text()
        for line_number, line in enumerate(text.splitlines(), start=1):
            if EXPLANATORY_WARNING.search(line):
                continue
            if any(pattern.search(line) for pattern in BARE_PUBLIC_COMMANDS):
                failures.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert not failures, "Actionable bare public commands:\n" + "\n".join(failures)


def test_public_maturity_and_access_decision_do_not_drift():
    package_metadata = (PROJECT_ROOT / "pyproject.toml").read_text()
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text()
    access_decision = (PROJECT_ROOT / ACCESS_DECISION).read_text()

    assert "Development Status :: 4 - Beta" in package_metadata
    assert "Development Status :: 5 - Production/Stable" not in package_metadata
    assert "production-ready" not in changelog.lower()

    required_access_statements = (
        "unofficial",
        "not affiliated with or certified by Qobuz",
        "public web bundle",
        "may break",
        "eligible Qobuz account and subscription",
        "do not establish current Qobuz approval, a current contract, or legal compliance",
        "effective 1 September 2011",
        "revised 15 January 2014",
        "accessed 12 September 2026",
        "exposes no revision date",
        "developer.qobuz.com",
        "Current source and offline tests",
    )
    for statement in required_access_statements:
        assert statement in access_decision


def test_current_public_docs_link_to_access_decision():
    for relative_path in (
        Path("README.md"),
        Path("docs/INDEX.md"),
        Path("docs/use-cases.md"),
    ):
        text = (PROJECT_ROOT / relative_path).read_text()
        assert "qobuz-access.md" in text


# Forms the CLI contract removed (issue #90). A maintained doc may explain
# them in prose, but no command it shows may use them.
DOCS_WITH_COMMANDS = (
    *MAINTAINED_PUBLIC_DOCS,
    Path("docs/testing.md"),
    Path("docs/development.md"),
    Path("docs/module-usage.md"),
)
COMMAND_LINE = re.compile(r"\b(?:qobuz-dl|qdl|live-qobuz)\b")
REMOVED_IN_COMMANDS = (
    ("-sc", re.compile(r"(?<![\w-])-sc(?![\w-])")),
    ("-ff", re.compile(r"(?<![\w-])-ff(?![\w-])")),
    ("-tf", re.compile(r"(?<![\w-])-tf(?![\w-])")),
    ("lucky -n COUNT", re.compile(r"\blucky\b.*(?<![\w-])-n\s*[0-9]")),
    ("--number", re.compile(r"(?<![\w-])--number\b")),
)
# Setting the retired password variable, as opposed to explaining it.
RETIRED_PASSWORD_USE = re.compile(
    r"(?:\bexport\b.*|\bread\b.*\s)QOBUZ_DL_LIVE_PASSWORD\b(?!_FILE)"
    r"|QOBUZ_DL_LIVE_PASSWORD="
)
REMOVED_TOKENS = re.compile(r"`(?:-sc|-ff|-tf)`")


def _removed_forms(line):
    found = []
    if COMMAND_LINE.search(line):
        found = [name for name, pattern in REMOVED_IN_COMMANDS if pattern.search(line)]
    if RETIRED_PASSWORD_USE.search(line):
        found.append("QOBUZ_DL_LIVE_PASSWORD")
    return found


def test_removed_forms_are_detected():
    assert _removed_forms("qobuz-dl -sc") == ["-sc"]
    assert _removed_forms("qobuz-dl dl URL -ff '{album}'") == ["-ff"]
    assert _removed_forms("qobuz-dl lucky -n 3 query") == ["lucky -n COUNT"]
    assert _removed_forms("qobuz-dl lucky query --number 2") == ["--number"]
    assert _removed_forms("export QOBUZ_DL_LIVE_PASSWORD") == ["QOBUZ_DL_LIVE_PASSWORD"]
    assert _removed_forms("qobuz-dl lucky query -n") == []
    assert _removed_forms("qobuz-dl fun -l 10") == []
    assert _removed_forms("export QOBUZ_DL_LIVE_PASSWORD_FILE=/tmp/p") == []
    assert _removed_forms("read -r -s QOBUZ_DL_LIVE_PASSWORD </dev/tty") == [
        "QOBUZ_DL_LIVE_PASSWORD"
    ]
    assert _removed_forms("The verifier no longer reads `QOBUZ_DL_LIVE_PASSWORD`") == []
    assert REMOVED_TOKENS.search("| `-sc`, `--show-config` |")


def test_maintained_docs_show_no_removed_flags():
    failures = []

    for relative_path in DOCS_WITH_COMMANDS:
        text = (PROJECT_ROOT / relative_path).read_text()
        for line_number, line in enumerate(text.splitlines(), start=1):
            removed = _removed_forms(line)
            if REMOVED_TOKENS.search(line):
                removed.append("short option token")
            if removed:
                failures.append(
                    f"{relative_path}:{line_number}: {', '.join(removed)}: "
                    f"{line.strip()}"
                )

    assert not failures, "Removed CLI forms in maintained docs:\n" + "\n".join(failures)
