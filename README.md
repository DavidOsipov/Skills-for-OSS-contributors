# Skills for OSS Contributors

A growing collection of reusable agent skills for contributing to open-source projects and open knowledge ecosystems safely, consistently, and with verifiable workflows.

The repository currently contains one skill for standards-compatible image metadata. Future additions may cover Wikidata and other project-specific OSS contribution workflows.

## Available skills

| Skill                                                | Purpose                                                                                                                                                                       |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [XMP Image Metadata](./xmp-image-metadata/) | Inspect images, prepare verified metadata, reverse-geocode coordinates with privacy controls, and embed standards-compatible XMP, IPTC, EXIF, Dublin Core, and PLUS metadata. |

### Portable XMP Image Metadata

The [`xmp-image-metadata`](./xmp-image-metadata/) skill is designed for careful metadata work across JPEG, PNG, WebP, AVIF, HEIC, TIFF, and other ExifTool-writable formats.

It provides:

* technical image inspection and cross-tool validation;
* metadata generation through a structured author profile and per-image specification;
* XMP embedding with original-file preservation;
* offline-first reverse geocoding and explicit consent before network geocoding;
* IPTC Media Topic and Digital Source Type lookup;
* accessibility descriptions, rights and credit fields, and AI-generated-image disclosure;
* Python scripts with smoke tests, Ruff checks, and mypy type checking.

The skill deliberately does **not** bundle a creator identity or reusable personal profile. Author, rights, contact, location, and provenance data must come from an authorized private profile and image-specific evidence.

See [`xmp-image-metadata/SKILL.md`](./xmp-image-metadata/SKILL.md) for the complete workflow, safety rules, dependencies, and commands.

## Using a skill

Each top-level skill directory is intended to be self-contained. Preserve its internal structure when copying or installing it into an agent environment that supports folder-based skills.

```text
<skill-name>/
├── SKILL.md
├── agents/
├── scripts/
├── reference/
└── tests/
```

Not every future skill will necessarily require every optional directory.

The current skill is identified as:

```text
$xmp-image-metadata
```

A compatible agent can be prompted to use it for tasks such as:

```text
Use $xmp-image-metadata to inspect this image and prepare
standards-compatible metadata without modifying the original.
```

Exact discovery and installation steps depend on the agent host. This repository is the source distribution; the authoritative instructions for each skill live in its own `SKILL.md`.

## Local development

Clone the repository:

```bash
git clone https://github.com/DavidOsipov/Skills-for-OSS-contributors.git
cd Skills-for-OSS-contributors
```

Run the current skill's checks:

```bash
cd xmp-image-metadata
python3 -m pytest tests -q
python3 -m ruff check scripts tests
python3 -m mypy --ignore-missing-imports --disallow-untyped-defs scripts
```

The image-metadata workflow also depends on ExifTool 12.46+, ImageMagick, MediaInfo, Pillow, and PyYAML. Run its preflight before using the scripts:

```bash
python3 scripts/inspect_image.py --check
```

## Design principles

Skills in this repository should:

1. encode a concrete, repeatable contribution workflow rather than a vague prompt;
2. distinguish verified facts from guesses, inherited metadata, and model inference;
3. minimize destructive actions and preserve original inputs by default;
4. keep credentials, personal profiles, and project secrets outside distributable skill folders;
5. prefer authoritative project documentation, specifications, and machine-readable references;
6. make network access and privacy-sensitive actions explicit;
7. include validation, failure conditions, and tests where executable tooling is provided.

## Planned directions

Potential future skills include:

* Wikidata item creation and editing;
* statement sourcing, reference quality, and identifier reconciliation;
* Wikimedia Commons media preparation and metadata review;
* project-specific contribution, issue-triage, and pull-request workflows;
* reusable validation and provenance workflows for other open-source ecosystems.

These are directions for the collection, not a release commitment.

## Contributing

Issues and pull requests are welcome.

For a new skill, keep the scope narrow, document its trigger conditions and stop conditions, cite authoritative references, and avoid embedding contributor-specific identity or credentials. Executable helpers should use safe defaults and include proportionate tests.

Changes to bundled standards or vocabularies should record their source and version so that reviewers can verify what changed.

## License

This repository is licensed under the [MIT License](./LICENSE).

Copyright © 2026 David Osipov.
