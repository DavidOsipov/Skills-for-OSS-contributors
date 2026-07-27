# Portable XMP Image Metadata

A portable AI-agent skill for handling image metadata end to end: inspecting the image, understanding what is visibly shown, writing useful alt text and descriptions, preparing verified metadata, reverse-geocoding approved GPS coordinates, embedding standards-compatible XMP/EXIF/IPTC metadata, and validating the final file.

- **Declared skill name:** `$xmp-image-metadata-portable`
- **Repository directory:** `skills/xmp-image-metadata-portable`
- **Source repository:** [DavidOsipov/Skills-for-OSS-contributors](https://github.com/DavidOsipov/Skills-for-OSS-contributors)
- **License:** MIT

The intended way to use this skill is to give the image to a capable AI agent and ask it to complete the whole workflow. Manual operation is possible, but is mainly documented for transparency, debugging, and advanced use.

> [!IMPORTANT]
> The AI should inspect the actual image pixels and write alt text, captions, descriptions, and keywords from what is visibly present. Personal identity, exact location, ownership, rights, license, capture date, and AI provenance must come from user-provided or user-confirmed information rather than guesses.

## What the AI agent does

A capable AI agent can run the entire workflow on the user's behalf. It should:

- hashing and fully decoding an image before modification;
- cross-checking dimensions and technical properties with ExifTool, Pillow, ImageMagick, and MediaInfo;
- harvesting existing EXIF values as reviewable candidates rather than accepted facts;
- generating XMP from a private author profile and a per-image JSON specification;
- embedding XMP while optionally synchronizing compatible EXIF and IPTC-IIM fields;
- preserving the original image during writes;
- reverse-geocoding GPS coordinates offline through ExifTool's GeoLocation database;
- using approved online geocoders only after explicit consent;
- looking up IPTC Media Topics, Scene Codes, Subject Codes, and Digital Source Types;
- recording accessibility descriptions, rights, credits, linked identities, locations, and AI-generation disclosures;
- validating the resulting image or XMP sidecar through ExifTool;
- testing the workflow across JPEG, PNG, WebP, and AVIF.

The toolkit is designed for JPEG, PNG, WebP, AVIF, HEIC/HEIF, TIFF, and other formats writable by the installed ExifTool version.

## Recommended usage: let AI handle everything

You normally should not need to run the individual scripts yourself.

Give the image to an AI agent that can view images, access this skill, and execute its tools. Ask it to:

1. inspect the image pixels and technical structure;
2. understand what is visibly shown;
3. write accurate alt text, a human-readable caption, a longer description, and useful keywords;
4. read existing EXIF/IPTC/XMP only as untrusted candidate data;
5. ask for or use confirmed creator, rights, license, identity, location, and provenance information;
6. create or update the private author profile and per-image specification;
7. select appropriate IPTC Media Topics and Digital Source Type values;
8. reverse-geocode GPS coordinates only when permitted;
9. build and embed the metadata while preserving the original;
10. read the metadata back and validate the final image.

A good default prompt is:

```text
Use $xmp-image-metadata-portable to process this image end to end.

Inspect the actual image and technical metadata. Write accurate alt text,
a concise title, a useful caption, a detailed description, and relevant
keywords based on what is visibly shown.

Use my confirmed personal, creator, rights, license, location, and provenance
information where applicable. Do not guess sensitive facts. Try offline
geocoding first. Before any online geocoding, ask for permission to transmit
the exact coordinates; if the chosen provider requires an API key, tell me
which local environment variable to configure without asking me to paste the
secret into metadata or the repository.

Create or update the private profile and per-image metadata specification,
choose appropriate IPTC classifications, embed the metadata while preserving
the original, then read it back and validate the final image.
```

For a batch of images:

```text
Use $xmp-image-metadata-portable to process all attached images end to end.

Inspect every image individually and create image-specific titles, alt text,
captions, detailed descriptions, and keywords. Reuse my confirmed author and
rights information, but do not copy scene descriptions, locations, people,
or classifications between images unless they are actually applicable.

Preserve every original, embed the approved metadata, and validate each final
file. Return a concise report of completed files, warnings, and anything that
still needs my confirmation.
```

The AI should do the repetitive technical work itself. The user should mainly review sensitive facts, resolve uncertainty, and approve the final metadata.

## Safety and privacy model

The workflow deliberately separates reusable identity data from image-specific facts.

### Private author profile

Copy `reference/author_profile.template.yaml` to a private, user- or project-controlled location. The completed profile may contain:

- creator and rights-holder names;
- canonical identifiers;
- contact details;
- license presets;
- PLUS supplier, copyright-owner, and licensor data;
- known-person aliases and stable identifiers;
- default timezone and digital-source type.

A user may ask an AI agent to create, complete, or edit this private profile. The agent should use only information the user has supplied or explicitly confirmed, show or summarize sensitive changes before embedding them, and leave uncertain fields blank rather than guessing.

Do not commit or redistribute a completed private profile unless its owner explicitly authorizes that disclosure.

### Per-image specification

Each image uses a separate JSON specification containing only the approved facts for that image, such as:

- title, headline, caption, and keywords;
- alt text and extended accessibility description;
- capture or depicted location;
- GPS coordinates;
- people shown;
- IPTC classification codes;
- license selection;
- AI-generation disclosure;
- stable image and provenance identifiers.

A user may likewise ask an AI agent to draft, revise, translate, or enrich these per-image fields. The AI may help write captions, alt text, keywords, accessibility descriptions, classifications, credits, rights statements, and other metadata, but factual or privacy-sensitive values must remain subject to user review.

### Guardrails

- Existing EXIF, IPTC, and XMP values are candidates, not proof.
- GPS coordinates are never sent online without `--allow-network`.
- Live geocoding also requires an identifiable user agent and a writable cache.
- Online geocoding keys are read from environment variables, not command arguments.
- Reverse-geocoded places are nearby map matches, not proof of capture or depicted location.
- The profile template's required placeholder is rejected by the builder.
- Unknown or retired controlled-vocabulary values are rejected where applicable.
- XML-illegal control characters are stripped and all XML text is escaped.
- Paths are converted to absolute paths before being passed to ExifTool, preventing dash-leading filenames from being interpreted as options.
- Subprocesses use argument lists and never invoke a shell.
- Validation warnings are treated as failures requiring review.
- Use `--keep-original` unless overwriting has been explicitly approved.

## Requirements

### Required

- Python 3.9 or later
- [ExifTool](https://exiftool.org/) 12.46 or later
- [Pillow](https://pillow.readthedocs.io/)
- [PyYAML](https://pyyaml.org/)

ExifTool 13.00 or later is recommended for reliable AVIF and HEIC/HEIF writing.

### Optional cross-checkers

- [ImageMagick](https://imagemagick.org/)
- [MediaInfo](https://mediaarea.net/en/MediaInfo)

Their absence does not block the ExifTool-centered workflow.

## Installation

Clone the repository and enter the skill directory:

```bash
git clone https://github.com/DavidOsipov/Skills-for-OSS-contributors.git
cd Skills-for-OSS-contributors/xmp-image-metadata
```

Install the required dependencies for your platform.

### Windows

```powershell
winget install OliverBetz.ExifTool
py -m pip install pillow pyyaml
```

Use `py` instead of `python3` in the commands below.

### macOS

```bash
brew install exiftool
python3 -m pip install pillow pyyaml
```

### Debian or Ubuntu

```bash
sudo apt-get update
sudo apt-get install libimage-exiftool-perl python3-pil python3-yaml
```

When ExifTool is not on `PATH`, set `ET_EXIFTOOL` to its executable or Perl-script path:

```bash
export ET_EXIFTOOL=/path/to/exiftool
```

A Windows installation does not satisfy a WSL preflight, and a WSL installation does not satisfy a native Windows preflight.

## Preflight

Run the dependency check before inspecting or modifying an image:

```bash
python3 scripts/inspect_image.py --check
```

The command exits nonzero when ExifTool, Pillow, or PyYAML is missing or when ExifTool is too old.

## Manual workflow reference

The following commands are primarily for debugging, auditing, development, or users who prefer direct CLI control. For normal use, ask an AI agent to execute these steps.


### 1. Create a private profile

Copy the template outside the shareable skill directory:

```bash
cp reference/author_profile.template.yaml ../photo-author.yaml
```

Edit `../photo-author.yaml` and replace the required creator placeholder. Add only authorized identity, contact, rights, and identifier information.

### 2. Create a per-image specification

```bash
cp reference/example_spec.json photo.json
```

Edit `photo.json` with facts verified for the image. For an AI-generated image, begin with:

```bash
cp reference/example_spec_ai.json photo.json
```

Print the complete supported field list at any time:

```bash
python3 scripts/build_xmp.py --print-schema
```

### 3. Inspect the source image

```bash
python3 scripts/inspect_image.py \
  --image photo.jpg \
  --out technical-report.json
```

Stop before modification when the image cannot be fully decoded or when an unexplained technical mismatch appears.

### 4. Build the XMP sidecar

```bash
python3 scripts/build_xmp.py \
  --profile ../photo-author.yaml \
  --spec photo.json \
  --image photo.jpg \
  --out photo.xmp
```

Passing `--image` allows the builder to detect the dimensions, MIME type, and a valid existing native EXIF version.

### 5. Embed the XMP and preserve the original

```bash
python3 scripts/embed_xmp.py \
  --xmp photo.xmp \
  --image photo.jpg \
  --keep-original
```

By default, the embedder also synchronizes compatible descriptive, rights, date, location, dimension, and camera fields between XMP, EXIF, and IPTC-IIM.

To embed only the XMP packet:

```bash
python3 scripts/embed_xmp.py \
  --xmp photo.xmp \
  --image photo.jpg \
  --keep-original \
  --no-sync
```

### 6. Read back the embedded XMP

```bash
python3 scripts/embed_xmp.py --read --image photo.jpg
```

### 7. Validate the final image

```bash
python3 scripts/validate_metadata.py \
  --image photo.jpg \
  --require-xmp
```

Do not publish the file until the report returns `"valid": true` and the approved fields match the intended specification.

## Detailed workflow

### Technical inspection

`inspect_image.py` produces a JSON report containing:

- file size and SHA-256 digest;
- full Pillow verification and pixel decode;
- format, dimensions, color mode, frame count, transparency, ICC profile size, and embedded EXIF size;
- ExifTool file, EXIF, and ICC values;
- optional ImageMagick and MediaInfo cross-checks;
- a dimension-consistency result.

```bash
python3 scripts/inspect_image.py --image photo.avif
```

Internal consistency does not establish authenticity, authorship, date, or location.

### Harvest existing EXIF as candidates

```bash
python3 scripts/read_exif.py --image photo.jpg > exif-candidates.json
```

The output may include dimensions, format, date, GPS, camera, lens, exposure, orientation, color space, software, and the native EXIF version.

To fill only absent keys in an existing specification:

```bash
python3 scripts/read_exif.py \
  --image photo.jpg \
  --merge photo.json \
  > merged-candidate.json
```

`--merge` is convenience, not verification. Review every merged field before using it.

### Reverse-geocode GPS offline

The default provider uses ExifTool's local GeoLocation database and sends nothing over the network:

```bash
python3 scripts/geocode.py \
  --image photo.jpg \
  --provider exiftool \
  --out geocode-candidate.json
```

Coordinates can also be supplied explicitly:

```bash
python3 scripts/geocode.py \
  --lat 41.7151 \
  --lon 44.8271 \
  --provider exiftool
```

The result is candidate JSON only. It never modifies the image or specification.

### Reverse-geocode with an approved online provider

Use online geocoding only after the user explicitly approves transmitting the exact coordinates.

When an AI agent is running the workflow, it must:

1. try the offline ExifTool GeoLocation lookup first;
2. explain that an online provider will receive the image's exact GPS coordinates;
3. ask the user for explicit permission before using `--allow-network`;
4. offer Nominatim when no API key is needed;
5. when `geocode.maps.co` is selected, ask the user to configure an API key in the local `GEOCODE_MAPS_CO_API_KEY` environment variable;
6. never ask the user to place the key in a metadata file, profile, prompt, command argument, or repository;
7. stop rather than silently switching to an online provider when consent or required credentials are missing.

A suitable agent message is:

```text
The offline location lookup was unavailable or insufficient. May I send the
exact GPS coordinates to an online reverse-geocoding service?

Nominatim does not require an API key. geocode.maps.co requires you to set
GEOCODE_MAPS_CO_API_KEY in the local environment. Do not paste the key into
the image metadata, author profile, command line, prompt, or repository.
```

Nominatim example:

```bash
python3 scripts/geocode.py \
  --image photo.jpg \
  --provider nominatim \
  --allow-network \
  --user-agent "image-metadata/1.0 (contact: approved@example.org)" \
  --cache geocode-cache.json \
  --out geocode-candidate.json
```

The default online zoom is city-level. Public Nominatim usage must follow its usage policy, including caching, attribution, an identifiable user agent, and a maximum rate of one request per second. Do not batch public Nominatim requests.

`geocode.maps.co` example:

```bash
export GEOCODE_MAPS_CO_API_KEY="your-key"

python3 scripts/geocode.py \
  --image photo.jpg \
  --provider mapsco \
  --allow-network \
  --user-agent "image-metadata/1.0 (contact: approved@example.org)" \
  --cache geocode-cache.json \
  --out geocode-candidate.json
```

Use `--endpoint` for a self-hosted or separately approved compatible endpoint. HTTP is accepted only for an explicit localhost address; remote endpoints must use HTTPS.

### Look up IPTC controlled vocabularies

Search all bundled vocabularies:

```bash
python3 scripts/lookup_codes.py portrait
```

Search a specific vocabulary:

```bash
python3 scripts/lookup_codes.py software --vocab media
python3 scripts/lookup_codes.py humanEdits --vocab source
python3 scripts/lookup_codes.py 09016000 --vocab subject
```

Available vocabularies:

| Vocabulary | Purpose |
|---|---|
| `media` | Modern IPTC Media Topics |
| `scene` | IPTC Scene Codes |
| `subject` | Legacy IPTC Subject Codes |
| `source` | IPTC Digital Source Type tokens |

Use only the numeric portion of IPTC Media Topic, Scene, and Subject codes in the per-image specification. Do not include `medtop:`, `scn:`, or `subj:` prefixes. Prefer modern Media Topics over deprecated Subject Codes.

### AI-generated and synthetic media disclosure

Set an AI-related `digital_source_type` to emit the IPTC 2025.1 AI block:

```json
{
  "title": "Example AI-generated illustration",
  "description": "A fictional illustrative scene generated with an AI system.",
  "alt_text": "A fictional AI-generated illustration.",
  "keywords": ["AI-generated", "illustration"],
  "digital_source_type": "trainedAlgorithmicMedia",
  "ai_system_used": "Name of the system confirmed by the user",
  "ai_system_version": "",
  "ai_prompt": "",
  "ai_prompt_writer": "",
  "license": "All-Rights-Reserved"
}
```

Recognized AI-oriented source types include:

- `trainedAlgorithmicMedia`
- `compositeWithTrainedAlgorithmicMedia`
- `algorithmicMedia`
- `compositeSynthetic`

For an ordinary camera image, use `digitalCapture`. Metadata disclosure is editable and is not a cryptographic authenticity guarantee.

## Metadata model

The builder combines two inputs.

### Profile fields

The private YAML profile can define:

- creator name, full name, localized names, role, and canonical identifier;
- contact email, URL, city, and country;
- external identifiers and reusable identity keywords;
- rights owner;
- default license and license presets;
- PLUS supplier, copyright-owner, licensor, and release-status fields;
- default creator tool, digital-source type, world region, and timezone;
- known people, aliases, identifiers, and descriptions.

Bundled license presets include:

- `CC-BY-4.0`
- `CC-BY-SA-4.0`
- `CC-BY-NC-SA-4.0`
- `CC0-1.0`
- `All-Rights-Reserved`

### Per-image fields

Major specification groups include:

| Group | Example fields |
|---|---|
| Descriptive | `title`, `headline`, `description`, `alt_text`, `ext_description`, `keywords` |
| Classification | `media_topics`, `scene_codes`, `subject_codes`, `intellectual_genre` |
| Location | `city`, `state`, `country`, `country_code`, `sublocation`, `location_created`, `location_shown`, `gps` |
| People | `persons_in_image`, `persons_details`, `model_age`, `image_creator` |
| AI disclosure | `digital_source_type`, `ai_system_used`, `ai_system_version`, `ai_prompt`, `ai_prompt_writer` |
| Technical | `width`, `height`, `format`, `dc_type`, `urgency`, `transmission_reference` |
| Rights and identity | `license`, `licensor_url`, `provenance`, `image_guid`, `supplier_image_id`, `rights_marked` |

Camera and exposure values are not normal specification inputs. They are preserved from the image's own EXIF and mirrored into XMP during synchronized embedding.

### Automatically generated values

The builder generates or derives:

- XMP document, original-document, and instance UUIDs;
- metadata and modification timestamps with a timezone offset;
- XMP history entries;
- dimensions and MIME type when `--image` is supplied;
- a stable `urn:uuid:` image identifier when one is omitted;
- license text from the selected profile preset;
- a valid native EXIF version when present in the source image.

A standalone XMP sidecar does not invent a native EXIF version. When synchronized embedding must create an EXIF block, the embedder requests the EXIF 3.1 marker `0300`.

## Script reference

| Script | Purpose |
|---|---|
| `scripts/inspect_image.py` | Check dependencies, hash and decode an image, and cross-check technical properties |
| `scripts/read_exif.py` | Export existing EXIF values as untrusted, spec-shaped candidate JSON |
| `scripts/geocode.py` | Produce offline or explicitly approved online reverse-geocoding candidates |
| `scripts/lookup_codes.py` | Search bundled IPTC vocabularies |
| `scripts/build_xmp.py` | Render an XMP packet from a private profile and per-image JSON |
| `scripts/embed_xmp.py` | Embed XMP, optionally synchronize EXIF/IPTC-IIM, read XMP, and preserve a backup |
| `scripts/validate_metadata.py` | Validate an image or sidecar through ExifTool and optionally require XMP |
| `scripts/update_iptc_references.py` | Refresh bundled IPTC documents and controlled vocabularies |

Use each script's built-in help for its complete arguments:

```bash
python3 scripts/geocode.py --help
```

## Standards and implementation

The skill separates three layers:

1. **Semantics:** IPTC, PLUS, XMP, EXIF/CIPA, Dublin Core, and applicable container specifications.
2. **Implementation:** the installed ExifTool version and its format/tag support.
3. **Evidence:** the actual image, readback reports, and user-confirmed facts.

ExifTool is the implementation authority for reading, writing, container-specific storage, tag copying, and validation. The Python scripts do not manually parse JPEG markers, PNG chunks, RIFF boxes, HEIF items, or TIFF/IFD structures.

The generated XMP may use namespaces and structures from:

- Dublin Core;
- IPTC Core and IPTC Extension;
- IPTC 2025.1 AI metadata;
- PLUS;
- Photoshop;
- XMP, XMP Rights, XMP Media Management, and XMP History;
- EXIF and TIFF;
- Dublin Core Terms;
- Lightroom hierarchical subjects.

The public package intentionally excludes restricted ISO and CIPA standards documents. `reference/standards-index.yaml` records acquisition locations and redistribution status.

## Synchronization behavior

By default, `embed_xmp.py`:

- writes the XMP packet;
- copies compatible creator, rights, caption, date, GPS, and dimensions from XMP into EXIF;
- copies compatible creator, rights, caption, keywords, headline, date, and location fields into IPTC-IIM where supported;
- mirrors camera, lens, orientation, exposure, ISO, focal length, and color-space values from native EXIF into XMP;
- preserves an existing valid EXIF version or uses `0300` when creating a new EXIF block;
- verifies that XMP can be read back after writing.

IPTC-IIM storage is expected only in containers supported by ExifTool for that legacy metadata, notably JPEG, PNG, and TIFF.

Use `--no-sync` when only the XMP packet should be written.

## Project structure

```text
xmp-image-metadata/
├── SKILL.md
├── README.md
├── pyproject.toml
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── _common.py
│   ├── build_xmp.py
│   ├── embed_xmp.py
│   ├── geocode.py
│   ├── inspect_image.py
│   ├── lookup_codes.py
│   ├── read_exif.py
│   ├── update_iptc_references.py
│   └── validate_metadata.py
├── reference/
│   ├── author_profile.template.yaml
│   ├── example_spec.json
│   ├── example_spec_ai.json
│   ├── field_guide.md
│   ├── iptc-reference-index.md
│   ├── standards.md
│   ├── standards-index.yaml
│   ├── exiftool-reference.md
│   ├── exiftool-docs/
│   └── bundled IPTC vocabularies and source material
└── tests/
    ├── fixture_profile.yaml
    ├── fixture_spec.json
    └── test_smoke.py
```

The repository may contain additional generated reference files or test fixtures not expanded in this overview.

## Development and tests

Run the smoke test suite:

```bash
python3 -m pytest tests -q
```

Run Ruff:

```bash
python3 -m ruff check scripts tests
```

Run mypy:

```bash
python3 -m mypy \
  --ignore-missing-imports \
  --disallow-untyped-defs \
  scripts
```

The current smoke suite checks, among other things:

- removal and escaping of XML-illegal characters;
- argument-injection-safe path handling;
- well-formed XMP generation;
- rejection of unknown licenses;
- timezone-aware metadata timestamps;
- omission of empty PLUS structures;
- non-invention of a native EXIF version for a standalone sidecar;
- XMP embedding and readback in JPEG, PNG, WebP, and AVIF when dependencies are available;
- synchronization of creator and EXIF dimension/version fields;
- safe processing of filenames beginning with a dash.

Embedding tests skip automatically when ExifTool or Pillow is unavailable.

## Updating IPTC references

Refresh the bundled IPTC material with:

```bash
python3 scripts/update_iptc_references.py
```

Then review:

```text
reference/iptc/source-manifest.json
```

Do not add restricted ISO, CIPA, or other standards documents to the public package without reviewing their redistribution terms.

## Limitations

- The toolkit does not prove authorship, ownership, capture date, location, or authenticity.
- Existing metadata can be stale, edited, forged, or copied from another file.
- Reverse geocoding returns a nearby database or map feature, not evidence of where an image was captured or what it depicts.
- ExifTool validation is not an independent full XMP schema validator.
- AI-disclosure metadata is informative, editable metadata rather than a cryptographic provenance mechanism.
- C2PA or CAI manifests may be linked through a provenance URL, but this toolkit does not create or verify those manifests.
- Actual read/write support depends on the installed ExifTool version and the target container.
- Optional ImageMagick and MediaInfo checks improve cross-tool visibility but do not replace ExifTool's write and validation role.
- A successful technical validation does not establish that the semantic claims are true.

## Using the agent skill

A compatible folder-based agent host can discover the skill from `SKILL.md` and `agents/openai.yaml`.

The simplest instruction is:

```text
Use $xmp-image-metadata-portable to process this image end to end.
Inspect the image, create proper alt text and descriptions, prepare all
appropriate metadata, preserve the original, embed the metadata, and
validate the final file. Ask me only for sensitive or uncertain facts
that cannot be established from the image itself.
```

The AI agent should perform the technical workflow rather than merely explain the commands. It should inspect the image visually, create image-specific text, operate the scripts, review the results, and deliver the completed file plus any warnings or unresolved questions.

Preserve the complete directory structure when copying the skill into another environment. Host-specific installation and discovery paths vary; `SKILL.md` is the authoritative operational instruction file.

## Contributing

Issues and pull requests are welcome in the parent repository.

Contributions should:

- preserve the distinction between verified evidence and inferred or inherited claims;
- keep personal profiles, credentials, and secrets outside the distributable skill;
- use safe, non-destructive defaults;
- make network access and privacy-sensitive operations explicit;
- cite authoritative standards and record reference versions;
- add or update tests when executable behavior changes.

## License

This project is distributed under the [MIT License](../LICENSE).

Copyright © 2026 David Osipov.
