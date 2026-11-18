#!/usr/bin/env python3
"""Upload the files listed in pdfs.csv to one archive.org item.

Files keep their folder structure, e.g. pdfs/deutsche-worte/1889_deutsche-worte.pdf
→ https://archive.org/download/hermann-bahr-texte/deutsche-worte/1889_deutsche-worte.pdf

Can be re-run at any time: files already in the item with the same size are
skipped, so an interrupted upload simply continues. Derivatives (OCR text,
book reader) are not queued per file; pass --derive once at the end.

Setup (once):
  pip install internetarchive
  ia configure            # stores your archive.org keys in ~/.config/internetarchive/ia.ini

Run:
  python3 -I scripts/pdf_manifest.py                  # refresh pdfs.csv first
  python3 -I scripts/upload_pdfs_ia.py --dry-run      # show what would be uploaded
  python3 -I scripts/upload_pdfs_ia.py                # upload
  python3 -I scripts/upload_pdfs_ia.py --derive       # upload remaining files, then derive once
"""
import argparse
import csv
import sys
from pathlib import Path

IDENTIFIER = "hermann-bahr-texte"

# Only applied when the item is created (first upload); later changes via
# `ia metadata hermann-bahr-texte --modify="key:value"` or the web interface.
METADATA = {
    "mediatype": "texts",
    "collection": "opensource",
    "title": "Hermann Bahr: Texte in Zeitschriften, Zeitungen und Büchern (Digitalisate)",
    "creator": "Bahr, Hermann, 1863-1934",
    "language": "ger",
    "subject": ["Hermann Bahr", "Wiener Moderne", "Zeitschriften", "Feuilleton"],
    "description": (
        "Digitalisate von Texten Hermann Bahrs und Sekundärliteratur, "
        "gesammelt für die Website „Hermann Bahr“ (bahr.acdh.oeaw.ac.at). "
        "Ordner = Publikationsorgan. "
        "Verzeichnis der Dateien: https://github.com/hermann-bahr/bahr-website-data/blob/main/pdfs.csv"
    ),
    "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="pdfs.csv", type=Path)
    ap.add_argument("--pdfs", default="pdfs", type=Path)
    ap.add_argument("--identifier", default=IDENTIFIER)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--derive", action="store_true",
                    help="queue one derive task for the whole item after uploading")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    try:
        import internetarchive as ia
    except ImportError:
        sys.exit("pip install internetarchive")
    item = ia.get_item(args.identifier)
    existing = {f["name"]: f.get("size") for f in item.files}

    todo = [r for r in rows if existing.get(r["path"]) != r["bytes"]]
    print(f"{args.identifier}: {len(rows)} in manifest, {len(rows) - len(todo)} already uploaded, "
          f"{len(todo)} to upload ({sum(int(r['bytes']) for r in todo) / 1e9:.2f} GB)")

    if args.dry_run:
        for r in todo[:20]:
            print(f"  {r['path']}")
        if len(todo) > 20:
            print(f"  … and {len(todo) - 20} more")
        return

    failed = []
    for n, r in enumerate(todo, 1):
        local = args.pdfs / r["path"]
        print(f"[{n}/{len(todo)}] {r['path']}", flush=True)
        try:
            responses = item.upload(
                {r["path"]: str(local)},
                metadata=METADATA,
                queue_derive=False,
                retries=10,
                retries_sleep=30,
            )
            bad = [x for x in responses if getattr(x, "status_code", 200) >= 400]
            if bad:
                raise RuntimeError(f"HTTP {bad[0].status_code}: {bad[0].text[:200]}")
        except Exception as e:  # keep going, report at the end
            print(f"  FAILED: {e}", flush=True)
            failed.append(r["path"])

    if failed:
        print(f"\n{len(failed)} failed (re-run the script to retry):")
        for p in failed:
            print(f"  {p}")
    elif args.derive:
        ia.get_item(args.identifier).derive()
        print(f"derive queued: https://archive.org/history/{args.identifier}")

    print(f"https://archive.org/details/{args.identifier}")


if __name__ == "__main__":
    main()
