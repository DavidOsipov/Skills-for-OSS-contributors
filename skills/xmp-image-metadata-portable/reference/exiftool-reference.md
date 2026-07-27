# ExifTool implementation reference

The bundled `exiftool_pod.md`/PDF documents cover the CLI; `ExifTool.md`/PDF cover
the Perl API. The scripts use the CLI with argument lists and never invoke a shell.
`source-manifest.json` records the local snapshot hashes.

Preferred operations:

- Read structured metadata with `-j -struct -G1`; use `-n` when numeric values are
  needed and `-X`/`-xmp -b` when the raw XMP packet is needed.
- Check the installed version with `-ver` and writable support with `-listw` or
  `-listwf`; do not assume every ExifTool-writable format has identical XMP/Exif/IPTC
  behavior.
- Copy or reconcile fields with `-tagsFromFile`, explicit source/destination tags,
  and absolute paths. ExifTool's copy operation handles the native storage details.
- Validate after writing with `-validate -warning -error`. A validation warning is
  a review stop for this skill, even when ExifTool exits successfully.
- Keep ExifTool's default `_original` backup unless the user explicitly authorizes
  in-place replacement. Never use `-all=` as part of the normal metadata workflow.

The skill's `embed_xmp.py`, `read_exif.py`, `geocode.py`, and
`validate_metadata.py` centralize these operations. Use the scripts first so path
handling, version checks, encoding, backup behavior, and privacy gates stay aligned.
