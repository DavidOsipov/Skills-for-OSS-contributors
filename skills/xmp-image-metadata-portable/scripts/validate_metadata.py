#!/usr/bin/env python3
"""Validate an image or XMP sidecar with ExifTool.

This is intentionally an ExifTool wrapper. It does not attempt to reimplement
JPEG/PNG/WebP/HEIF/TIFF validation or an XMP schema validator. A validation
warning is reported as a failure so the caller reviews it before publishing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402  (local sibling module)


def values(record: dict[str, Any], suffix: str) -> list[str]:
    found: list[str] = []
    for key, value in record.items():
        if key.split()[-1].rstrip(":") == suffix or key.split(":")[-1] == suffix:
            raw: Iterable[Any] = value if isinstance(value, list) else [value]
            found.extend(str(item) for item in raw if item not in (None, ""))
    return found


def validate(cmd: list[str], path: str) -> dict[str, Any]:
    safe = _common.safe_arg(path)
    proc = subprocess.run(
        [*cmd, "-validate", "-warning", "-error", "-j", "-G1", "-struct", safe],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    record: dict[str, Any] = {}
    parse_error = ""
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                record = payload[0]
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    warnings = values(record, "Warning")
    errors = values(record, "Error")
    validation = values(record, "Validate")
    status = validation[0] if validation else "unreadable"
    result: dict[str, Any] = {
        "file": safe,
        "validate": status,
        "warnings": warnings,
        "errors": errors,
        "exiftool_exit_code": proc.returncode,
        "valid": proc.returncode == 0 and status == "OK" and not warnings and not errors,
    }
    if parse_error:
        result["parse_error"] = parse_error
        result["valid"] = False
    if proc.stderr.strip():
        result["stderr"] = proc.stderr.strip()
    try:
        xmp = subprocess.run(
            [*cmd, "-xmp", "-b", safe],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        result["has_xmp"] = "<x:xmpmeta" in xmp.stdout or "<rdf:RDF" in xmp.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        result["has_xmp"] = False
        result["xmp_read_error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an image or XMP sidecar through ExifTool."
    )
    parser.add_argument("--image", help="Image file to validate.")
    parser.add_argument("--xmp", help="XMP sidecar to validate instead of an image.")
    parser.add_argument("--out", help="Write the JSON report here instead of stdout.")
    parser.add_argument(
        "--require-xmp",
        action="store_true",
        help="Fail unless an image contains an XMP packet.",
    )
    parser.add_argument("--check", action="store_true", help="Check ExifTool only.")
    args = parser.parse_args()
    if args.image and args.xmp:
        parser.error("use only one of --image or --xmp")

    cmd = _common.find_exiftool()
    if not cmd:
        sys.stderr.write("ERROR: ExifTool not found (set ET_EXIFTOOL or install it).\n")
        return 3
    version = _common.exiftool_version(cmd)
    if version is None or version < _common.MIN_VERSION:
        sys.stderr.write(
            f"ERROR: ExifTool {version or 'unreadable'} is below the required "
            f"minimum {_common.MIN_VERSION}.\n"
        )
        return 3
    if args.check:
        print(json.dumps({"exiftool": " ".join(cmd), "version": version, "ready": True}, indent=2))
        return 0

    target = args.image or args.xmp
    if not target:
        parser.error("--image or --xmp is required unless --check is used")
    if not os.path.isfile(target):
        parser.error(f"file not found: {target}")

    report = validate(cmd, target)
    report["exiftool"] = {"command": cmd, "version": version}
    if args.require_xmp and not report.get("has_xmp"):
        report["valid"] = False
        report.setdefault("errors", []).append("required XMP packet not found")
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
