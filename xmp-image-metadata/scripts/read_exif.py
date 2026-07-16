#!/usr/bin/env python3
"""Harvest EXIF metadata into a spec-shaped JSON fragment of CANDIDATE facts.

  python3 read_exif.py --image DSCF1234.jpg
  python3 read_exif.py --image photo.jpg --merge base_spec.json > enriched_spec.json

Output keys line up with build_xmp.py's spec: width, height, format, date_created,
gps{lat,lon,alt}, camera{make,model,lens}, exposure{...}, orientation, color_space.
Every value is untrusted and possibly stale or forged: review before use. --merge
fills only missing fields and is not verification.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402  (local sibling module)

TAGS = [
    "-EXIF:Make",
    "-EXIF:Model",
    "-EXIF:LensModel",
    "-EXIF:LensInfo",
    "-EXIF:LensMake",
    "-EXIF:ExposureTime",
    "-EXIF:FNumber",
    "-EXIF:ISO",
    "-EXIF:FocalLength",
    "-EXIF:FocalLengthIn35mmFormat",
    "-EXIF:ExposureProgram",
    "-EXIF:MeteringMode",
    "-EXIF:Flash",
    "-EXIF:Orientation",
    "-EXIF:ColorSpace",
    "-EXIF:DateTimeOriginal",
    "-EXIF:CreateDate",
    "-EXIF:ModifyDate",
    "-Composite:GPSLatitude",
    "-Composite:GPSLongitude",
    "-EXIF:GPSAltitude",
    "-File:ImageWidth",
    "-File:ImageHeight",
    "-File:MIMEType",
    "-EXIF:Software",
]


def harvest(cmd: list[str], image: str) -> dict[str, Any]:
    proc = subprocess.run(
        [*cmd, "-j", "-n", "-G0", *TAGS, _common.safe_arg(image)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    data: dict[str, Any] = (
        json.loads(proc.stdout)[0] if proc.stdout.strip().startswith("[") else {}
    )

    def g(*names: str) -> Any:
        for name in names:
            for key, value in data.items():
                if key.split(":")[-1] == name and value not in (None, ""):
                    return value
        return None

    out: dict[str, Any] = {}
    width, height = g("ImageWidth"), g("ImageHeight")
    if width:
        out["width"] = int(width)
    if height:
        out["height"] = int(height)
    mime = g("MIMEType")
    if mime:
        out["format"] = mime
    dto = g("DateTimeOriginal") or g("CreateDate")
    if dto:
        out["date_created"] = str(dto)[:10].replace(":", "-")
    lat, lon, alt = g("GPSLatitude"), g("GPSLongitude"), g("GPSAltitude")
    if lat is not None and lon is not None:
        out["gps"] = {"lat": round(float(lat), 7), "lon": round(float(lon), 7)}
        if alt is not None:
            out["gps"]["alt"] = float(alt)
    cam: dict[str, Any] = {}
    if g("Make"):
        cam["make"] = g("Make")
    if g("Model"):
        cam["model"] = g("Model")
    if g("LensModel"):
        cam["lens"] = g("LensModel")
    if cam:
        out["camera"] = cam
    exp: dict[str, Any] = {}
    for key, tag in [
        ("exposure_time", "ExposureTime"),
        ("f_number", "FNumber"),
        ("iso", "ISO"),
        ("focal_length", "FocalLength"),
        ("focal_length_35mm", "FocalLengthIn35mmFormat"),
    ]:
        value = g(tag)
        if value is not None:
            exp[key] = value
    if exp:
        out["exposure"] = exp
    if g("Orientation") is not None:
        out["orientation"] = g("Orientation")
    if g("ColorSpace") is not None:
        out["color_space"] = g("ColorSpace")
    if g("Software"):
        out["software"] = g("Software")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Harvest untrusted EXIF candidates into a spec fragment."
    )
    ap.add_argument("--image", required=True)
    ap.add_argument(
        "--merge",
        help="Merge harvested fields into this base spec JSON (fills gaps only).",
    )
    a = ap.parse_args()
    cmd = _common.find_exiftool()
    if not cmd:
        sys.exit("ERROR: ExifTool not found (set ET_EXIFTOOL or install it).")
    if not os.path.isfile(a.image):
        sys.exit(f"ERROR: image not found: {a.image}")
    frag = harvest(cmd, a.image)
    if a.merge:
        with open(a.merge, encoding="utf-8") as handle:
            base = json.load(handle)
        for key, value in frag.items():
            base.setdefault(key, value)
        print(json.dumps(base, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(frag, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
