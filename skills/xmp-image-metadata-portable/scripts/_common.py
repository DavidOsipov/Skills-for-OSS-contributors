"""Shared helpers for the image-metadata scripts.

Centralises ExifTool discovery, version parsing, argument-injection-safe path
handling, and XML-safe escaping so every script behaves identically (DRY) and
inherits the same hardening.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from xml.sax.saxutils import escape as _xml_escape

MIN_VERSION = 12.46  # first ExifTool release with WebP write support
REC_VERSION = 13.00  # reliable AVIF/HEIC writing

# XML 1.0 allows only tab, LF, CR and the Unicode ranges below. Any other
# character (NUL, bell, vertical tab, ...) makes the document ill-formed and is
# stripped before escaping.
_ILLEGAL_XML = re.compile(
    "[^\u0009\u000a\u000d\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]"
)


def find_exiftool() -> list[str] | None:
    """Return a command prefix for invoking ExifTool, or None if unavailable.

    Resolution order: ``$ET_EXIFTOOL``, then ``PATH``, then a copy bundled next
    to the scripts (``./exiftool`` or ``./exiftool-git/exiftool``).
    """
    env = os.environ.get("ET_EXIFTOOL")
    if env and os.path.exists(env):
        return [env] if os.access(env, os.X_OK) else ["perl", env]
    exe = shutil.which("exiftool")
    if exe:
        return [exe]
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        os.path.join(here, "exiftool"),
        os.path.join(here, "exiftool-git", "exiftool"),
    ):
        if os.path.exists(cand):
            return ["perl", cand]
    return None


def exiftool_version(cmd: list[str]) -> float | None:
    """Return ExifTool major.minor as a float, robust to patch suffixes."""
    try:
        proc = subprocess.run(
            [*cmd, "-ver"], capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.match(r"(\d+)\.(\d+)", proc.stdout.strip())
    return float(f"{match.group(1)}.{match.group(2)}") if match else None


def safe_arg(path: str) -> str:
    """Return an absolute path safe to pass as a positional ExifTool argument.

    Absolute paths never begin with a dash, which prevents a crafted filename
    (e.g. -delete_original) from being parsed as an ExifTool option
    (argument injection).
    """
    return os.path.abspath(path)


def strip_illegal_xml(text: str) -> str:
    """Drop characters that are not permitted anywhere in XML 1.0."""
    return _ILLEGAL_XML.sub("", text)


def xml_text(value: object) -> str:
    """Escape a value for XML element text, removing XML-illegal characters."""
    return _xml_escape(strip_illegal_xml("" if value is None else str(value)))


def xml_attr(value: object) -> str:
    """Escape a value for an XML attribute (also escapes quotes)."""
    cleaned = strip_illegal_xml("" if value is None else str(value))
    return _xml_escape(cleaned, {'"': "&quot;", "'": "&apos;"})
