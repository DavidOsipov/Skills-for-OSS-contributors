---
name: xmp-image-metadata-portable
description: Create, inspect, geocode, and safely embed standards-compatible XMP, IPTC, EXIF, Dublin Core, and PLUS metadata in image files without bundling a person's identity or profile. Use for captioning, tagging, classifying, crediting, licensing, reverse-geocoding GPS coordinates, accessibility descriptions, metadata reading, or AI-generated-image disclosure in JPEG, PNG, WebP, AVIF, HEIC, TIFF, and other ExifTool-writable images; including requests mentioning XMP, IPTC, EXIF, alt text, image copyright, keywords, photo metadata, location lookup, geocoding, or AI disclosure.
---

# Portable XMP Image Metadata

Embed verified, portable metadata in an image. Use the supplied builder rather than hand-authoring XMP.

## Identity and privacy

- This distribution deliberately contains no creator profile or personal data. Never infer a creator, rights holder, license, contact detail, location, person's identity, capture date, or AI provenance from pixels or existing metadata.
- Before building, create a **private** profile from `reference/author_profile.template.yaml` in a user- or project-controlled location, for example `photo-author.yaml`. Do not edit the bundled template and do not add the private profile to a shareable skill package, repository, or output folder unless the user explicitly asks.
- Populate that profile only from durable user information already available in the current context and clearly applicable to the image, or ask the user for each missing value. Confirm before embedding contact details, GPS, names, identifiers, or rights information.
- The builder requires `--profile PATH`; it rejects the template's `[REQUIRED ...]` placeholder. Keep image-specific facts in a separate JSON spec.
- Treat EXIF/IPTC/XMP as editable, untrusted claims. Use them as candidates only; resolve conflicts with user-confirmed evidence, otherwise omit the field.
- Never send GPS coordinates to an online geocoding service without the user’s explicit approval. Reverse-geocoded addresses are nearby map results, not proof of capture or depicted location.
- Preserve the original with `--keep-original` unless the user explicitly authorizes overwriting it.

## Required tools

Run every command in one runtime: `py` on Windows or `python3` on macOS/Linux. Before inspecting, reading, building, or modifying an image, run:

```bash
python3 scripts/inspect_image.py --check
```

It requires PyYAML, Pillow, ExifTool 12.46+, ImageMagick, and MediaInfo. If anything is missing or outdated, stop; propose the smallest platform-appropriate installation command and wait for user approval. Do not continue with a partial workflow.

- Windows: `winget install OliverBetz.ExifTool ImageMagick.ImageMagick MediaArea.MediaInfo`, then `py -m pip install pillow pyyaml`
- macOS: `brew install exiftool imagemagick mediainfo`, then `python3 -m pip install pillow pyyaml`
- Debian/Ubuntu: `sudo apt-get install libimage-exiftool-perl imagemagick mediainfo python3-pil python3-yaml`

Set `ET_EXIFTOOL` to the executable path when ExifTool is not on `PATH`. Windows-installed tools do not satisfy a WSL preflight and vice versa.

## Workflow

1. Inspect pixels with the available image viewer at high detail. Record only visible facts and mark uncertainty. Ask before naming people or adding locations, ownership, license, or AI disclosure.
2. Run a technical analysis before using metadata. It hashes the file, fully decodes it, and cross-checks it through ExifTool, ImageMagick, and MediaInfo:

   ```bash
   python3 scripts/inspect_image.py --image photo.jpg --out technical-report.json
   ```

   A dependency failure, decode error, or unexplained mismatch is a stop condition.
3. Optionally harvest technical candidates. Do not use `--merge` until each field is reviewed or user-confirmed:

   ```bash
   python3 scripts/read_exif.py --image photo.jpg > exif-candidates.json
   ```
   First use ExifTool's **offline** GeoLocation database. It derives the nearest GeoNames feature and never changes the image or spec:

   ```bash
   python3 scripts/geocode.py --image photo.jpg --provider exiftool --out geocode-candidate.json
   ```

   If the local result is unsuitable and the user explicitly approves sending exact GPS online, use an online candidate-only fallback:

   ```bash
   python3 scripts/geocode.py --image photo.jpg --provider nominatim --allow-network \
     --user-agent "image-metadata/1.0 (contact: approved@example.org)" \
     --cache geocode-cache.json --out geocode-candidate.json
   ```

   For geocode.maps.co, use `--provider mapsco`; keep its key only in `GEOCODE_MAPS_CO_API_KEY`, never a command, spec, profile, or repository. Review `suggested_spec_fields` with the user and manually copy only approved values into the spec. The default city-level zoom avoids needless address detail. Use `--endpoint` for a self-hosted or user-approved alternative; never batch public-Nominatim queries. Follow [Nominatim's usage policy](https://operations.osmfoundation.org/policies/nominatim/), including its one-request-per-second limit, identifiable user agent, caching, and attribution requirements.
4. Copy `reference/author_profile.template.yaml` to a private profile location. Fill it from authorized user information; ask for missing creator and license details. Copy `reference/example_spec.json` for each image and use `reference/field_guide.md` for the fields.
5. Optionally find accurate IPTC codes. Prefer Media Topics; Subject Codes are deprecated:

   ```bash
   python3 scripts/lookup_codes.py software --vocab media
   python3 scripts/lookup_codes.py humanEdits --vocab source
   ```

6. Build and embed, preserving a backup. Pass the image to detect dimensions and MIME type:

   ```bash
   python3 scripts/build_xmp.py --profile photo-author.yaml --spec photo.json --image photo.jpg --out photo.xmp
   python3 scripts/embed_xmp.py --xmp photo.xmp --image photo.jpg --keep-original
   python3 scripts/embed_xmp.py --read --image photo.jpg
   ```

7. Compare the embedded XMP with the approved spec. Verify creator, rights, location, accessibility text, codes, and AI disclosure; then keep or remove only the temporary sidecar as appropriate.

## References

- `reference/field_guide.md`: per-image spec fields and mappings.
- `reference/author_profile.template.yaml`: private profile template; copy it before editing.
- `reference/example_spec.json` and `reference/example_spec_ai.json`: generic starting specs.
- `reference/iptc-reference-index.md`: bundled IPTC standard, machine-readable TechReference, mappings, and vocabularies.
- `reference/exiftool-docs/`: format-specific ExifTool references.
- `scripts/geocode.py --help`: reverse-geocoding pipeline; network-off by default, cache and identifiable user agent required for public Nominatim.

Refresh IPTC documents and controlled vocabularies with `python3 scripts/update_iptc_references.py`, then review `reference/iptc/source-manifest.json`.
