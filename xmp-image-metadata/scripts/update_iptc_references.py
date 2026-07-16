#!/usr/bin/env python3
"""Download current official IPTC Photo Metadata references and vocabularies."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "reference"
IPTC_REF = REF / "iptc"

DOCUMENTS = {
    "techreference-2025.1.json": "https://iptc.org/std/photometadata/specification/iptc-pmd-techreference_2025.1.json",
    "techreference-2025.1.yaml": "https://iptc.org/std/photometadata/specification/iptc-pmd-techreference_2025.1.yml",
    "standard-2025.1.html": "https://iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html",
    "user-guide.html": "https://www.iptc.org/std/photometadata/documentation/userguide/",
    "mapping-guidelines-2023.1.html": "https://iptc.org/std/photometadata/documentation/mappingguidelines/",
    "techreference-documentation-1.2.html": "https://iptc.org/std/photometadata/documentation/techreference/",
    "google-images-quick-guide.html": "https://iptc.org/standards/photo-metadata/quick-guide-to-iptc-photo-metadata-and-google-images/",
}

VOCABS = {
    "subject": ("https://cv.iptc.org/newscodes/subjectcode/?format=json&lang=en-US", REF / "iptc_subject_codes.tsv"),
    "scene": ("https://cv.iptc.org/newscodes/scene/?format=json&lang=en-US", REF / "iptc_scene_codes.tsv"),
    "media": ("https://cv.iptc.org/newscodes/mediatopic/?format=json&lang=en-US", REF / "iptc_media_topics.tsv"),
    "source": ("https://cv.iptc.org/newscodes/digitalsourcetype/?format=json&lang=en-US", REF / "iptc_digital_source_types.tsv"),
}


def fetch(url):
    request = Request(url, headers={"User-Agent": "xmp-image-metadata-reference-updater/1.0"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def concepts(payload):
    values = payload["conceptSet"]
    return values.values() if isinstance(values, dict) else values


def text(values):
    if not values:
        return ""
    return values.get("en-US") or values.get("en-GB") or next(iter(values.values()))


def code(concept):
    return concept["qcode"].split(":", 1)[1]


def update_vocab(name, payload, destination):
    rows = list(concepts(payload))
    if name == "media":
        fields = ["code", "prefLabel", "broader", "definition"]
        data = [{"code": code(c), "prefLabel": text(c.get("prefLabel")),
                 "broader": ";".join(c.get("broader", [])), "definition": text(c.get("definition"))}
                for c in rows]
    elif name == "source":
        fields = ["token", "prefLabel", "definition", "retired", "note", "uri", "modified"]
        data = [{"token": code(c), "prefLabel": text(c.get("prefLabel")),
                 "definition": text(c.get("definition")), "retired": c.get("retired", ""),
                 "note": text(c.get("note")), "uri": c["uri"], "modified": c.get("modified", "")}
                for c in rows]
    else:
        fields = ["code", "name", "definition"]
        data = [{"code": code(c), "name": text(c.get("prefLabel")), "definition": text(c.get("definition"))}
                for c in rows]
    data.sort(key=lambda row: row[fields[0]])
    with destination.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(data)
    return len(data), payload.get("dateReleased", "")


def main():
    parser = argparse.ArgumentParser(description="Refresh bundled IPTC sources from official IPTC endpoints.")
    parser.add_argument("--docs-only", action="store_true", help="Refresh standards and guides, not vocabularies.")
    parser.add_argument("--vocabs-only", action="store_true", help="Refresh vocabularies, not standards and guides.")
    args = parser.parse_args()
    if args.docs_only and args.vocabs_only:
        parser.error("--docs-only and --vocabs-only cannot be combined")

    IPTC_REF.mkdir(parents=True, exist_ok=True)
    manifest = {"retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "license": "CC BY 4.0", "documents": {}, "vocabularies": {}}
    if not args.vocabs_only:
        for filename, url in DOCUMENTS.items():
            data = fetch(url)
            (IPTC_REF / filename).write_bytes(data)
            manifest["documents"][filename] = {"source_url": url, "bytes": len(data)}
            print(f"updated {filename}")
    if not args.docs_only:
        for name, (url, destination) in VOCABS.items():
            payload = json.loads(fetch(url))
            count, release = update_vocab(name, payload, destination)
            manifest["vocabularies"][name] = {"source_url": url, "release_timestamp": release,
                                                "entries": count, "file": str(destination.relative_to(ROOT))}
            print(f"updated {destination.name} ({count} entries)")
    (IPTC_REF / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("updated source-manifest.json")


if __name__ == "__main__":
    main()
