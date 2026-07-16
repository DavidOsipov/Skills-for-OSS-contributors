# IPTC reference corpus

Use the current, official IPTC sources bundled in `reference/iptc/`.

| Need | Read |
|---|---|
| Validate fields, types, XMP identifiers, IIM identifiers, ExifTool tags, or structures in code | `techreference-2025.1.json` (preferred) or `techreference-2025.1.yaml` |
| Interpret a property, cardinality, implementation note, or deprecation | `standard-2025.1.html` |
| Choose accurate descriptive, rights, location, accessibility, or image-region values | `user-guide.html` |
| Map IPTC values to Exif or Schema.org | `mapping-guidelines-2023.1.html` |
| Interpret the machine-readable TechReference model | `techreference-documentation-1.2.html` |
| Configure creator, credit, copyright, Web Statement of Rights, or Licensor URL for Google Images | `google-images-quick-guide.html` |

Use the adjacent TSV vocabularies for local lookup. Prefer Media Topics; IPTC labels Subject Codes as deprecated. Use `iptc_digital_source_types.tsv` to select an active Digital Source Type and never emit a value marked `retired`.

`source-manifest.json` records the exact official URLs, release timestamps, entry counts, and retrieval time. All bundled IPTC documentation and NewsCodes are published under CC BY 4.0 according to the source material. Refresh this corpus with:

```bash
python3 scripts/update_iptc_references.py
```

The updater intentionally tracks current documentation used by this skill, not archived historical versions or unrelated IPTC standards.
