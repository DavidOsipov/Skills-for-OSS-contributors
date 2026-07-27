#!/usr/bin/env python3
"""
build_xmp.py - Render a complete, standards-compliant XMP packet from a reusable
author profile + a per-photo spec, ready to embed with embed_xmp.py.

  python3 build_xmp.py --spec photo.json --out photo.xmp
  python3 build_xmp.py --spec photo.json --image photo.avif --out photo.xmp   # auto dims+format
  python3 build_xmp.py --print-schema                                          # show spec fields

Covers: photoshop, dc, Iptc4xmpCore, Iptc4xmpExt (incl. IPTC 2025.1 AI fields,
PersonInImageWDetails linked-data, LocationShown), xmpMM, stEvt, xmpRights, plus,
dcterms, xmp, exif (incl. GPS), tiff, lr. Numeric-only IPTC codes in
subject_codes / scene_codes / media_topics.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterable, Mapping
from typing import Any, TypedDict, cast

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402  (local sibling module)

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference")
PROFILE = os.path.join(REF, "author_profile.yaml")
MEDIA_TSV = os.path.join(REF, "iptc_media_topics.tsv")
SOURCE_TSV = os.path.join(REF, "iptc_digital_source_types.tsv")
DST_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
AI_SOURCE_TYPES = {
    "trainedAlgorithmicMedia",
    "compositeWithTrainedAlgorithmicMedia",
    "algorithmicMedia",
    "compositeSynthetic",
}


def esc(value: object) -> str:
    return _common.xml_text(value)


def _parse_offset(tz: str) -> datetime.timezone:
    """Parse an offset like '+04:00'/'-05:30'/'Z' into a tzinfo (UTC fallback)."""
    text = (tz or "").strip()
    if text in ("", "Z", "z"):
        return datetime.timezone.utc
    m = re.match(r"([+-])(\d{2}):?(\d{2})$", text)
    if not m:
        return datetime.timezone.utc
    sign = 1 if m.group(1) == "+" else -1
    return datetime.timezone(
        sign * datetime.timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
    )


_MEDTOP: dict[str, str] | None = None
_SOURCE_TYPES: dict[str, dict[str, str]] | None = None


def _medtop_label(code: str) -> str:
    global _MEDTOP
    if _MEDTOP is None:
        _MEDTOP = {}
        try:
            import csv

            with open(MEDIA_TSV, encoding="utf-8") as f:
                for r in csv.DictReader(f, delimiter="\t"):
                    _MEDTOP[r["code"]] = r.get("prefLabel", "")
        except Exception:
            _MEDTOP = {}
    return _MEDTOP.get(str(code).strip(), "")


def _digital_source_uri(token: str) -> str:
    """Return an active official Digital Source Type URI for a short token."""
    token = str(token)
    if token.startswith(DST_BASE):
        token = token.rsplit("/", 1)[-1]
    global _SOURCE_TYPES
    if _SOURCE_TYPES is None:
        _SOURCE_TYPES = {}
        try:
            import csv

            with open(SOURCE_TSV, encoding="utf-8") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    _SOURCE_TYPES[row["token"]] = row
        except Exception as exc:
            raise ValueError(f"cannot read {SOURCE_TSV}: {exc}") from exc
    entry = _SOURCE_TYPES.get(token)
    if not entry:
        raise ValueError(
            f"unknown Digital Source Type {token!r}; search with lookup_codes.py --vocab source"
        )
    if entry.get("retired"):
        raise ValueError(
            f"Digital Source Type {token!r} is retired: {entry.get('note') or 'select an active value'}"
        )
    return entry["uri"]


class Spec(TypedDict, total=False):
    title: str
    headline: str
    description: str
    alt_text: str
    ext_description: str
    keywords: list[str]
    intellectual_genre: str
    subject_codes: list[str]
    scene_codes: list[str]
    media_topics: list[str]
    city: str
    state: str
    country: str
    country_code: str
    sublocation: str
    location_created: dict[str, Any]
    location_shown: list[dict[str, Any]]
    gps: dict[str, float]
    persons_in_image: list[str]
    persons_details: list[dict[str, Any]]
    model_age: int
    image_creator: dict[str, str]
    digital_source_type: str
    ai_system_used: str
    ai_system_version: str
    ai_prompt: str
    ai_prompt_writer: str
    width: int
    height: int
    format: str
    dc_type: str
    urgency: int
    transmission_reference: str
    date_created: str
    authors_position: str
    license: str
    licensor_url: str
    provenance: str
    image_guid: str
    supplier_image_id: str
    rights_marked: bool


def load_profile(path: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        sys.exit("ERROR: PyYAML required. Install with: pip install pyyaml")
    if not os.path.isfile(path):
        raise ValueError(
            f"profile not found: {path}. Copy reference/author_profile.template.yaml and fill it in."
        )
    with open(path, encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(
            "profile must be a YAML mapping copied from author_profile.template.yaml"
        )
    return loaded


def validate_profile(profile: dict[str, Any]) -> None:
    """Reject an unfilled template and surface useful errors for real profiles."""
    required = ("creator", "contact", "plus", "defaults", "license_presets")
    missing = [key for key in required if not isinstance(profile.get(key), dict)]
    if missing:
        raise ValueError(
            "profile is missing required mapping(s): " + ", ".join(missing)
        )
    if not str(profile["creator"].get("name", "")).strip():
        raise ValueError("profile creator.name is required")

    def find_placeholder(value: Any, path: str = "profile") -> str | None:
        if isinstance(value, dict):
            for key, item in value.items():
                found = find_placeholder(item, f"{path}.{key}")
                if found:
                    return found
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found = find_placeholder(item, f"{path}[{index}]")
                if found:
                    return found
        elif isinstance(value, str) and "[REQUIRED" in value:
            return path
        return None

    placeholder = find_placeholder(profile)
    if placeholder:
        raise ValueError(
            f"replace the required placeholder in {placeholder} before building"
        )


def detect_image(image: str) -> tuple[int | None, int | None, str | None]:
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 100_000_000  # guard against decompression bombs
        with Image.open(_common.safe_arg(image)) as im:
            w, h = im.size
            fmt = (im.format or "").lower()
        mime = {
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "avif": "image/avif",
            "heif": "image/heif",
            "gif": "image/gif",
            "tiff": "image/tiff",
        }.get(fmt, "application/octet-stream")
        return w, h, mime
    except Exception:
        return None, None, None


def native_exif_version(image: str) -> str | None:
    """Read a valid native Exif version without inventing one for a sidecar."""
    cmd = _common.find_exiftool()
    if not cmd:
        return None
    try:
        proc = subprocess.run(
            [*cmd, "-s3", "-EXIF:ExifVersion", _common.safe_arg(image)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = proc.stdout.strip()
    return value if re.fullmatch(r"\d{4}", value) else None


def _gps(dec: float, is_lat: bool) -> str:
    ref = ("N" if dec >= 0 else "S") if is_lat else ("E" if dec >= 0 else "W")
    dec = abs(float(dec))
    deg = int(dec)
    minutes = (dec - deg) * 60
    mm = f"{minutes:.6f}".rstrip("0").rstrip(".")
    return f"{deg},{mm}{ref}"


# ---- generic RDF renderers ---------------------------------------------------
def alt_block(tag: str, value: object, IND: str) -> str:
    """value: str -> single x-default; dict lang->text -> multi-language Alt."""
    if isinstance(value, dict):
        lis = "".join(
            f'{IND}      <rdf:li xml:lang="{_common.xml_attr(lang)}">{esc(t)}</rdf:li>\n'
            for lang, t in value.items()
        )
    else:
        lis = f'{IND}      <rdf:li xml:lang="x-default">{esc(value)}</rdf:li>\n'
    return f"{IND}<{tag}>\n{IND}   <rdf:Alt>\n{lis}{IND}   </rdf:Alt>\n{IND}</{tag}>\n"


def bag_block(tag: str, items: Iterable[object], IND: str) -> str:
    values = list(items)
    if not values:
        return ""
    lis = "".join(f"{IND}      <rdf:li>{esc(i)}</rdf:li>\n" for i in values)
    return f"{IND}<{tag}>\n{IND}   <rdf:Bag>\n{lis}{IND}   </rdf:Bag>\n{IND}</{tag}>\n"


def code_bag(tag: str, codes: Iterable[object], IND: str) -> str:
    return bag_block(tag, [str(c).strip() for c in codes if str(c).strip()], IND)


def resolve_person(
    name: str, profile: Mapping[str, Any], spec: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge a known-persons registry entry + any per-spec override for `name`."""
    reg = profile.get("known_persons", {}) or {}
    aliases = reg.get("aliases", {}) or {}
    canon = aliases.get(name, name)
    data = dict(reg.get(canon, {})) if isinstance(reg.get(canon), dict) else {}
    for d in spec.get("persons_details", []) or []:
        if d.get("name") in (name, canon):
            data = {**data, **d}
    data.setdefault("name", canon if canon in reg else name)
    return data


def build(spec: Spec, profile: Mapping[str, Any], image: str | None = None) -> str:
    cr = profile["creator"]
    ct = profile["contact"]
    ids = profile.get("identifiers", {})
    plus = profile.get("plus", {})
    dfl = profile.get("defaults", {})
    rights = profile.get("rights", {}) or {}
    lic_key = spec.get("license") or profile.get("default_license")
    presets = profile.get("license_presets") or {}
    if not lic_key or lic_key not in presets:
        raise ValueError(
            f"license {lic_key!r} is not defined in the profile's license_presets"
        )
    lic = presets[lic_key]

    tz = dfl.get("timezone", "+00:00")
    tzinfo = _parse_offset(tz)
    date_created = spec.get("date_created")
    year = (date_created or datetime.datetime.now(tzinfo).date().isoformat())[:4]
    meta_ts = datetime.datetime.now(tzinfo).replace(microsecond=0).isoformat()
    creator_full = cr.get("full_name") or cr["name"]

    w = spec.get("width")
    h = spec.get("height")
    mime = spec.get("format")
    if image and (w is None or h is None or mime is None):
        dw, dh, dmime = detect_image(image)
        w = w or dw
        h = h or dh
        mime = mime or dmime
    mime = mime or "image/jpeg"
    native_version = native_exif_version(image) if image else None

    kw = list(spec.get("keywords", [])) + list(profile.get("identity_keywords", []))
    seen, kw_u = set(), []
    for k in kw:
        if k not in seen:
            seen.add(k)
            kw_u.append(k)

    rights_line = lic["rights_line"].format(year=year, creator=cr["name"])
    dst = spec.get("digital_source_type") or dfl.get(
        "digital_source_type", "digitalCapture"
    )
    dst_leaf = _digital_source_uri(dst)
    is_ai = (dst in AI_SOURCE_TYPES) or any(
        spec.get(k)
        for k in (
            "ai_system_used",
            "ai_prompt",
            "ai_prompt_writer",
            "ai_system_version",
        )
    )
    persons = spec.get("persons_in_image", [])

    IND = "         "
    out: list[str] = []
    A = out.append
    A('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n')
    A('<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Image Metadata Skill">\n')
    A('   <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n')
    A('      <rdf:Description rdf:about=""\n')
    for pfx, uri in [
        ("photoshop", "http://ns.adobe.com/photoshop/1.0/"),
        ("dc", "http://purl.org/dc/elements/1.1/"),
        ("Iptc4xmpCore", "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/"),
        ("Iptc4xmpExt", "http://iptc.org/std/Iptc4xmpExt/2008-02-29/"),
        ("xmpMM", "http://ns.adobe.com/xap/1.0/mm/"),
        ("stEvt", "http://ns.adobe.com/xap/1.0/sType/ResourceEvent#"),
        ("xmpRights", "http://ns.adobe.com/xap/1.0/rights/"),
        ("plus", "http://ns.useplus.org/ldf/xmp/1.0/"),
        ("dcterms", "http://purl.org/dc/terms/"),
        ("xmp", "http://ns.adobe.com/xap/1.0/"),
        ("exif", "http://ns.adobe.com/exif/1.0/"),
        ("tiff", "http://ns.adobe.com/tiff/1.0/"),
        ("lr", "http://ns.adobe.com/lightroom/1.0/"),
    ]:
        A(f'            xmlns:{pfx}="{uri}"\n')
    out[-1] = out[-1].rstrip("\n") + ">\n"

    # --- photoshop ---
    A(f'{IND}<photoshop:Urgency>{esc(spec.get("urgency",1))}</photoshop:Urgency>\n')
    A(
        f'{IND}<photoshop:Instructions>{esc(lic["instructions"])}</photoshop:Instructions>\n'
    )
    if date_created:
        A(
            f"{IND}<photoshop:DateCreated>{esc(date_created)}T00:00:00</photoshop:DateCreated>\n"
        )
    A(
        f'{IND}<photoshop:AuthorsPosition>{esc(spec.get("authors_position", cr.get("authors_position","")))}</photoshop:AuthorsPosition>\n'
    )
    if spec.get("city"):
        A(f'{IND}<photoshop:City>{esc(spec["city"])}</photoshop:City>\n')
    if spec.get("state"):
        A(f'{IND}<photoshop:State>{esc(spec["state"])}</photoshop:State>\n')
    if spec.get("country"):
        A(f'{IND}<photoshop:Country>{esc(spec["country"])}</photoshop:Country>\n')
    if spec.get("transmission_reference"):
        A(
            f'{IND}<photoshop:TransmissionReference>{esc(spec["transmission_reference"])}</photoshop:TransmissionReference>\n'
        )
    if spec.get("headline"):
        A(f'{IND}<photoshop:Headline>{esc(spec["headline"])}</photoshop:Headline>\n')
    credit = cr["name"] + (
        f' (ISNI: {ids["isni_spaced"]})' if ids.get("isni_spaced") else ""
    )
    A(f"{IND}<photoshop:Credit>{esc(credit)}</photoshop:Credit>\n")
    A(f"{IND}<photoshop:Source>{esc(creator_full)}</photoshop:Source>\n")
    A(f"{IND}<photoshop:CaptionWriter>{esc(creator_full)}</photoshop:CaptionWriter>\n")
    A(f"{IND}<photoshop:ColorMode>3</photoshop:ColorMode>\n")

    # --- dc ---
    A(f"{IND}<dc:format>{esc(mime)}</dc:format>\n")
    A(f'{IND}<dc:type>{esc(spec.get("dc_type","StillImage"))}</dc:type>\n')
    guid = spec.get("image_guid") or ("urn:uuid:" + str(uuid.uuid4()))
    A(f"{IND}<dc:identifier>{esc(guid)}</dc:identifier>\n")
    if spec.get("title"):
        A(alt_block("dc:title", spec["title"], IND))
    A(bag_block("dc:subject", kw_u, IND))
    A(
        f'{IND}<dc:creator>\n{IND}   <rdf:Seq>\n{IND}      <rdf:li>{esc(cr["name"])}</rdf:li>\n{IND}   </rdf:Seq>\n{IND}</dc:creator>\n'
    )
    A(alt_block("dc:rights", rights_line, IND))
    if spec.get("description"):
        A(alt_block("dc:description", spec["description"], IND))

    # --- Iptc4xmpCore ---
    if spec.get("country_code"):
        A(
            f'{IND}<Iptc4xmpCore:CountryCode>{esc(spec["country_code"])}</Iptc4xmpCore:CountryCode>\n'
        )
    if spec.get("sublocation"):
        A(
            f'{IND}<Iptc4xmpCore:Location>{esc(spec["sublocation"])}</Iptc4xmpCore:Location>\n'
        )
    if spec.get("intellectual_genre"):
        A(
            f'{IND}<Iptc4xmpCore:IntellectualGenre>{esc(spec["intellectual_genre"])}</Iptc4xmpCore:IntellectualGenre>\n'
        )
    contact_fields = [
        ("CiAdrCtry", ct.get("country")),
        ("CiAdrCity", ct.get("city")),
        ("CiEmailWork", ct.get("email")),
        ("CiUrlWork", ct.get("url")),
    ]
    if any(value for _, value in contact_fields):
        A(f'{IND}<Iptc4xmpCore:CreatorContactInfo rdf:parseType="Resource">\n')
        for tag, value in contact_fields:
            if value:
                A(f"{IND}   <Iptc4xmpCore:{tag}>{esc(value)}</Iptc4xmpCore:{tag}>\n")
        A(f"{IND}</Iptc4xmpCore:CreatorContactInfo>\n")
    if spec.get("alt_text"):
        A(alt_block("Iptc4xmpCore:AltTextAccessibility", spec["alt_text"], IND))
    if spec.get("ext_description"):
        A(alt_block("Iptc4xmpCore:ExtDescrAccessibility", spec["ext_description"], IND))
    if spec.get("subject_codes"):
        A(code_bag("Iptc4xmpCore:SubjectCode", spec["subject_codes"], IND))
    if spec.get("scene_codes"):
        A(code_bag("Iptc4xmpCore:Scene", spec["scene_codes"], IND))

    # --- xmpMM ---
    iid = "xmp.iid:" + str(uuid.uuid4())
    did = "xmp.did:" + str(uuid.uuid4())
    odid = uuid.uuid4().hex.upper()
    A(f"{IND}<xmpMM:OriginalDocumentID>{odid}</xmpMM:OriginalDocumentID>\n")
    A(f"{IND}<xmpMM:InstanceID>{iid}</xmpMM:InstanceID>\n")
    A(f"{IND}<xmpMM:DocumentID>{did}</xmpMM:DocumentID>\n")
    A(
        f'{IND}<xmpMM:History>\n{IND}   <rdf:Seq>\n{IND}      <rdf:li rdf:parseType="Resource">\n'
        f"{IND}         <stEvt:action>saved</stEvt:action>\n"
        f"{IND}         <stEvt:instanceID>{iid}</stEvt:instanceID>\n"
        f"{IND}         <stEvt:when>{meta_ts}</stEvt:when>\n"
        f'{IND}         <stEvt:softwareAgent>{esc(dfl.get("creator_tool","ExifTool"))}</stEvt:softwareAgent>\n'
        f"{IND}      </rdf:li>\n{IND}   </rdf:Seq>\n{IND}</xmpMM:History>\n"
    )

    # --- xmpRights ---
    web_stmt = lic.get("web_statement") or lic.get("deed")
    if web_stmt:
        A(f"{IND}<xmpRights:WebStatement>{esc(web_stmt)}</xmpRights:WebStatement>\n")
    A(
        f'{IND}<xmpRights:Marked>{esc(spec.get("rights_marked", True))}</xmpRights:Marked>\n'
    )
    owner = rights.get("owner") or creator_full
    if owner:
        A(bag_block("xmpRights:Owner", [owner], IND))
    ut = lic.get("usage_terms") or lic.get("url")
    if ut:
        A(alt_block("xmpRights:UsageTerms", ut, IND))

    # --- Iptc4xmpExt ---
    A(
        f"{IND}<Iptc4xmpExt:DigitalSourceType>{esc(dst_leaf)}</Iptc4xmpExt:DigitalSourceType>\n"
    )
    if is_ai:  # IPTC 2025.1 AI-generation disclosure
        if spec.get("ai_system_used"):
            A(
                f'{IND}<Iptc4xmpExt:AISystemUsed>{esc(spec["ai_system_used"])}</Iptc4xmpExt:AISystemUsed>\n'
            )
        if spec.get("ai_system_version"):
            A(
                f'{IND}<Iptc4xmpExt:AISystemVersionUsed>{esc(spec["ai_system_version"])}</Iptc4xmpExt:AISystemVersionUsed>\n'
            )
        if spec.get("ai_prompt"):
            A(
                f'{IND}<Iptc4xmpExt:AIPromptInformation>{esc(spec["ai_prompt"])}</Iptc4xmpExt:AIPromptInformation>\n'
            )
        if spec.get("ai_prompt_writer"):
            A(
                f'{IND}<Iptc4xmpExt:AIPromptWriterName>{esc(spec["ai_prompt_writer"])}</Iptc4xmpExt:AIPromptWriterName>\n'
            )
    if w:
        A(f"{IND}<Iptc4xmpExt:MaxAvailWidth>{esc(w)}</Iptc4xmpExt:MaxAvailWidth>\n")
    if h:
        A(f"{IND}<Iptc4xmpExt:MaxAvailHeight>{esc(h)}</Iptc4xmpExt:MaxAvailHeight>\n")
    if persons:
        A(bag_block("Iptc4xmpExt:PersonInImage", persons, IND))
    # PersonInImageWDetails (linked-data): from known_persons registry / persons_details
    wd = []
    for nm in persons:
        d = resolve_person(nm, profile, spec)
        if d.get("ids") or d.get("description"):
            wd.append(d)
    if wd:
        A(f"{IND}<Iptc4xmpExt:PersonInImageWDetails>\n{IND}   <rdf:Bag>\n")
        for d in wd:
            A(f'{IND}      <rdf:li rdf:parseType="Resource">\n')
            if d.get("ids"):
                A(f"{IND}         <Iptc4xmpExt:PersonId>\n{IND}            <rdf:Bag>\n")
                for u in d["ids"]:
                    A(f"{IND}               <rdf:li>{esc(u)}</rdf:li>\n")
                A(
                    f"{IND}            </rdf:Bag>\n{IND}         </Iptc4xmpExt:PersonId>\n"
                )
            A(
                f"{IND}         <Iptc4xmpExt:PersonName>\n{IND}            <rdf:Alt>\n"
                f'{IND}               <rdf:li xml:lang="x-default">{esc(d.get("name",""))}</rdf:li>\n'
                f"{IND}            </rdf:Alt>\n{IND}         </Iptc4xmpExt:PersonName>\n"
            )
            if d.get("description"):
                A(
                    f"{IND}         <Iptc4xmpExt:PersonDescription>\n{IND}            <rdf:Alt>\n"
                    f'{IND}               <rdf:li xml:lang="x-default">{esc(d["description"])}</rdf:li>\n'
                    f"{IND}            </rdf:Alt>\n{IND}         </Iptc4xmpExt:PersonDescription>\n"
                )
            A(f"{IND}      </rdf:li>\n")
        A(f"{IND}   </rdf:Bag>\n{IND}</Iptc4xmpExt:PersonInImageWDetails>\n")

    def location_bag(tag: str, loc: Mapping[str, Any]) -> str:
        inner = ""
        for k, xtag in [
            ("city", "City"),
            ("sublocation", "Sublocation"),
            ("state", "ProvinceState"),
            ("country", "CountryName"),
            ("country_code", "CountryCode"),
            ("world_region", "WorldRegion"),
        ]:
            if loc.get(k):
                inner += f"{IND}         <Iptc4xmpExt:{xtag}>{esc(loc[k])}</Iptc4xmpExt:{xtag}>\n"
        if not inner:
            return ""
        return f'{IND}<{tag}>\n{IND}   <rdf:Bag>\n{IND}      <rdf:li rdf:parseType="Resource">\n{inner}{IND}      </rdf:li>\n{IND}   </rdf:Bag>\n{IND}</{tag}>\n'

    loc = spec.get("location_created") or {
        "city": spec.get("city"),
        "country": spec.get("country"),
        "country_code": spec.get("country_code"),
        "state": spec.get("state"),
        "sublocation": spec.get("sublocation"),
        "world_region": dfl.get("world_region"),
    }
    lc = location_bag("Iptc4xmpExt:LocationCreated", loc)
    if lc:
        A(lc)
    for shown in spec.get("location_shown") or []:
        A(location_bag("Iptc4xmpExt:LocationShown", shown))

    if spec.get("media_topics"):
        A(f"{IND}<Iptc4xmpExt:AboutCvTerm>\n{IND}   <rdf:Bag>\n")
        for c in spec["media_topics"]:
            c = str(c).strip()
            name = _medtop_label(c)
            A(
                f'{IND}      <rdf:li rdf:parseType="Resource">\n'
                f"{IND}         <Iptc4xmpExt:CvId>http://cv.iptc.org/newscodes/mediatopic/</Iptc4xmpExt:CvId>\n"
                f"{IND}         <Iptc4xmpExt:CvTermId>http://cv.iptc.org/newscodes/mediatopic/{c}</Iptc4xmpExt:CvTermId>\n"
            )
            if name:
                A(
                    f"{IND}         <Iptc4xmpExt:CvTermName>\n{IND}            <rdf:Alt>\n"
                    f'{IND}               <rdf:li xml:lang="x-default">{esc(name)}</rdf:li>\n'
                    f"{IND}            </rdf:Alt>\n{IND}         </Iptc4xmpExt:CvTermName>\n"
                )
            A(f"{IND}      </rdf:li>\n")
        A(f"{IND}   </rdf:Bag>\n{IND}</Iptc4xmpExt:AboutCvTerm>\n")
    if persons and spec.get("model_age"):
        A(bag_block("Iptc4xmpExt:ModelAge", [spec["model_age"]], IND))

    # --- PLUS ---
    def plus_seq(tag: str, fields: Iterable[tuple[str, Any]]) -> str:
        inner = "".join(f"{IND}         <{k}>{esc(v)}</{k}>\n" for k, v in fields if v)
        if not inner:
            return ""
        return f'{IND}<{tag}>\n{IND}   <rdf:Seq>\n{IND}      <rdf:li rdf:parseType="Resource">\n{inner}{IND}      </rdf:li>\n{IND}   </rdf:Seq>\n{IND}</{tag}>\n'

    if persons:
        for tag, key in (
            ("ModelReleaseStatus", "model_release_status"),
            ("MinorModelAgeDisclosure", "minor_model_age_disclosure"),
        ):
            if plus.get(key):
                A(f"{IND}<plus:{tag}>{esc(plus[key])}</plus:{tag}>\n")
    if plus.get("property_release_status"):
        A(
            f'{IND}<plus:PropertyReleaseStatus>{esc(plus["property_release_status"])}</plus:PropertyReleaseStatus>\n'
        )
    A(
        plus_seq(
            "plus:ImageSupplier",
            [
                ("plus:ImageSupplierName", plus.get("supplier_name")),
                ("plus:ImageSupplierID", plus.get("supplier_id")),
                ("plus:ImageSupplierImageID", spec.get("supplier_image_id")),
            ],
        )
    )
    ic = spec.get("image_creator")
    if ic:
        A(
            plus_seq(
                "plus:ImageCreator",
                [
                    ("plus:ImageCreatorName", ic.get("name")),
                    ("plus:ImageCreatorID", ic.get("id")),
                ],
            )
        )
    A(
        plus_seq(
            "plus:CopyrightOwner",
            [
                ("plus:CopyrightOwnerName", plus.get("copyright_owner_name")),
                ("plus:CopyrightOwnerID", plus.get("copyright_owner_id")),
            ],
        )
    )
    A(
        plus_seq(
            "plus:Licensor",
            [
                ("plus:LicensorName", plus.get("licensor_name")),
                ("plus:LicensorID", plus.get("licensor_id")),
                ("plus:LicensorEmail", plus.get("licensor_email")),
                ("plus:LicensorURL", spec.get("licensor_url")),
            ],
        )
    )

    # --- dcterms / xmp ---
    if spec.get("provenance"):
        A(f'{IND}<dcterms:provenance>{esc(spec["provenance"])}</dcterms:provenance>\n')
    A(f"{IND}<xmp:MetadataDate>{meta_ts}</xmp:MetadataDate>\n")
    A(
        f'{IND}<xmp:CreatorTool>{esc(dfl.get("creator_tool","ExifTool"))}</xmp:CreatorTool>\n'
    )
    A(f"{IND}<xmp:ModifyDate>{meta_ts}</xmp:ModifyDate>\n")

    # --- exif / tiff (+ GPS) ---
    if native_version:
        A(f"{IND}<exif:ExifVersion>{esc(native_version)}</exif:ExifVersion>\n")
    if date_created:
        A(
            f"{IND}<exif:DateTimeOriginal>{esc(date_created)}T00:00:00{tz}</exif:DateTimeOriginal>\n"
        )
    if w:
        A(f"{IND}<exif:PixelXDimension>{esc(w)}</exif:PixelXDimension>\n")
    if h:
        A(f"{IND}<exif:PixelYDimension>{esc(h)}</exif:PixelYDimension>\n")
    gps = spec.get("gps") or {}
    if gps.get("lat") is not None and gps.get("lon") is not None:
        A(f'{IND}<exif:GPSLatitude>{esc(_gps(gps["lat"], True))}</exif:GPSLatitude>\n')
        A(
            f'{IND}<exif:GPSLongitude>{esc(_gps(gps["lon"], False))}</exif:GPSLongitude>\n'
        )
        if gps.get("alt") is not None:
            A(f'{IND}<exif:GPSAltitude>{esc(gps["alt"])}</exif:GPSAltitude>\n')
            A(
                f'{IND}<exif:GPSAltitudeRef>{esc(0 if float(gps["alt"])>=0 else 1)}</exif:GPSAltitudeRef>\n'
            )
    A(f"{IND}<tiff:Orientation>1</tiff:Orientation>\n")
    if w:
        A(f"{IND}<tiff:ImageWidth>{esc(w)}</tiff:ImageWidth>\n")
    if h:
        A(f"{IND}<tiff:ImageLength>{esc(h)}</tiff:ImageLength>\n")

    A(bag_block("lr:hierarchicalSubject", kw_u, IND))
    A("      </rdf:Description>\n   </rdf:RDF>\n</x:xmpmeta>\n")
    A('<?xpacket end="w"?>\n')
    return "".join(out)


SCHEMA = {
    "descriptive": [
        "title",
        "headline",
        "description",
        "alt_text",
        "ext_description",
        "keywords",
        "intellectual_genre",
    ],
    "classification": [
        "subject_codes (legacy 8-digit)",
        "scene_codes (6-digit)",
        "media_topics (medtop 8-digit)",
    ],
    "location": [
        "city",
        "state",
        "country",
        "country_code",
        "sublocation",
        "location_created{city,state,country,country_code,sublocation,world_region}",
        "location_shown[ {..same..} ]",
        "gps{lat,lon,alt}",
    ],
    "people": [
        "persons_in_image[]",
        "model_age",
        "image_creator{name,id}",
        "persons_details[{name,ids[],description}]  (or use profile known_persons)",
    ],
    "ai_disclosure_2025.1": [
        "digital_source_type: trainedAlgorithmicMedia (etc.)",
        "ai_system_used",
        "ai_system_version",
        "ai_prompt",
        "ai_prompt_writer",
    ],
    "technical": [
        "width",
        "height",
        "format",
        "dc_type (default StillImage)",
        "urgency",
        "transmission_reference",
    ],
    "rights_identity": [
        "license (preset key)",
        "licensor_url",
        "provenance",
        "image_guid",
        "supplier_image_id",
        "rights_marked",
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render a complete XMP packet from profile + per-photo spec."
    )
    ap.add_argument("--spec", help="Per-photo spec JSON.")
    ap.add_argument(
        "--image", help="Optional image to auto-detect width/height/format."
    )
    ap.add_argument(
        "--profile",
        default=PROFILE,
        help="Author profile YAML (defaults to reference/author_profile.yaml if present).",
    )
    ap.add_argument("--out", help="Write the XMP here (default: stdout).")
    ap.add_argument("--print-schema", action="store_true")
    a = ap.parse_args()
    if a.print_schema:
        print(json.dumps(SCHEMA, indent=2))
        return 0
    if not a.spec:
        ap.error("--spec is required (or use --print-schema)")
    try:
        with open(a.spec, encoding="utf-8") as handle:
            spec = json.load(handle)
        if not isinstance(spec, dict):
            raise ValueError("spec must be a JSON object")
        profile = load_profile(a.profile)
        validate_profile(profile)
        xmp = build(cast(Spec, spec), profile, image=a.image)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        ap.error(str(exc))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as handle:
            handle.write(xmp)
        print(f"wrote {a.out}")
    else:
        sys.stdout.write(xmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
