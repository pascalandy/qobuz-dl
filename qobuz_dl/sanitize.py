import re

_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
_CONTROL_CHARS = {chr(i) for i in range(32)}
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(value) -> str:
    """Return a conservative filename-safe string for qobuz-dl output names.

    This intentionally implements only the behavior qobuz-dl relies on: strip
    platform-problematic characters, control characters, surrounding whitespace,
    trailing dots/spaces, and Windows reserved device names.
    """
    if value is None:
        value = ""
    text = str(value)
    sanitized = "".join(
        char
        for char in text
        if char not in _INVALID_FILENAME_CHARS and char not in _CONTROL_CHARS
    )
    sanitized = sanitized.strip().rstrip(". ")
    sanitized = re.sub(r"\s+", " ", sanitized)
    if sanitized.upper() in _RESERVED_NAMES:
        return ""
    return sanitized


def sanitize_filepath(value) -> str:
    """Sanitize a generated relative path without introducing new directories."""
    return sanitize_filename(value)
