#!/usr/bin/env python3
"""Search the bundled IPTC controlled vocabularies by keyword.

Vocabularies (in ../reference/):
  subject   iptc_subject_codes.tsv        legacy IPTC Subject Codes  (8-digit)
  scene     iptc_scene_codes.tsv          IPTC Scene Codes           (6-digit)
  media     iptc_media_topics.tsv         modern IPTC Media Topics   (medtop 8-digit)
  source    iptc_digital_source_types.tsv Digital Source Type tokens

Only the NUMERIC part of a code goes into XMP (no subj:/scn:/medtop: prefix).

  python3 lookup_codes.py portrait
  python3 lookup_codes.py "product management" --vocab media
  python3 lookup_codes.py 09016000 --vocab subject
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference")
FILES = {
    "subject": "iptc_subject_codes.tsv",
    "scene": "iptc_scene_codes.tsv",
    "media": "iptc_media_topics.tsv",
    "source": "iptc_digital_source_types.tsv",
}

Hit = tuple[int, str, str, str, str, str, str]


def load(vocab: str) -> list[dict[str, str]]:
    path = os.path.join(REF, FILES[vocab])
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def label_of(row: dict[str, str]) -> str:
    return row.get("name") or row.get("prefLabel") or ""


def search(vocab: str, query: str, limit: int) -> list[Hit]:
    q = query.lower().strip()
    hits: list[Hit] = []
    for row in load(vocab):
        code = row.get("code") or row.get("token") or ""
        label = label_of(row)
        defin = row.get("definition", "")
        haystack = f"{code} {label} {defin}".lower()
        if q == code or q in haystack:
            rank = 0 if q == code else (1 if q in label.lower() else 2)
            hits.append(
                (
                    rank,
                    code,
                    label,
                    defin,
                    row.get("broader", ""),
                    row.get("retired", ""),
                    row.get("note", ""),
                )
            )
    hits.sort(key=lambda item: (item[0], item[1]))
    return hits[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Search IPTC vocabularies for classification codes."
    )
    ap.add_argument("query", help="Keyword, phrase, or exact code.")
    ap.add_argument("--vocab", choices=[*FILES, "all"], default="all")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args()
    vocabs = list(FILES) if a.vocab == "all" else [a.vocab]
    any_hit = False
    for vocab in vocabs:
        hits = search(vocab, a.query, a.limit)
        if not hits:
            continue
        any_hit = True
        print(f"\n== {vocab} ==")
        for _, code, label, defin, broader, retired, note in hits:
            extra = f"  (broader={broader})" if broader else ""
            if retired:
                extra += f"  [RETIRED: {note or retired}]"
            shown = (defin[:100] + "…") if len(defin) > 100 else defin
            print(f"  {code}\t{label}{extra}\n\t\t{shown}")
    if not any_hit:
        print(f"No matches for {a.query!r}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
