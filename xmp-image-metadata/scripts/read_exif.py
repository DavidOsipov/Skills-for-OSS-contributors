#!/usr/bin/env python3
"""
read_exif.py - Harvest EXIF (and file) metadata from an image into a spec-shaped
JSON fragment of CANDIDATE technical facts, for review before creating XMP.

  python3 read_exif.py --image DSCF1234.jpg
  python3 read_exif.py --image photo.jpg --merge base_spec.json > enriched_spec.json

Output keys line up with build_xmp.py's spec: width, height, format, date_created,
gps{lat,lon,alt}, camera{make,model,lens}, exposure{...}, orientation, color_space.
Only fields actually present in the source are included. Treat every value as
editable and potentially stale or forged. Review each value against the image or
confirm it with the user before adding it to a per-photo spec; --merge fills only
missing fields and does not constitute verification.

Requires ExifTool (same discovery as embed_xmp.py: PATH, ET_EXIFTOOL, or bundled).
"""
import argparse, json, os, shutil, subprocess, sys

def find_exiftool():
    env = os.environ.get("ET_EXIFTOOL")
    if env and os.path.exists(env):
        return [env] if os.access(env, os.X_OK) else ["perl", env]
    exe = shutil.which("exiftool")
    if exe: return [exe]
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "exiftool"), os.path.join(here, "exiftool-git", "exiftool")):
        if os.path.exists(c): return ["perl", c]
    return None

TAGS = ["-EXIF:Make","-EXIF:Model","-EXIF:LensModel","-EXIF:LensInfo","-EXIF:LensMake",
        "-EXIF:ExposureTime","-EXIF:FNumber","-EXIF:ISO","-EXIF:FocalLength",
        "-EXIF:FocalLengthIn35mmFormat","-EXIF:ExposureProgram","-EXIF:MeteringMode",
        "-EXIF:Flash","-EXIF:Orientation","-EXIF:ColorSpace",
        "-EXIF:DateTimeOriginal","-EXIF:CreateDate","-EXIF:ModifyDate",
        "-Composite:GPSLatitude","-Composite:GPSLongitude","-EXIF:GPSAltitude",
        "-File:ImageWidth","-File:ImageHeight","-File:MIMEType","-EXIF:Software"]

def harvest(cmd, image):
    r = subprocess.run(cmd + ["-j", "-n", "-G0"] + TAGS + [image],
                       capture_output=True, text=True)
    data = (json.loads(r.stdout)[0] if r.stdout.strip().startswith("[") else {})
    def g(*names):
        for n in names:
            for k, v in data.items():
                if k.split(":")[-1] == n and v not in (None, ""):
                    return v
        return None
    out = {}
    w, h = g("ImageWidth"), g("ImageHeight")
    if w: out["width"] = int(w)
    if h: out["height"] = int(h)
    mime = g("MIMEType")
    if mime: out["format"] = mime
    dto = g("DateTimeOriginal") or g("CreateDate")
    if dto:  # "2026:07:16 10:00:00" -> date part
        out["date_created"] = str(dto)[:10].replace(":", "-")
    lat, lon, alt = g("GPSLatitude"), g("GPSLongitude"), g("GPSAltitude")
    if lat is not None and lon is not None:
        out["gps"] = {"lat": round(float(lat), 7), "lon": round(float(lon), 7)}
        if alt is not None: out["gps"]["alt"] = float(alt)
    cam = {}
    if g("Make"): cam["make"] = g("Make")
    if g("Model"): cam["model"] = g("Model")
    if g("LensModel"): cam["lens"] = g("LensModel")
    if cam: out["camera"] = cam
    exp = {}
    for k, tag in [("exposure_time","ExposureTime"),("f_number","FNumber"),("iso","ISO"),
                   ("focal_length","FocalLength"),("focal_length_35mm","FocalLengthIn35mmFormat")]:
        v = g(tag)
        if v is not None: exp[k] = v
    if exp: out["exposure"] = exp
    if g("Orientation") is not None: out["orientation"] = g("Orientation")
    if g("ColorSpace") is not None: out["color_space"] = g("ColorSpace")
    if g("Software"): out["software"] = g("Software")
    return out

def main():
    ap = argparse.ArgumentParser(description="Harvest untrusted EXIF candidates into a spec-shaped JSON fragment.")
    ap.add_argument("--image", required=True)
    ap.add_argument("--merge", help="Merge harvested fields INTO this base spec JSON (harvest fills gaps only).")
    a = ap.parse_args()
    cmd = find_exiftool()
    if not cmd:
        sys.exit("ERROR: ExifTool not found (set ET_EXIFTOOL or install it).")
    frag = harvest(cmd, a.image)
    if a.merge:
        base = json.load(open(a.merge, encoding="utf-8"))
        for k, v in frag.items():
            base.setdefault(k, v)   # do not overwrite values the user already set
        print(json.dumps(base, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(frag, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
