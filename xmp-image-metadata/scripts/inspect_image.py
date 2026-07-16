#!/usr/bin/env python3
"""Inspect image pixels and technical containers before writing metadata."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys


def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}")
    return result.stdout


def find_exiftool():
    configured = os.environ.get("ET_EXIFTOOL")
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("exiftool")


def dependencies():
    exiftool = find_exiftool()
    if exiftool:
        try:
            version = float(run([exiftool, "-ver"]).strip())
            exiftool_status = {"status": "available" if version >= 12.46 else "too_old", "version": version}
        except Exception as exc:
            exiftool_status = {"status": "error", "error": str(exc)}
    else:
        exiftool_status = {"status": "missing"}
    image_magick = shutil.which("magick") or shutil.which("identify")
    return {
        "pyyaml": {"status": "available" if importlib.util.find_spec("yaml") else "missing"},
        "pillow": {"status": "available" if importlib.util.find_spec("PIL") else "missing"},
        "exiftool": exiftool_status,
        "imagemagick": {"status": "available" if image_magick else "missing", "command": image_magick},
        "mediainfo": {"status": "available" if shutil.which("mediainfo") else "missing"},
    }


def ready(deps):
    return all(item["status"] == "available" for item in deps.values())


def file_facts(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": os.path.getsize(path), "sha256": digest.hexdigest()}


def pillow_facts(path):
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
            return {"status": "ok", "format": image.format, "width": image.width,
                    "height": image.height, "mode": image.mode, "frames": frames,
                    "animated": bool(getattr(image, "is_animated", False)),
                    "has_transparency": "transparency" in info or "A" in image.getbands(),
                    "icc_profile_bytes": len(info.get("icc_profile", b"")),
                    "exif_bytes": len(info.get("exif", b""))}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def exiftool_facts(path):
    exe = find_exiftool()
    if not exe:
        return {"status": "unavailable"}
    tags = ["-File:FileType", "-File:MIMEType", "-File:ImageWidth", "-File:ImageHeight",
            "-File:FileSize", "-EXIF:Orientation", "-EXIF:ColorSpace",
            "-ICC_Profile:ProfileDescription", "-ICC_Profile:ProfileVersion"]
    try:
        output = run([exe, "-j", "-n", "-G1", *tags, path])
        return {"status": "ok", "tags": json.loads(output)[0]}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def imagemagick_facts(path):
    command = ["magick", "identify"] if shutil.which("magick") else (["identify"] if shutil.which("identify") else None)
    if not command:
        return {"status": "unavailable"}
    try:
        fmt = "%m\t%w\t%h\t%z\t%[colorspace]\t%[channels]\t%[opaque]\t%n\n"
        rows = run([*command, "+ping", "-format", fmt, path]).splitlines()
        fields = ["format", "width", "height", "depth", "colorspace", "channels", "opaque", "frame_count"]
        first = dict(zip(fields, rows[0].split("\t"))) if rows else {}
        return {"status": "ok", "reader": command[0], "first_frame": first, "reported_frames": len(rows)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def mediainfo_facts(path):
    exe = shutil.which("mediainfo")
    if not exe:
        return {"status": "unavailable"}
    wanted = {"@type", "Format", "Format_Profile", "Width", "Height", "BitDepth", "ColorSpace",
              "ChromaSubsampling", "FileSize", "StreamSize", "Encoded_Date", "Tagged_Date"}
    try:
        tracks = json.loads(run([exe, "--Output=JSON", path]))["media"].get("track", [])
        return {"status": "ok", "tracks": [{k: v for k, v in track.items() if k in wanted} for track in tracks]}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def dimensions(report):
    values = {}
    pixel = report["pixel_decode"]
    if pixel.get("status") == "ok":
        values["Pillow"] = (pixel["width"], pixel["height"])
    tags = report["exiftool"].get("tags", {})
    width = tags.get("[File] ImageWidth", tags.get("File:ImageWidth"))
    height = tags.get("[File] ImageHeight", tags.get("File:ImageHeight"))
    if width is not None and height is not None:
        values["ExifTool"] = (width, height)
    image_magick = report["imagemagick"].get("first_frame", {})
    if image_magick.get("width") and image_magick.get("height"):
        values["ImageMagick"] = (int(image_magick["width"]), int(image_magick["height"]))
    return values


def main():
    parser = argparse.ArgumentParser(description="Cross-check image pixels and technical containers before metadata work.")
    parser.add_argument("--image")
    parser.add_argument("--out", help="Write JSON report to this file instead of stdout.")
    parser.add_argument("--check", action="store_true", help="Check all required dependencies and exit non-zero if any are unavailable.")
    args = parser.parse_args()
    deps = dependencies()
    if args.check:
        sys.stdout.write(json.dumps({"dependencies": deps, "ready": ready(deps)}, indent=2) + "\n")
        return 0 if ready(deps) else 3
    if not ready(deps):
        missing = ", ".join(name for name, item in deps.items() if item["status"] != "available")
        sys.stderr.write(f"ERROR: required technical-inspection dependencies unavailable: {missing}. Run --check and install them before continuing.\n")
        return 3
    if not args.image:
        parser.error("--image is required unless --check is used")
    if not os.path.isfile(args.image):
        parser.error(f"image not found: {args.image}")

    report = {"schema_version": 1, "image": os.path.abspath(args.image), "file": file_facts(args.image),
              "pixel_decode": pillow_facts(args.image), "exiftool": exiftool_facts(args.image),
              "imagemagick": imagemagick_facts(args.image), "mediainfo": mediainfo_facts(args.image)}
    checked_dimensions = dimensions(report)
    report["cross_checks"] = {"dimensions": checked_dimensions,
                              "consistent": len(set(checked_dimensions.values())) <= 1,
                              "note": "Internal consistency is not proof of capture date, location, creator, or authenticity."}
    if report["pixel_decode"].get("status") != "ok":
        report["cross_checks"]["warning"] = "Pillow could not fully verify and decode the image. Do not modify it until investigated."
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as file:
            file.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
