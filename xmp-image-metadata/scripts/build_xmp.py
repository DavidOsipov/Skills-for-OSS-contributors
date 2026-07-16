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
import argparse, datetime, json, os, sys, uuid
from xml.sax.saxutils import escape as _esc

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference")
PROFILE_TEMPLATE = os.path.join(REF, "author_profile.template.yaml")
MEDIA_TSV = os.path.join(REF, "iptc_media_topics.tsv")
SOURCE_TSV = os.path.join(REF, "iptc_digital_source_types.tsv")
DST_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
AI_SOURCE_TYPES = {"trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia",
                   "algorithmicMedia", "compositeSynthetic"}

def esc(v): return _esc("" if v is None else str(v))

_MEDTOP = None
_SOURCE_TYPES = None
def _medtop_label(code):
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

def _digital_source_uri(token):
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
        raise ValueError(f"unknown Digital Source Type {token!r}; search with lookup_codes.py --vocab source")
    if entry.get("retired"):
        raise ValueError(f"Digital Source Type {token!r} is retired: {entry.get('note') or 'select an active value'}")
    return entry["uri"]

def load_profile(path):
    try:
        import yaml
    except ImportError:
        sys.exit("ERROR: PyYAML required. Install with: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def validate_profile(profile):
    """Reject an incomplete template and produce useful errors for private profiles."""
    if not isinstance(profile, dict):
        raise ValueError("profile must be a YAML mapping copied from author_profile.template.yaml")
    required_maps = ("creator", "contact", "plus", "defaults", "license_presets")
    missing = [key for key in required_maps if not isinstance(profile.get(key), dict)]
    if missing:
        raise ValueError("profile is missing required mapping(s): " + ", ".join(missing))
    if not str(profile["creator"].get("name", "")).strip():
        raise ValueError("profile creator.name is required; ask the user before choosing it")

    def find_placeholder(value, path="profile"):
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
        raise ValueError(f"replace the required placeholder in {placeholder} before building")

def detect_image(image):
    try:
        from PIL import Image
        with Image.open(image) as im:
            w, h = im.size
            fmt = (im.format or "").lower()
        mime = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                "avif": "image/avif", "heif": "image/heif", "gif": "image/gif",
                "tiff": "image/tiff"}.get(fmt, "application/octet-stream")
        return w, h, mime
    except Exception:
        return None, None, None

def _gps(dec, is_lat):
    ref = ("N" if dec >= 0 else "S") if is_lat else ("E" if dec >= 0 else "W")
    dec = abs(float(dec)); deg = int(dec); minutes = (dec - deg) * 60
    mm = f"{minutes:.6f}".rstrip("0").rstrip(".")
    return f"{deg},{mm}{ref}"

# ---- generic RDF renderers ---------------------------------------------------
def alt_block(tag, value, I):
    """value: str -> single x-default; dict lang->text -> multi-language Alt."""
    if isinstance(value, dict):
        lis = "".join(f'{I}      <rdf:li xml:lang="{esc(l)}">{esc(t)}</rdf:li>\n' for l, t in value.items())
    else:
        lis = f'{I}      <rdf:li xml:lang="x-default">{esc(value)}</rdf:li>\n'
    return f"{I}<{tag}>\n{I}   <rdf:Alt>\n{lis}{I}   </rdf:Alt>\n{I}</{tag}>\n"

def bag_block(tag, items, I):
    lis = "".join(f"{I}      <rdf:li>{esc(i)}</rdf:li>\n" for i in items)
    return f"{I}<{tag}>\n{I}   <rdf:Bag>\n{lis}{I}   </rdf:Bag>\n{I}</{tag}>\n"

def code_bag(tag, codes, I):
    return bag_block(tag, [str(c).strip() for c in codes if str(c).strip()], I)

def resolve_person(name, profile, spec):
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

def build(spec, profile, image=None):
    cr = profile["creator"]; ct = profile["contact"]; ids = profile.get("identifiers", {})
    plus = profile.get("plus", {}); dfl = profile.get("defaults", {}); rights = profile.get("rights", {}) or {}
    lic_key = spec.get("license") or profile.get("default_license")
    presets = profile["license_presets"]
    if not lic_key or lic_key not in presets:
        raise ValueError(f"license {lic_key!r} is not defined in the private profile")
    lic = presets[lic_key]

    tz = dfl.get("timezone", "+00:00")
    date_created = spec.get("date_created")
    year = (date_created or datetime.date.today().isoformat())[:4]
    now = datetime.datetime.now().replace(microsecond=0).isoformat()
    meta_ts = f"{now}{tz}"
    creator_full = cr.get("full_name") or cr["name"]

    w = spec.get("width"); h = spec.get("height"); mime = spec.get("format")
    if image and (w is None or h is None or mime is None):
        dw, dh, dmime = detect_image(image)
        w = w or dw; h = h or dh; mime = mime or dmime
    mime = mime or "image/jpeg"

    kw = list(spec.get("keywords", [])) + list(profile.get("identity_keywords", []))
    seen, kw_u = set(), []
    for k in kw:
        if k not in seen:
            seen.add(k); kw_u.append(k)

    rights_line = lic["rights_line"].format(year=year, creator=cr["name"])
    dst = spec.get("digital_source_type") or dfl.get("digital_source_type", "digitalCapture")
    dst_leaf = _digital_source_uri(dst)
    is_ai = (dst in AI_SOURCE_TYPES) or any(spec.get(k) for k in
             ("ai_system_used", "ai_prompt", "ai_prompt_writer", "ai_system_version"))
    persons = spec.get("persons_in_image", [])

    I = "         "
    out = []; A = out.append
    A('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n')
    A('<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Image Metadata Skill">\n')
    A('   <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n')
    A('      <rdf:Description rdf:about=""\n')
    for pfx, uri in [
        ("photoshop","http://ns.adobe.com/photoshop/1.0/"),
        ("dc","http://purl.org/dc/elements/1.1/"),
        ("Iptc4xmpCore","http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/"),
        ("Iptc4xmpExt","http://iptc.org/std/Iptc4xmpExt/2008-02-29/"),
        ("xmpMM","http://ns.adobe.com/xap/1.0/mm/"),
        ("stEvt","http://ns.adobe.com/xap/1.0/sType/ResourceEvent#"),
        ("xmpRights","http://ns.adobe.com/xap/1.0/rights/"),
        ("plus","http://ns.useplus.org/ldf/xmp/1.0/"),
        ("dcterms","http://purl.org/dc/terms/"),
        ("xmp","http://ns.adobe.com/xap/1.0/"),
        ("exif","http://ns.adobe.com/exif/1.0/"),
        ("tiff","http://ns.adobe.com/tiff/1.0/"),
        ("lr","http://ns.adobe.com/lightroom/1.0/")]:
        A(f'            xmlns:{pfx}="{uri}"\n')
    out[-1] = out[-1].rstrip("\n") + ">\n"

    # --- photoshop ---
    A(f'{I}<photoshop:Urgency>{esc(spec.get("urgency",1))}</photoshop:Urgency>\n')
    A(f'{I}<photoshop:Instructions>{esc(lic["instructions"])}</photoshop:Instructions>\n')
    if date_created:
        A(f'{I}<photoshop:DateCreated>{esc(date_created)}T00:00:00</photoshop:DateCreated>\n')
    A(f'{I}<photoshop:AuthorsPosition>{esc(spec.get("authors_position", cr.get("authors_position","")))}</photoshop:AuthorsPosition>\n')
    if spec.get("city"): A(f'{I}<photoshop:City>{esc(spec["city"])}</photoshop:City>\n')
    if spec.get("state"): A(f'{I}<photoshop:State>{esc(spec["state"])}</photoshop:State>\n')
    if spec.get("country"): A(f'{I}<photoshop:Country>{esc(spec["country"])}</photoshop:Country>\n')
    if spec.get("transmission_reference"):
        A(f'{I}<photoshop:TransmissionReference>{esc(spec["transmission_reference"])}</photoshop:TransmissionReference>\n')
    if spec.get("headline"): A(f'{I}<photoshop:Headline>{esc(spec["headline"])}</photoshop:Headline>\n')
    credit = cr["name"] + (f' (ISNI: {ids["isni_spaced"]})' if ids.get("isni_spaced") else "")
    A(f'{I}<photoshop:Credit>{esc(credit)}</photoshop:Credit>\n')
    A(f'{I}<photoshop:Source>{esc(creator_full)}</photoshop:Source>\n')
    A(f'{I}<photoshop:CaptionWriter>{esc(creator_full)}</photoshop:CaptionWriter>\n')
    A(f'{I}<photoshop:ColorMode>3</photoshop:ColorMode>\n')

    # --- dc ---
    A(f'{I}<dc:format>{esc(mime)}</dc:format>\n')
    A(f'{I}<dc:type>{esc(spec.get("dc_type","StillImage"))}</dc:type>\n')
    guid = spec.get("image_guid") or ("urn:uuid:" + str(uuid.uuid4()))
    A(f'{I}<dc:identifier>{esc(guid)}</dc:identifier>\n')
    if spec.get("title"): A(alt_block("dc:title", spec["title"], I))
    A(bag_block("dc:subject", kw_u, I))
    A(f'{I}<dc:creator>\n{I}   <rdf:Seq>\n{I}      <rdf:li>{esc(cr["name"])}</rdf:li>\n{I}   </rdf:Seq>\n{I}</dc:creator>\n')
    A(alt_block("dc:rights", rights_line, I))
    if spec.get("description"): A(alt_block("dc:description", spec["description"], I))

    # --- Iptc4xmpCore ---
    if spec.get("country_code"): A(f'{I}<Iptc4xmpCore:CountryCode>{esc(spec["country_code"])}</Iptc4xmpCore:CountryCode>\n')
    if spec.get("sublocation"): A(f'{I}<Iptc4xmpCore:Location>{esc(spec["sublocation"])}</Iptc4xmpCore:Location>\n')
    if spec.get("intellectual_genre"): A(f'{I}<Iptc4xmpCore:IntellectualGenre>{esc(spec["intellectual_genre"])}</Iptc4xmpCore:IntellectualGenre>\n')
    A(f'{I}<Iptc4xmpCore:CreatorContactInfo rdf:parseType="Resource">\n')
    if ct.get("country"): A(f'{I}   <Iptc4xmpCore:CiAdrCtry>{esc(ct["country"])}</Iptc4xmpCore:CiAdrCtry>\n')
    if ct.get("city"): A(f'{I}   <Iptc4xmpCore:CiAdrCity>{esc(ct["city"])}</Iptc4xmpCore:CiAdrCity>\n')
    if ct.get("email"): A(f'{I}   <Iptc4xmpCore:CiEmailWork>{esc(ct["email"])}</Iptc4xmpCore:CiEmailWork>\n')
    if ct.get("url"): A(f'{I}   <Iptc4xmpCore:CiUrlWork>{esc(ct["url"])}</Iptc4xmpCore:CiUrlWork>\n')
    A(f'{I}</Iptc4xmpCore:CreatorContactInfo>\n')
    if spec.get("alt_text"): A(alt_block("Iptc4xmpCore:AltTextAccessibility", spec["alt_text"], I))
    if spec.get("ext_description"): A(alt_block("Iptc4xmpCore:ExtDescrAccessibility", spec["ext_description"], I))
    if spec.get("subject_codes"): A(code_bag("Iptc4xmpCore:SubjectCode", spec["subject_codes"], I))
    if spec.get("scene_codes"): A(code_bag("Iptc4xmpCore:Scene", spec["scene_codes"], I))

    # --- xmpMM ---
    iid = "xmp.iid:" + str(uuid.uuid4()); did = "xmp.did:" + str(uuid.uuid4())
    odid = uuid.uuid4().hex.upper()
    A(f'{I}<xmpMM:OriginalDocumentID>{odid}</xmpMM:OriginalDocumentID>\n')
    A(f'{I}<xmpMM:InstanceID>{iid}</xmpMM:InstanceID>\n')
    A(f'{I}<xmpMM:DocumentID>{did}</xmpMM:DocumentID>\n')
    A(f'{I}<xmpMM:History>\n{I}   <rdf:Seq>\n{I}      <rdf:li rdf:parseType="Resource">\n'
      f'{I}         <stEvt:action>saved</stEvt:action>\n'
      f'{I}         <stEvt:instanceID>{iid}</stEvt:instanceID>\n'
      f'{I}         <stEvt:when>{meta_ts}</stEvt:when>\n'
      f'{I}         <stEvt:softwareAgent>{esc(dfl.get("creator_tool","ExifTool"))}</stEvt:softwareAgent>\n'
      f'{I}      </rdf:li>\n{I}   </rdf:Seq>\n{I}</xmpMM:History>\n')

    # --- xmpRights ---
    web_stmt = lic.get("web_statement") or lic.get("deed")
    if web_stmt: A(f'{I}<xmpRights:WebStatement>{esc(web_stmt)}</xmpRights:WebStatement>\n')
    A(f'{I}<xmpRights:Marked>{esc(spec.get("rights_marked", True))}</xmpRights:Marked>\n')
    owner = rights.get("owner") or creator_full
    if owner: A(bag_block("xmpRights:Owner", [owner], I))
    ut = lic.get("usage_terms") or lic.get("url")
    if ut: A(alt_block("xmpRights:UsageTerms", ut, I))

    # --- Iptc4xmpExt ---
    A(f'{I}<Iptc4xmpExt:DigitalSourceType>{esc(dst_leaf)}</Iptc4xmpExt:DigitalSourceType>\n')
    if is_ai:  # IPTC 2025.1 AI-generation disclosure
        if spec.get("ai_system_used"): A(f'{I}<Iptc4xmpExt:AISystemUsed>{esc(spec["ai_system_used"])}</Iptc4xmpExt:AISystemUsed>\n')
        if spec.get("ai_system_version"): A(f'{I}<Iptc4xmpExt:AISystemVersionUsed>{esc(spec["ai_system_version"])}</Iptc4xmpExt:AISystemVersionUsed>\n')
        if spec.get("ai_prompt"): A(f'{I}<Iptc4xmpExt:AIPromptInformation>{esc(spec["ai_prompt"])}</Iptc4xmpExt:AIPromptInformation>\n')
        if spec.get("ai_prompt_writer"): A(f'{I}<Iptc4xmpExt:AIPromptWriterName>{esc(spec["ai_prompt_writer"])}</Iptc4xmpExt:AIPromptWriterName>\n')
    if w: A(f'{I}<Iptc4xmpExt:MaxAvailWidth>{esc(w)}</Iptc4xmpExt:MaxAvailWidth>\n')
    if h: A(f'{I}<Iptc4xmpExt:MaxAvailHeight>{esc(h)}</Iptc4xmpExt:MaxAvailHeight>\n')
    if persons: A(bag_block("Iptc4xmpExt:PersonInImage", persons, I))
    # PersonInImageWDetails (linked-data): from known_persons registry / persons_details
    wd = []
    for nm in persons:
        d = resolve_person(nm, profile, spec)
        if d.get("ids") or d.get("description"):
            wd.append(d)
    if wd:
        A(f'{I}<Iptc4xmpExt:PersonInImageWDetails>\n{I}   <rdf:Bag>\n')
        for d in wd:
            A(f'{I}      <rdf:li rdf:parseType="Resource">\n')
            if d.get("ids"):
                A(f'{I}         <Iptc4xmpExt:PersonId>\n{I}            <rdf:Bag>\n')
                for u in d["ids"]:
                    A(f'{I}               <rdf:li>{esc(u)}</rdf:li>\n')
                A(f'{I}            </rdf:Bag>\n{I}         </Iptc4xmpExt:PersonId>\n')
            A(f'{I}         <Iptc4xmpExt:PersonName>\n{I}            <rdf:Alt>\n'
              f'{I}               <rdf:li xml:lang="x-default">{esc(d.get("name",""))}</rdf:li>\n'
              f'{I}            </rdf:Alt>\n{I}         </Iptc4xmpExt:PersonName>\n')
            if d.get("description"):
                A(f'{I}         <Iptc4xmpExt:PersonDescription>\n{I}            <rdf:Alt>\n'
                  f'{I}               <rdf:li xml:lang="x-default">{esc(d["description"])}</rdf:li>\n'
                  f'{I}            </rdf:Alt>\n{I}         </Iptc4xmpExt:PersonDescription>\n')
            A(f'{I}      </rdf:li>\n')
        A(f'{I}   </rdf:Bag>\n{I}</Iptc4xmpExt:PersonInImageWDetails>\n')

    def location_bag(tag, loc):
        inner = ""
        for k, xtag in [("city","City"),("sublocation","Sublocation"),("state","ProvinceState"),
                        ("country","CountryName"),("country_code","CountryCode"),("world_region","WorldRegion")]:
            if loc.get(k): inner += f'{I}         <Iptc4xmpExt:{xtag}>{esc(loc[k])}</Iptc4xmpExt:{xtag}>\n'
        if not inner: return ""
        return (f'{I}<{tag}>\n{I}   <rdf:Bag>\n{I}      <rdf:li rdf:parseType="Resource">\n{inner}{I}      </rdf:li>\n{I}   </rdf:Bag>\n{I}</{tag}>\n')

    loc = spec.get("location_created") or {
        "city": spec.get("city"), "country": spec.get("country"),
        "country_code": spec.get("country_code"), "state": spec.get("state"),
        "sublocation": spec.get("sublocation"), "world_region": dfl.get("world_region")}
    lc = location_bag("Iptc4xmpExt:LocationCreated", loc)
    if lc: A(lc)
    for shown in (spec.get("location_shown") or []):
        A(location_bag("Iptc4xmpExt:LocationShown", shown))

    if spec.get("media_topics"):
        A(f'{I}<Iptc4xmpExt:AboutCvTerm>\n{I}   <rdf:Bag>\n')
        for c in spec["media_topics"]:
            c = str(c).strip(); name = _medtop_label(c)
            A(f'{I}      <rdf:li rdf:parseType="Resource">\n'
              f'{I}         <Iptc4xmpExt:CvId>http://cv.iptc.org/newscodes/mediatopic/</Iptc4xmpExt:CvId>\n'
              f'{I}         <Iptc4xmpExt:CvTermId>http://cv.iptc.org/newscodes/mediatopic/{c}</Iptc4xmpExt:CvTermId>\n')
            if name:
                A(f'{I}         <Iptc4xmpExt:CvTermName>\n{I}            <rdf:Alt>\n'
                  f'{I}               <rdf:li xml:lang="x-default">{esc(name)}</rdf:li>\n'
                  f'{I}            </rdf:Alt>\n{I}         </Iptc4xmpExt:CvTermName>\n')
            A(f'{I}      </rdf:li>\n')
        A(f'{I}   </rdf:Bag>\n{I}</Iptc4xmpExt:AboutCvTerm>\n')
    if persons and spec.get("model_age"):
        A(bag_block("Iptc4xmpExt:ModelAge", [spec["model_age"]], I))

    # --- PLUS ---
    def plus_seq(tag, fields):
        inner = "".join(f'{I}         <{k}>{esc(v)}</{k}>\n' for k, v in fields if v)
        return (f'{I}<{tag}>\n{I}   <rdf:Seq>\n{I}      <rdf:li rdf:parseType="Resource">\n{inner}{I}      </rdf:li>\n{I}   </rdf:Seq>\n{I}</{tag}>\n')
    if persons:
        A(f'{I}<plus:ModelReleaseStatus>{esc(plus.get("model_release_status",""))}</plus:ModelReleaseStatus>\n')
        A(f'{I}<plus:MinorModelAgeDisclosure>{esc(plus.get("minor_model_age_disclosure",""))}</plus:MinorModelAgeDisclosure>\n')
    A(f'{I}<plus:PropertyReleaseStatus>{esc(plus.get("property_release_status",""))}</plus:PropertyReleaseStatus>\n')
    A(plus_seq("plus:ImageSupplier", [("plus:ImageSupplierName", plus.get("supplier_name")),
                                      ("plus:ImageSupplierID", plus.get("supplier_id")),
                                      ("plus:ImageSupplierImageID", spec.get("supplier_image_id"))]))
    ic = spec.get("image_creator")
    if ic:
        A(plus_seq("plus:ImageCreator", [("plus:ImageCreatorName", ic.get("name")), ("plus:ImageCreatorID", ic.get("id"))]))
    A(plus_seq("plus:CopyrightOwner", [("plus:CopyrightOwnerName", plus.get("copyright_owner_name")), ("plus:CopyrightOwnerID", plus.get("copyright_owner_id"))]))
    A(plus_seq("plus:Licensor", [("plus:LicensorName", plus.get("licensor_name")), ("plus:LicensorID", plus.get("licensor_id")), ("plus:LicensorEmail", plus.get("licensor_email")), ("plus:LicensorURL", spec.get("licensor_url"))]))

    # --- dcterms / xmp ---
    if spec.get("provenance"): A(f'{I}<dcterms:provenance>{esc(spec["provenance"])}</dcterms:provenance>\n')
    A(f'{I}<xmp:MetadataDate>{meta_ts}</xmp:MetadataDate>\n')
    A(f'{I}<xmp:CreatorTool>{esc(dfl.get("creator_tool","ExifTool"))}</xmp:CreatorTool>\n')
    A(f'{I}<xmp:ModifyDate>{meta_ts}</xmp:ModifyDate>\n')

    # --- exif / tiff (+ GPS) ---
    A(f'{I}<exif:ExifVersion>0231</exif:ExifVersion>\n')
    if date_created: A(f'{I}<exif:DateTimeOriginal>{esc(date_created)}T00:00:00{tz}</exif:DateTimeOriginal>\n')
    if w: A(f'{I}<exif:PixelXDimension>{esc(w)}</exif:PixelXDimension>\n')
    if h: A(f'{I}<exif:PixelYDimension>{esc(h)}</exif:PixelYDimension>\n')
    gps = spec.get("gps") or {}
    if gps.get("lat") is not None and gps.get("lon") is not None:
        A(f'{I}<exif:GPSLatitude>{esc(_gps(gps["lat"], True))}</exif:GPSLatitude>\n')
        A(f'{I}<exif:GPSLongitude>{esc(_gps(gps["lon"], False))}</exif:GPSLongitude>\n')
        if gps.get("alt") is not None:
            A(f'{I}<exif:GPSAltitude>{esc(gps["alt"])}</exif:GPSAltitude>\n')
            A(f'{I}<exif:GPSAltitudeRef>{esc(0 if float(gps["alt"])>=0 else 1)}</exif:GPSAltitudeRef>\n')
    A(f'{I}<tiff:Orientation>1</tiff:Orientation>\n')
    if w: A(f'{I}<tiff:ImageWidth>{esc(w)}</tiff:ImageWidth>\n')
    if h: A(f'{I}<tiff:ImageLength>{esc(h)}</tiff:ImageLength>\n')

    A(bag_block("lr:hierarchicalSubject", kw_u, I))
    A('      </rdf:Description>\n   </rdf:RDF>\n</x:xmpmeta>\n')
    A('<?xpacket end="w"?>\n')
    return "".join(out)

SCHEMA = {
    "descriptive": ["title","headline","description","alt_text","ext_description","keywords","intellectual_genre"],
    "classification": ["subject_codes (legacy 8-digit)","scene_codes (6-digit)","media_topics (medtop 8-digit)"],
    "location": ["city","state","country","country_code","sublocation",
                 "location_created{city,state,country,country_code,sublocation,world_region}",
                 "location_shown[ {..same..} ]","gps{lat,lon,alt}"],
    "people": ["persons_in_image[]","model_age","image_creator{name,id}",
               "persons_details[{name,ids[],description}]  (or use profile known_persons)"],
    "ai_disclosure_2025.1": ["digital_source_type: trainedAlgorithmicMedia (etc.)",
                             "ai_system_used","ai_system_version","ai_prompt","ai_prompt_writer"],
    "technical": ["width","height","format","dc_type (default StillImage)","urgency","transmission_reference"],
    "rights_identity": ["license (preset key)","licensor_url","provenance","image_guid","supplier_image_id","rights_marked"],
}

def main():
    ap = argparse.ArgumentParser(description="Render a complete XMP packet from profile + per-photo spec.")
    ap.add_argument("--spec")
    ap.add_argument("--image", help="Optional image to auto-detect width/height/format.")
    ap.add_argument("--profile", help="Private profile copied from reference/author_profile.template.yaml.")
    ap.add_argument("--out")
    ap.add_argument("--print-schema", action="store_true")
    a = ap.parse_args()
    if a.print_schema:
        print(json.dumps(SCHEMA, indent=2)); return 0
    if not a.spec: ap.error("--spec is required (or use --print-schema)")
    if not a.profile:
        ap.error("--profile is required; copy reference/author_profile.template.yaml to a private location first")
    spec = json.load(open(a.spec, encoding="utf-8"))
    try:
        profile = load_profile(a.profile)
        validate_profile(profile)
        xmp = build(spec, profile, image=a.image)
    except ValueError as exc:
        ap.error(str(exc))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(xmp); print(f"wrote {a.out}")
    else:
        sys.stdout.write(xmp)
    return 0

if __name__ == "__main__":
    sys.exit(main())
