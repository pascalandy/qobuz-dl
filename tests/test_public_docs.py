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
