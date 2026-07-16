"""Smoke tests: shared helpers, XML sanitisation, build -> validate -> embed -> read.

Embedding tests require ExifTool (>= 12.46) and Pillow; they self-skip otherwise.
Run: python3 -m pytest tests/ -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.dom.minidom as minidom
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
REFERENCE = ROOT / "reference"
sys.path.insert(0, str(SCRIPTS))

import _common  # noqa: E402
import build_xmp  # noqa: E402

FIXTURES = Path(__file__).resolve().parent


def _profile() -> dict:
    return build_xmp.load_profile(str(FIXTURES / "fixture_profile.yaml"))


def _spec() -> dict:
    with open(FIXTURES / "fixture_spec.json", encoding="utf-8") as handle:
        return json.load(handle)


def _core(xmp: str) -> str:
    return xmp[xmp.find("<x:xmpmeta") : xmp.find("</x:xmpmeta>") + 12]


# ---- unit: _common ----------------------------------------------------------
def test_strip_illegal_xml_removes_control_chars():
    assert _common.strip_illegal_xml("a\x00b\x0bc\x07d") == "abcd"
    assert _common.strip_illegal_xml("keep\ttab\nlf") == "keep\ttab\nlf"


def test_xml_text_escapes_and_sanitises():
    assert _common.xml_text("<a>&\x07") == "&lt;a&gt;&amp;"


def test_xml_attr_escapes_quotes():
    assert '"' not in _common.xml_attr('x"y')


def test_safe_arg_is_absolute():
    assert _common.safe_arg("-delete_original").startswith(os.sep)


# ---- unit: build ------------------------------------------------------------
def test_build_is_wellformed_xml():
    xmp = build_xmp.build(_spec(), _profile())
    minidom.parseString(_core(xmp))  # raises if malformed


def test_control_chars_in_spec_do_not_break_xml():
    spec = _spec()
    spec["title"] = "Bad\x0bTitle\x00"
    xmp = build_xmp.build(spec, _profile())
    minidom.parseString(_core(xmp))
    assert "BadTitle" in xmp


def test_unknown_license_raises():
    spec = _spec()
    spec["license"] = "does-not-exist"
    with pytest.raises(ValueError, match="license"):
        build_xmp.build(spec, _profile())


def test_metadata_date_is_timezone_aware():
    xmp = build_xmp.build(_spec(), _profile())
    assert "<xmp:MetadataDate>" in xmp
    stamp = xmp.split("<xmp:MetadataDate>")[1].split("<")[0]
    assert stamp[-6] in "+-" and stamp[-3] == ":"  # ends with +HH:MM


# ---- integration: embed + read across formats -------------------------------
EXIFTOOL = _common.find_exiftool()
HAVE_PIL = shutil.which("python3") is not None
try:  # noqa: SIM105
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

pytestmark = pytest.mark.skipif(
    not (EXIFTOOL and HAVE_PIL), reason="ExifTool and Pillow required for embedding tests"
)


@pytest.mark.parametrize("ext,fmt", [("jpg", "JPEG"), ("png", "PNG"), ("webp", "WEBP"), ("avif", "AVIF")])
def test_embed_and_readback(tmp_path: Path, ext: str, fmt: str):
    from PIL import Image

    img = tmp_path / f"pic.{ext}"
    Image.new("RGB", (320, 240), (60, 90, 120)).save(img, fmt)
    xmp = tmp_path / "meta.xmp"
    xmp.write_text(build_xmp.build(_spec(), _profile()), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "embed_xmp.py"), "--xmp", str(xmp), "--image", str(img)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    got = subprocess.run(
        [*EXIFTOOL, "-s", "-T", "-XMP-dc:Creator", "-EXIF:Artist", str(img)],
        capture_output=True, text=True,
    ).stdout
    assert "Test Creator" in got  # XMP creator + synced EXIF Artist both present


def test_argument_injection_dash_filename(tmp_path: Path):
    """A file whose name starts with '-' must be processed as a file, not an option."""
    from PIL import Image

    img = tmp_path / "-delete_original.jpg"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(img, "JPEG")
    xmp = tmp_path / "m.xmp"
    xmp.write_text(build_xmp.build(_spec(), _profile()), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "embed_xmp.py"), "--xmp", str(xmp), "--image", str(img), "--no-sync"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert img.exists()
