#!/usr/bin/env python3
"""Embed an XMP packet into an image and (by default) synchronise EXIF + IPTC-IIM.

  python3 embed_xmp.py --xmp meta.xmp --image photo.avif             # embed + sync
  python3 embed_xmp.py --xmp meta.xmp --image photo.jpg --no-sync    # embed XMP only
  python3 embed_xmp.py --check                                       # verify ExifTool
  python3 embed_xmp.py --image p.jpg --read                          # dump embedded XMP

Supported: JPEG, PNG, WebP, AVIF (+ any ExifTool-writable format). With sync,
XMP->EXIF/IPTC descriptive+rights fields and EXIF->XMP capture fields are copied so
all three metadata blocks agree. IPTC-IIM lands only in JPEG/PNG/TIFF.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402  (local sibling module)

# XMP -> EXIF/IPTC (descriptive/rights/location) and EXIF -> XMP (technical capture).
SYNC_MAP = [
    "-EXIF:Artist<XMP-dc:Creator",
    "-EXIF:Copyright<XMP-dc:Rights",
    "-EXIF:ImageDescription<XMP-dc:Description",
    "-EXIF:DateTimeOriginal<XMP-photoshop:DateCreated",
    "-EXIF:CreateDate<XMP-photoshop:DateCreated",
    "-EXIF:Software<XMP-xmp:CreatorTool",
    "-EXIF:GPSLatitude<XMP-exif:GPSLatitude",
    "-EXIF:GPSLongitude<XMP-exif:GPSLongitude",
    "-EXIF:GPSAltitude<XMP-exif:GPSAltitude",
    # ExifTool exposes XMP's exif:PixelX/YDimension as ExifImageWidth/Height.
    "-EXIF:ExifImageWidth<XMP-exif:ExifImageWidth",
    "-EXIF:ExifImageHeight<XMP-exif:ExifImageHeight",
    "-IPTC:By-line<XMP-dc:Creator",
    "-IPTC:CopyrightNotice<XMP-dc:Rights",
    "-IPTC:Caption-Abstract<XMP-dc:Description",
    "-IPTC:Keywords<XMP-dc:Subject",
    "-IPTC:Headline<XMP-photoshop:Headline",
    "-IPTC:City<XMP-photoshop:City",
    "-IPTC:Province-State<XMP-photoshop:State",
    "-IPTC:Country-PrimaryLocationName<XMP-photoshop:Country",
    "-IPTC:Country-PrimaryLocationCode<XMP-Iptc4xmpCore:CountryCode",
    "-IPTC:DateCreated<XMP-photoshop:DateCreated",
    "-XMP-tiff:Make<EXIF:Make",
    "-XMP-tiff:Model<EXIF:Model",
    "-XMP-tiff:Orientation<EXIF:Orientation",
    "-XMP-exifEX:LensModel<EXIF:LensModel",
    "-XMP-exif:ExposureTime<EXIF:ExposureTime",
    "-XMP-exif:FNumber<EXIF:FNumber",
    "-XMP-exif:ISO<EXIF:ISO",
    "-XMP-exif:FocalLength<EXIF:FocalLength",
    "-XMP-exif:FocalLengthIn35mmFormat<EXIF:FocalLengthIn35mmFormat",
    "-XMP-exif:ColorSpace<EXIF:ColorSpace",
]


def preflight(quiet: bool = False) -> list[str] | None:
    cmd = _common.find_exiftool()
    if not cmd:
        sys.stderr.write(
            "ERROR: ExifTool not found.\n"
            "  Debian/Ubuntu : sudo apt-get install libimage-exiftool-perl\n"
            "  macOS (brew)  : brew install exiftool\n"
            "  Windows       : https://exiftool.org  (or `winget install exiftool`)\n"
            "  Or set ET_EXIFTOOL=/path/to/exiftool .\n"
        )
        return None
    ver = _common.exiftool_version(cmd)
    if ver is None:
        sys.stderr.write("ERROR: found ExifTool but could not read its version.\n")
        return None
    if ver < _common.MIN_VERSION:
        sys.stderr.write(
            f"ERROR: ExifTool {ver} too old (need >= {_common.MIN_VERSION} for WebP, "
            f">= {_common.REC_VERSION} for AVIF/HEIC).\n"
        )
        return None
    if ver < _common.REC_VERSION and not quiet:
        sys.stderr.write(
            f"WARNING: ExifTool {ver} predates {_common.REC_VERSION}; AVIF/HEIC may be unreliable.\n"
        )
    if not quiet:
        print(f"ExifTool {ver} OK ({' '.join(cmd)})")
    return cmd


def read_xmp(cmd: list[str], image: str) -> str:
    proc = subprocess.run(
        [*cmd, "-xmp", "-b", _common.safe_arg(image)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.stdout


def read_tag(cmd: list[str], tag: str, image: str) -> str:
    """Read one native tag without print conversion; return empty when absent."""
    proc = subprocess.run(
        [*cmd, "-s3", f"-{tag}", _common.safe_arg(image)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return proc.stdout.strip()


def sync_exif(cmd: list[str], image: str) -> int:
    safe = _common.safe_arg(image)
    existing_version = read_tag(cmd, "EXIF:ExifVersion", image)
    exif_version = existing_version if re.fullmatch(r"\d{4}", existing_version) else "0300"
    args = [
        *cmd,
        "-m",
        "-overwrite_original",
        "-codedcharacterset=utf8",
        "-charset",
        "iptc=UTF8",
        "-tagsfromfile",
        safe,
        *SYNC_MAP,
        f"-EXIF:ExifVersion={exif_version}",
        safe,
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "ERROR: EXIF/IPTC sync failed.\n")
        return 1
    print(f"OK: EXIF/IPTC synchronised from XMP in {image}")
    return 0


def embed(
    cmd: list[str],
    xmp: str,
    image: str,
    keep_original: bool = False,
    do_sync: bool = False,
) -> int:
    if not os.path.isfile(xmp):
        sys.stderr.write(f"ERROR: XMP file not found: {xmp}\n")
        return 2
    if not os.path.isfile(image):
        sys.stderr.write(f"ERROR: image not found: {image}\n")
        return 2
    args = [*cmd, "-m", "-tagsfromfile", _common.safe_arg(xmp), "-xmp"]
    args += [] if keep_original else ["-overwrite_original"]
    args += [_common.safe_arg(image)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=300)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0 or "0 image files updated" in proc.stdout:
        sys.stderr.write(proc.stderr or "ERROR: ExifTool did not update the file.\n")
        return 1
    embedded = read_xmp(cmd, image)
    if "<x:xmpmeta" not in embedded and "<rdf:RDF" not in embedded:
        sys.stderr.write("ERROR: post-write verification found no XMP in the image.\n")
        return 1
    print(f"OK: XMP embedded into {image}")
    if do_sync:
        return sync_exif(cmd, image)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Embed XMP into an image; sync EXIF/IPTC by default."
    )
    ap.add_argument("--xmp")
    ap.add_argument("--image")
    ap.add_argument(
        "--keep-original",
        action="store_true",
        help="Keep IMAGE_original backup (default: overwrite in place).",
    )
    ap.add_argument(
        "--no-sync",
        action="store_true",
        help="Embed XMP only; skip the default EXIF + IPTC-IIM synchronisation.",
    )
    ap.add_argument(
        "--sync-exif", action="store_true", help=argparse.SUPPRESS
    )  # back-compat no-op
    ap.add_argument("--check", action="store_true")
    ap.add_argument(
        "--read", action="store_true", help="Print the XMP embedded in --image."
    )
    a = ap.parse_args()
    cmd = preflight(quiet=a.read)
    if not cmd:
        return 3
    if a.check:
        return 0
    if a.read:
        if not a.image:
            ap.error("--read requires --image")
        sys.stdout.write(read_xmp(cmd, a.image))
        return 0
    if not (a.xmp and a.image):
        ap.error("need --xmp and --image (or --check / --read)")
    return embed(cmd, a.xmp, a.image, a.keep_original, do_sync=not a.no_sync)


if __name__ == "__main__":
    sys.exit(main())
