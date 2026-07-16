#!/usr/bin/env python3
"""
embed_xmp.py - Embed an XMP metadata packet into an image, and (optionally)
synchronise the key fields into the legacy EXIF and IPTC-IIM blocks so all three
metadata containers agree.

Supported formats: JPEG, PNG, WebP, AVIF (+ any ExifTool-writable format).

  # Embed XMP AND sync consistent EXIF/IPTC (this is the default):
  python3 embed_xmp.py --xmp meta.xmp --image photo.avif

  # Embed XMP only, no EXIF/IPTC sync:
  python3 embed_xmp.py --xmp meta.xmp --image photo.jpg --no-sync

  python3 embed_xmp.py --check                 # verify ExifTool
  python3 embed_xmp.py --image p.jpg --read    # dump embedded XMP

By default (unless --no-sync), after the XMP is embedded the skill copies:
  * XMP -> EXIF   : Artist, Copyright, ImageDescription, DateTimeOriginal/CreateDate,
                    Software, GPS.
  * XMP -> IPTC   : By-line, CopyrightNotice, Caption, Keywords, City/State/Country,
                    Headline, DateCreated  (written UTF-8; IPTC-IIM only lands in
                    JPEG/PNG/TIFF — silently skipped for WebP/AVIF, which keep XMP+EXIF).
  * EXIF -> XMP   : Make, Model, LensModel, ExposureTime, FNumber, ISO, FocalLength,
                    ColorSpace  (mirrors real capture data into XMP if the source has it).
Missing source tags are simply skipped.
"""
import argparse, os, shutil, subprocess, sys

MIN_VERSION = 12.46
REC_VERSION = 13.00

# XMP -> EXIF/IPTC (descriptive/rights/location) and EXIF -> XMP (technical capture)
SYNC_MAP = [
    # --- XMP -> EXIF ---
    "-EXIF:Artist<XMP-dc:Creator",
    "-EXIF:Copyright<XMP-dc:Rights",
    "-EXIF:ImageDescription<XMP-dc:Description",
    "-EXIF:DateTimeOriginal<XMP-photoshop:DateCreated",
    "-EXIF:CreateDate<XMP-photoshop:DateCreated",
    "-EXIF:Software<XMP-xmp:CreatorTool",
    "-EXIF:GPSLatitude<XMP-exif:GPSLatitude",
    "-EXIF:GPSLongitude<XMP-exif:GPSLongitude",
    "-EXIF:GPSAltitude<XMP-exif:GPSAltitude",
    # --- XMP -> IPTC-IIM ---
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
    # --- EXIF -> XMP (mirror capture data; only if present in source) ---
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

def find_exiftool():
    env = os.environ.get("ET_EXIFTOOL")
    if env and os.path.exists(env):
        return [env] if os.access(env, os.X_OK) else ["perl", env]
    exe = shutil.which("exiftool")
    if exe:
        return [exe]
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "exiftool"), os.path.join(here, "exiftool-git", "exiftool")):
        if os.path.exists(cand):
            return ["perl", cand]
    return None

def exiftool_version(cmd):
    try:
        out = subprocess.run(cmd + ["-ver"], capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return None

def preflight(quiet=False):
    cmd = find_exiftool()
    if not cmd:
        sys.stderr.write(
            "ERROR: ExifTool not found.\n"
            "  Debian/Ubuntu : sudo apt-get install libimage-exiftool-perl\n"
            "  macOS (brew)  : brew install exiftool\n"
            "  Windows       : https://exiftool.org  (or `winget install exiftool`)\n"
            "  Or set ET_EXIFTOOL=/path/to/exiftool .\n")
        return None
    ver = exiftool_version(cmd)
    if ver is None:
        sys.stderr.write("ERROR: found ExifTool but could not read its version.\n"); return None
    if ver < MIN_VERSION:
        sys.stderr.write(f"ERROR: ExifTool {ver} too old (need >= {MIN_VERSION} for WebP, "
                         f">= {REC_VERSION} for AVIF/HEIC).\n"); return None
    if ver < REC_VERSION and not quiet:
        sys.stderr.write(f"WARNING: ExifTool {ver} predates {REC_VERSION}; AVIF/HEIC may be unreliable.\n")
    if not quiet:
        print(f"ExifTool {ver} OK ({' '.join(cmd)})")
    return cmd

def read_xmp(cmd, image):
    return subprocess.run(cmd + ["-xmp", "-b", image], capture_output=True, text=True).stdout

def sync_exif(cmd, image):
    args = cmd + ["-m", "-overwrite_original", "-codedcharacterset=utf8",
                  "-charset", "iptc=UTF8", "-tagsfromfile", image] + SYNC_MAP + [image]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr or "ERROR: EXIF/IPTC sync failed.\n"); return 1
    print(f"OK: EXIF/IPTC synchronised from XMP in {image}")
    return 0

def embed(cmd, xmp, image, keep_original=False, do_sync=False):
    if not os.path.exists(xmp):
        sys.stderr.write(f"ERROR: XMP file not found: {xmp}\n"); return 2
    if not os.path.exists(image):
        sys.stderr.write(f"ERROR: image not found: {image}\n"); return 2
    args = cmd + ["-m", "-tagsfromfile", xmp, "-xmp"]
    args += [] if keep_original else ["-overwrite_original"]
    args += [image]
    r = subprocess.run(args, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0 or "0 image files updated" in r.stdout:
        sys.stderr.write(r.stderr or "ERROR: ExifTool did not update the file.\n"); return 1
    if "<x:xmpmeta" not in read_xmp(cmd, image) and "<rdf:RDF" not in read_xmp(cmd, image):
        sys.stderr.write("ERROR: post-write verification found no XMP in the image.\n"); return 1
    print(f"OK: XMP embedded into {image}")
    if do_sync:
        return sync_exif(cmd, image)
    return 0

def main():
    ap = argparse.ArgumentParser(description="Embed XMP into an image; optionally sync EXIF/IPTC.")
    ap.add_argument("--xmp"); ap.add_argument("--image")
    ap.add_argument("--keep-original", action="store_true",
                    help="Keep IMAGE_original backup (default: overwrite in place).")
    ap.add_argument("--no-sync", action="store_true",
                    help="Embed XMP only; skip the default EXIF + IPTC-IIM synchronisation.")
    ap.add_argument("--sync-exif", action="store_true", help=argparse.SUPPRESS)  # back-compat no-op (sync is default)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--read", action="store_true", help="Print the XMP embedded in --image.")
    a = ap.parse_args()
    cmd = preflight(quiet=a.read)
    if not cmd: return 3
    if a.check: return 0
    if a.read:
        if not a.image: ap.error("--read requires --image")
        sys.stdout.write(read_xmp(cmd, a.image)); return 0
    if not (a.xmp and a.image):
        ap.error("need --xmp and --image (or --check / --read)")
    return embed(cmd, a.xmp, a.image, a.keep_original, do_sync=not a.no_sync)

if __name__ == "__main__":
    sys.exit(main())
