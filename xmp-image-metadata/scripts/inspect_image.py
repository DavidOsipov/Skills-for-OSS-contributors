#!/usr/bin/env python3
"""Inspect image pixels and technical containers before writing metadata.

Required dependencies: ExifTool, Pillow, PyYAML. ImageMagick and MediaInfo are
optional cross-checkers; their absence does not block inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402  (local sibling module)

REQUIRED = ("exiftool", "pillow", "pyyaml")


def run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit {result.returncode}"
        )
    return result.stdout


def dependencies() -> dict[str, dict[str, Any]]:
    cmd = _common.find_exiftool()
    if cmd:
        try:
            version = _common.exiftool_version(cmd)
            if version is None:
                exiftool_status: dict[str, Any] = {
                    "status": "error",
                    "error": "unreadable version",
                }
            else:
                exiftool_status = {
                    "status": (
                        "available" if version >= _common.MIN_VERSION else "too_old"
                    ),
                    "version": version,
                }
        except OSError as exc:
            exiftool_status = {"status": "error", "error": str(exc)}
    else:
        exiftool_status = {"status": "missing"}
    image_magick = shutil.which("magick") or shutil.which("identify")
    return {
        "pyyaml": {
            "status": "available" if importlib.util.find_spec("yaml") else "missing"
        },
        "pillow": {
            "status": "available" if importlib.util.find_spec("PIL") else "missing"
        },
        "exiftool": exiftool_status,
        "imagemagick": {
            "status": "available" if image_magick else "missing",
            "command": image_magick,
        },
        "mediainfo": {
            "status": "available" if shutil.which("mediainfo") else "missing"
        },
    }


def ready(deps: dict[str, dict[str, Any]]) -> bool:
    """True when every REQUIRED dependency is available (optional ones ignored)."""
    return all(deps[name]["status"] == "available" for name in REQUIRED)


def file_facts(path: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": os.path.getsize(path), "sha256": digest.hexdigest()}


def pillow_facts(path: str) -> dict[str, Any]:
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 100_000_000
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            frames = getattr(image, "n_frames", 1)
            for frame in range(frames):
                image.seek(frame)
                image.load()
            info = image.info
            return {
                "status": "ok",
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "frames": frames,
                "animated": bool(getattr(image, "is_animated", False)),
                "has_transparency": "transparency" in info or "A" in image.getbands(),
                "icc_profile_bytes": len(info.get("icc_profile", b"")),
                "exif_bytes": len(info.get("exif", b"")),
            }
    except (
        Exception
    ) as exc:  # noqa: BLE001 (report any decode failure as data, never crash)
        return {"status": "error", "error": str(exc)}


def exiftool_facts(path: str) -> dict[str, Any]:
    cmd = _common.find_exiftool()
    if not cmd:
        return {"status": "unavailable"}
    tags = [
        "-File:FileType",
        "-File:MIMEType",
        "-File:ImageWidth",
        "-File:ImageHeight",
        "-File:FileSize",
        "-EXIF:Orientation",
        "-EXIF:ColorSpace",
        "-ICC_Profile:ProfileDescription",
        "-ICC_Profile:ProfileVersion",
    ]
    try:
        output = run([*cmd, "-j", "-n", "-G1", *tags, path])
        return {"status": "ok", "tags": json.loads(output)[0]}
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, IndexError) as exc:
        return {"status": "error", "error": str(exc)}


def imagemagick_facts(path: str) -> dict[str, Any]:
    magick = shutil.which("magick")
    identify = shutil.which("identify")
    command = ["magick", "identify"] if magick else (["identify"] if identify else None)
    if not command:
        return {"status": "unavailable"}
    try:
        fmt = "%m\t%w\t%h\t%z\t%[colorspace]\t%[channels]\t%[opaque]\t%n\n"
        rows = run([*command, "+ping", "-format", fmt, path]).splitlines()
        fields = [
            "format",
            "width",
            "height",
            "depth",
            "colorspace",
            "channels",
            "opaque",
            "frame_count",
        ]
        first = dict(zip(fields, rows[0].split("\t"))) if rows else {}
        return {
            "status": "ok",
            "reader": command[0],
            "first_frame": first,
            "reported_frames": len(rows),
        }
    except (OSError, RuntimeError) as exc:
        return {"status": "error", "error": str(exc)}


def mediainfo_facts(path: str) -> dict[str, Any]:
    exe = shutil.which("mediainfo")
    if not exe:
        return {"status": "unavailable"}
    wanted = {
        "@type",
        "Format",
        "Format_Profile",
        "Width",
        "Height",
        "BitDepth",
        "ColorSpace",
        "ChromaSubsampling",
        "FileSize",
        "StreamSize",
        "Encoded_Date",
        "Tagged_Date",
    }
    try:
        tracks = json.loads(run([exe, "--Output=JSON", path]))["media"].get("track", [])
        return {
            "status": "ok",
            "tracks": [{k: v for k, v in t.items() if k in wanted} for t in tracks],
        }
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, KeyError) as exc:
        return {"status": "error", "error": str(exc)}


def dimensions(report: dict[str, Any]) -> dict[str, tuple[int, int]]:
    values: dict[str, tuple[int, int]] = {}
    pixel = report["pixel_decode"]
    if pixel.get("status") == "ok":
        values["Pillow"] = (pixel["width"], pixel["height"])
    tags = report["exiftool"].get("tags", {})
    width = tags.get("[File] ImageWidth", tags.get("File:ImageWidth"))
    height = tags.get("[File] ImageHeight", tags.get("File:ImageHeight"))
    if width is not None and height is not None:
        values["ExifTool"] = (int(width), int(height))
    magick = report["imagemagick"].get("first_frame", {})
    if magick.get("width") and magick.get("height"):
        values["ImageMagick"] = (int(magick["width"]), int(magick["height"]))
    return values


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cross-check image pixels and technical containers before metadata work."
    )
    ap.add_argument("--image")
    ap.add_argument("--out", help="Write JSON report to this file instead of stdout.")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Report dependency status; exit non-zero if a REQUIRED one is missing.",
    )
    args = ap.parse_args()
    deps = dependencies()
    if args.check:
        sys.stdout.write(
            json.dumps({"dependencies": deps, "ready": ready(deps)}, indent=2) + "\n"
        )
        return 0 if ready(deps) else 3
    if not ready(deps):
        missing = ", ".join(
            name for name in REQUIRED if deps[name]["status"] != "available"
        )
        sys.stderr.write(
            f"ERROR: required inspection dependencies unavailable: {missing}. Run --check.\n"
        )
        return 3
    if not args.image:
        ap.error("--image is required unless --check is used")
    if not os.path.isfile(args.image):
        ap.error(f"image not found: {args.image}")

    image = _common.safe_arg(args.image)
    report: dict[str, Any] = {
        "schema_version": 1,
        "image": image,
        "file": file_facts(image),
        "pixel_decode": pillow_facts(image),
        "exiftool": exiftool_facts(image),
        "imagemagick": imagemagick_facts(image),
        "mediainfo": mediainfo_facts(image),
    }
    checked = dimensions(report)
    report["cross_checks"] = {
        "dimensions": checked,
        "consistent": len(set(checked.values())) <= 1,
        "note": "Internal consistency is not proof of capture date, location, creator, or authenticity.",
    }
    if report["pixel_decode"].get("status") != "ok":
        report["cross_checks"][
            "warning"
        ] = "Pillow could not fully verify and decode the image. Do not modify it until investigated."
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as file:
            file.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
