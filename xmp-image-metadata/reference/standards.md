# Standards routing

Use ExifTool for implementation: detect the file type, read metadata, write XMP,
copy fields between XMP/Exif/IPTC, validate the result, and handle container-specific
storage. Do not parse JPEG APP markers, PNG chunks, RIFF boxes, HEIF items, or TIFF/IFD
bytes in Python for this skill.

Use the applicable normative source for meaning and representation questions:

1. IPTC TechReference 2025.1 for field meaning, cardinality, type, XMP path, and
   controlled-vocabulary rules.
2. The PLUS XMP reference for PLUS structures and release-status values.
3. XMP Parts 1–3 for RDF/XMP representation, standard schemas, storage, and
   reconciliation when the bundled references do not settle the question.
4. CIPA DC-010-2026 for current Exif-to-XMP mappings, if the user supplies an
   authorized local copy; use CIPA DC-008-2026 for native Exif validity.
5. PNG, WebP, AVIF, HEIF, or ISO Base Media references only for a container-specific
   interoperability question.
6. IPTC-IIM 4.2 only when creating or synchronizing legacy IPTC-IIM.
7. ExifTool documentation for command syntax and supported tag names, never as the
   semantic authority for an IPTC/Exif/PLUS field.

The public package intentionally contains no ISO, CIPA, or other restricted standards
PDFs. `standards-index.yaml` records official acquisition URLs, redistribution status,
and optional local-copy policy. Do not copy a restricted document into the public skill
without reviewing its terms.

Exif version handling is deliberately conservative. The builder preserves a valid
native `EXIF:ExifVersion` when an image is supplied. It does not invent a version in a
standalone XMP sidecar. During a synchronized write, ExifTool preserves an existing
native version; when it has to create the Exif block, the script requests the CIPA 3.1
marker `0300` and also copies `ExifImageWidth`/`ExifImageHeight` from the XMP dimensions.

For a standards question, keep three layers separate:

- semantics: IPTC/PLUS/CIPA/XMP specification;
- implementation: ExifTool version installed on the machine;
- evidence: the actual image, its readback report, and user-confirmed facts.
