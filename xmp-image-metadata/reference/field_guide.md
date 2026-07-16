# Field Guide — per-photo spec

A per-photo spec is a small JSON object. Combined with a private profile copied from
`author_profile.template.yaml` (fixed identity/rights/people), `build_xmp.py` renders
the full XMP. Do not add the completed private profile to a shareable package. See
`example_spec.json` (photo) and `example_spec_ai.json` (AI image). Run
`python3 scripts/build_xmp.py --print-schema` for a field list.

IPTC codes use the NUMERIC part only (e.g. `09016000`, `010100`, `20000763`) —
never the `subj:` / `scn:` / `medtop:` prefix.

## Descriptive
| Field | XMP target | Notes |
|---|---|---|
| `title` | dc:title | Short human title. |
| `headline` | photoshop:Headline | One-line summary. |
| `description` | dc:description | Narrative caption. |
| `alt_text` | Iptc4xmpCore:AltTextAccessibility | Short screen-reader alt (~1 sentence). |
| `ext_description` | Iptc4xmpCore:ExtDescrAccessibility | Long accessible description. |
| `keywords` | dc:subject + lr:hierarchicalSubject | Array; identity keywords merged in automatically. |
| `intellectual_genre` | Iptc4xmpCore:IntellectualGenre | e.g. "Portrait; Headshot". |

## Classification codes
| Field | XMP target | Lookup |
|---|---|---|
| `subject_codes` | Iptc4xmpCore:SubjectCode (legacy) | `lookup_codes.py <kw> --vocab subject` |
| `scene_codes` | Iptc4xmpCore:Scene | `lookup_codes.py <kw> --vocab scene` |
| `media_topics` | Iptc4xmpExt:AboutCvTerm (modern) | `lookup_codes.py <kw> --vocab media` |

## Location
| Field | XMP target |
|---|---|
| `city`, `state`, `country`, `country_code` | photoshop:City / photoshop:State / photoshop:Country / Iptc4xmpCore:CountryCode |
| `sublocation` | Iptc4xmpCore:Location |
| `location_created` `{city,state,country,country_code,sublocation,world_region}` | Iptc4xmpExt:LocationCreated |
| `location_shown` `[ {…same fields…} ]` | Iptc4xmpExt:LocationShown (where the depicted subject is, vs where the shot was taken) |
| `gps` `{lat, lon, alt}` | exif:GPSLatitude / GPSLongitude / GPSAltitude (decimal degrees in; converted to XMP form) |

`country_code` is ISO 3166-1 alpha-2. If `location_created` is omitted it is built
from `city`/`state`/`country`/`country_code`/`sublocation`.

## People
| Field | XMP target | Notes |
|---|---|---|
| `persons_in_image` | Iptc4xmpExt:PersonInImage | Array of names. |
| `persons_details` | Iptc4xmpExt:PersonInImageWDetails | Optional `[{name, ids[], description}]`. Usually unnecessary — if a name matches `known_persons` in the profile, the builder attaches that person's stable IDs (Wikidata/ISNI/ORCID/…) and description automatically. |
| `model_age` | Iptc4xmpExt:ModelAge | Integer; emitted only with a person present. |
| `image_creator` `{name,id}` | plus:ImageCreator | The photographer, if different from the copyright holder. |

Linked-data tip: `PersonInImageWDetails` turns a name string into a graph node by
attaching URIs (Wikidata entity, ISNI, ORCID). Populate `known_persons` once in the
profile and every future photo of that person is auto-linked.

## AI-generated / synthetic media (IPTC 2025.1)
Set `digital_source_type` to an AI value to trigger the AI block:
`trainedAlgorithmicMedia` (fully AI-generated), `compositeWithTrainedAlgorithmicMedia`
(real photo + AI elements), `algorithmicMedia`, `compositeSynthetic`.
| Field | XMP target |
|---|---|
| `ai_system_used` | Iptc4xmpExt:AISystemUsed (e.g. "ChatGPT DALL-E", "Google Gemini") |
| `ai_system_version` | Iptc4xmpExt:AISystemVersionUsed |
| `ai_prompt` | Iptc4xmpExt:AIPromptInformation (positive/negative prompt text) |
| `ai_prompt_writer` | Iptc4xmpExt:AIPromptWriterName (not the image "creator") |

Disclosing AI generation this way is what Meta/Google/Adobe read and is increasingly
required (e.g. EU AI Act). For non-AI photos use `digitalCapture` (default) and the
AI block is omitted.

### digital_source_type tokens (non-AI)
`digitalCapture`, `computationalCapture`, `negativeFilm`, `positiveFilm`, `print`,
`humanEdits`, `algorithmicallyEnhanced`, `digitalCreation`, `dataDrivenMedia`,
`screenCapture`, `virtualRecording`, `composite`, `compositeCapture`.

Do not use retired values such as `minorHumanEdits` (use `humanEdits`) or
`digitalArt` (use `digitalCreation`). Check the current bundled vocabulary with
`lookup_codes.py <token> --vocab source`.
You may also pass a full `http://cv.iptc.org/...` URL.

## Technical
| Field | XMP target | Notes |
|---|---|---|
| `width`, `height` | exif/tiff dims + MaxAvail | Auto-detected from `--image`. |
| `format` | dc:format | Auto-detected. |
| `dc_type` | dc:type | Default "StillImage". |
| `urgency` | photoshop:Urgency | 1–8, default 1. |
| `transmission_reference` | photoshop:TransmissionReference | Job/batch reference. |

## Rights & identity
| Field | XMP target | Notes |
|---|---|---|
| `license` | rights block | Preset key from the private profile, such as `CC-BY-4.0`, `CC-BY-SA-4.0`, `CC-BY-NC-SA-4.0`, `CC0-1.0`, or `All-Rights-Reserved`. Defaults to profile `default_license`. |
| `licensor_url` | plus:LicensorURL | Per-image licensing/landing page. |
| `provenance` | dcterms:provenance | Optional C2PA/CAI manifest URL. |
| `image_guid` | dc:identifier | Stable ID; auto `urn:uuid:…` if omitted. |
| `supplier_image_id` | plus:ImageSupplierImageID | Supplier's own image ID. |
| `rights_marked` | xmpRights:Marked | Default True (rights-managed). |

`xmpRights:Owner` comes from the private profile `rights.owner`. Add an organization-
specific preset to that private profile only after the user confirms its terms.

## Auto-generated (do NOT put in the spec)
`xmpMM:InstanceID/DocumentID/OriginalDocumentID` (fresh UUIDs), `xmp:MetadataDate` /
`ModifyDate` / History timestamp, `exif:DateTimeOriginal` (from `date_created`).
`LegacyIPTCDigest` is intentionally omitted.

## EXIF (camera/technical) — not spec fields
Camera and exposure data (Make, Model, LensModel, ExposureTime, FNumber, ISO,
FocalLength, ColorSpace, Orientation) are **not** set in the spec. They come from the
image's own EXIF and are mirrored into XMP by `embed_xmp.py` (on by default; `--no-sync` to skip). To harvest a
source photo's EXIF (date, GPS, dimensions, camera) for review before building,
use `read_exif.py --image X`; do not use `--merge` until each intended field is approved.
The default embed also writes the
authoritative XMP values back out to EXIF and IPTC-IIM so all three containers agree.
