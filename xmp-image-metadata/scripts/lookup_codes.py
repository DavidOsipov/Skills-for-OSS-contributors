#!/usr/bin/env python3
"""
lookup_codes.py - Search the bundled IPTC controlled vocabularies by keyword.

Vocabularies (in ../reference/):
  subject   iptc_subject_codes.tsv   legacy IPTC Subject Codes  (8-digit, e.g. 09016000)
  scene     iptc_scene_codes.tsv     IPTC Scene Codes           (6-digit, e.g. 010100)
  media     iptc_media_topics.tsv    modern IPTC Media Topics   (8-digit medtop, e.g. 20000002)

Only the NUMERIC part of a code goes into XMP (no 'subj:' / 'scn:' / 'medtop:' prefix).

Usage:
  python3 lookup_codes.py portrait
  python3 lookup_codes.py "product management" --vocab media
  python3 lookup_codes.py 09016000 --vocab subject     # exact-code lookup
  python3 lookup_codes.py cyber --vocab media --limit 15
"""
import argparse, csv, os, sys

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference")
FILES = {
    "subject": "iptc_subject_codes.tsv",
    "scene":   "iptc_scene_codes.tsv",
    "media":   "iptc_media_topics.tsv",
    "source":  "iptc_digital_source_types.tsv",
}

def load(vocab):
    path = os.path.join(REF, FILES[vocab])
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))

def label_of(vocab, row):
    return row.get("name") or row.get("prefLabel") or ""

def search(vocab, query, limit):
    q = query.lower().strip()
    hits = []
    for row in load(vocab):
        code = row.get("code") or row.get("token")
        label = label_of(vocab, row)
        defin = row.get("definition", "")
        hay = f"{code} {label} {defin}".lower()
        if q == code or q in hay:
            # rank: exact code > label match > definition match
            rank = 0 if q == code else (1 if q in label.lower() else 2)
            hits.append((rank, code, label, defin, row.get("broader", ""),
                         row.get("retired", ""), row.get("note", "")))
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits[:limit]

def main():
    ap = argparse.ArgumentParser(description="Search IPTC vocabularies for classification codes.")
    ap.add_argument("query", help="Keyword, phrase, or exact code.")
    ap.add_argument("--vocab", choices=list(FILES) + ["all"], default="all")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args()
    vocabs = list(FILES) if a.vocab == "all" else [a.vocab]
    any_hit = False
    for v in vocabs:
        hits = search(v, a.query, a.limit)
        if not hits:
            continue
        any_hit = True
        print(f"\n== {v} ==")
        for _, code, label, defin, broader, retired, note in hits:
            extra = f"  (broader={broader})" if broader else ""
            if retired:
                extra += f"  [RETIRED: {note or retired}]"
            d = (defin[:100] + "…") if len(defin) > 100 else defin
            print(f"  {code}\t{label}{extra}\n\t\t{d}")
    if not any_hit:
        print(f"No matches for {a.query!r}.", file=sys.stderr); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
