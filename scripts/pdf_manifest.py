#!/usr/bin/env python3
"""Write pdfs.csv, a manifest of the PDF folder (pdfs/), which is not in git.

The PDFs are hosted on archive.org (item IDENTIFIER, see upload_pdfs_ia.py).
pdfs/ mirrors https://bahr.univie.ac.at/sites/all/txt/, so every file has an
old URL on the Drupal site and a new one on archive.org.

Columns:
  path        path below pdfs/ (Unicode NFC), = file name on archive.org
  bytes       file size
  sha256      checksum, to detect changed or lost files
  ia_url      download URL on archive.org
  old_url     URL on the old site (bahr.univie.ac.at/sites/all/txt/…)
  references  number of links to old_url or ia_url in editions/

Also reports files that will need attention (duplicates, odd names, non-PDFs)
and links in editions/ to sites/all/txt/ for which no local file exists.

Run:  python3 -I scripts/pdf_manifest.py [--pdfs pdfs] [--editions editions] [--out pdfs.csv]
"""
import argparse
import csv
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote, unquote

IDENTIFIER = "hermann-bahr-texte"
IA_BASE = f"https://archive.org/download/{IDENTIFIER}/"
OLD_BASE = "https://bahr.univie.ac.at/sites/all/txt/"
LINK = re.compile(r"(?:https?://bahr\.univie\.ac\.at/sites/all/txt/|https://archive\.org/download/hermann-bahr-texte/)([^\"'<>\s#?]+)")
SAFE = re.compile(r"^[A-Za-z0-9._/-]+$")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def is_junk(p):
    return p.name.lower() == ".ds_store" or p.name.startswith("._")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def edition_links(editions):
    refs = Counter()
    for f in editions.rglob("*.xml"):
        for m in LINK.finditer(f.read_text(encoding="utf-8")):
            refs[nfc(unquote(m.group(1)))] += 1
    return refs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", default="pdfs", type=Path)
    ap.add_argument("--editions", default="editions", type=Path)
    ap.add_argument("--out", default="pdfs.csv", type=Path)
    args = ap.parse_args()

    refs = edition_links(args.editions)
    files = sorted(
        (p for p in args.pdfs.rglob("*") if p.is_file() and not is_junk(p)),
        key=lambda p: nfc(p.relative_to(args.pdfs).as_posix()),
    )

    rows, by_hash = [], defaultdict(list)
    for p in files:
        rel = nfc(p.relative_to(args.pdfs).as_posix())
        digest = sha256(p)
        by_hash[digest].append(rel)
        rows.append({
            "path": rel,
            "bytes": p.stat().st_size,
            "sha256": digest,
            "ia_url": IA_BASE + quote(rel),
            "old_url": OLD_BASE + quote(rel),
            "references": refs.get(rel, 0),
        })

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    total = sum(r["bytes"] for r in rows)
    print(f"{args.out}: {len(rows)} files, {total / 1e9:.2f} GB, "
          f"{sum(1 for r in rows if r['references'])} linked from {args.editions}/")

    present = {r["path"] for r in rows}
    checks = {
        "identical content (duplicates)":
            [" = ".join(v) for v in by_hash.values() if len(v) > 1],
        "names with spaces/special characters (work, but URLs need encoding)":
            [r["path"] for r in rows if not SAFE.match(r["path"])],
        "not *.pdf":
            [r["path"] for r in rows if not r["path"].lower().endswith(".pdf")],
        f"linked in {args.editions}/ but missing in {args.pdfs}/":
            sorted(k for k in refs if k not in present),
    }
    for label, items in checks.items():
        if items:
            print(f"\n{label}: {len(items)}")
            for i in items:
                print(f"  {i}")


if __name__ == "__main__":
    main()
