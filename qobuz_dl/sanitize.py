import hashlib
import os
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
_RESERVED_FIRST_STEMS = _RESERVED_NAMES | {
    *(f"COM{suffix}" for suffix in "¹²³"),
    *(f"LPT{suffix}" for suffix in "¹²³"),
}
_FILENAME_DIGEST_DOMAIN = b"qobuz-dl:filename:v1\0"


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


def filename_component(raw: str, extension: str, max_bytes: int) -> str:
    """Build one complete audio filename that fits a component byte limit."""
    sanitized = sanitize_filename(raw)
    complete_name = f"{sanitized}{extension}"
    if (
        sanitized
        and not _has_reserved_first_stem(sanitized)
        and len(os.fsencode(complete_name)) <= max_bytes
    ):
        return complete_name

    digest = hashlib.sha256(_FILENAME_DIGEST_DOMAIN + raw.encode("utf-8")).hexdigest()[
        :32
    ]
    fallback = f"track-{digest}{extension}"
    fallback_bytes = len(os.fsencode(fallback))
    if fallback_bytes > max_bytes:
        raise ValueError(
            f"filename component limit of {max_bytes} bytes cannot fit "
            f"the required {fallback_bytes}-byte fallback"
        )

    if not sanitized or _has_reserved_first_stem(sanitized):
        return fallback

    suffix = f"~{digest}{extension}"
    prefix = _fit_prefix(sanitized, max_bytes - len(os.fsencode(suffix)))
    candidate = f"{prefix}{suffix}"
    return fallback if _has_reserved_first_stem(candidate) else candidate


def _has_reserved_first_stem(value: str) -> bool:
    return value.partition(".")[0].rstrip(" ").upper() in _RESERVED_FIRST_STEMS


def _fit_prefix(value: str, max_bytes: int) -> str:
    fitted = []
    fitted_bytes = 0
    for character in value:
        character_bytes = len(os.fsencode(character))
        if fitted_bytes + character_bytes > max_bytes:
            break
        fitted.append(character)
        fitted_bytes += character_bytes
    return "".join(fitted)
