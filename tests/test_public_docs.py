import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
