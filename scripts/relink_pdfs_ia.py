#!/usr/bin/env python3
"""Replace links to bahr.univie.ac.at/sites/all/txt/... in editions/ by the
archive.org URLs from pdfs.csv (exact, case-insensitive, or via FIX).
Links without a file (e.g. Neue Freie Presse, available on ANNO) stay unchanged.

Run:  python3 -I scripts/relink_pdfs_ia.py [--dry]
"""
import csv,re,sys,unicodedata
from pathlib import Path
from urllib.parse import unquote
from collections import Counter
dry = "--dry" in sys.argv
ia={r["path"]:r["ia_url"] for r in csv.DictReader(open("pdfs.csv",encoding="utf-8"))}
low={k.lower():k for k in ia}
FIX={"/1897_emerson.pdf":"literarni-listy/1897_emerson.pdf",
     "die-zeit/140-altenberg.pdf":"die-zeit/1897-11/140-altenberg.pdf",
     "divadelni/1901_rezie.pdf":"divadelny/1901_rezie.pdf",
     "vossische/1917_ackermann.pdf":"vossische-zeitung/1917_ackermann.pdf",
     # Link und Dateiname weichen ab; geprüft gegen Heft- und Seitenangabe im Text
     "die-zeit/1895-3/30_58--59.pdf":"die-zeit/1895-3/30_58-59.pdf",
     "die-zeit/1895-3/30_60--61.pdf":"die-zeit/1895-3/30_60-61.pdf",
     "die-zeit/1895-3/34_124-125.pdf":"die-zeit/1895-3/34-124_125.pdf",
     "die-zeit/1895-5/53-27.pdf":"die-zeit/1895-5/54-27.pdf",
     "die-zeit/1895-5/53-28.pdf":"die-zeit/1895-5/54-28.pdf",
     "die-zeit/1895-5/58-93.pdf":"die-zeit/1895-5/59-93.pdf",
     "die-zeit/1899-18/223-14.pdf":"die-zeit/1899-18/224-14.pdf"}
LINK=re.compile(r"https?://bahr\.univie\.ac\.at/sites/all/txt/([^\"'<>\s#?]+)([#?][^\"'<>\s]*)?")
done=Counter(); missing=Counter(); files=0
for f in sorted(Path("editions").rglob("*.xml")):
    t=f.read_text(encoding="utf-8")
    def sub(m):
        key=unicodedata.normalize("NFC",unquote(m.group(1)))
        key=FIX.get(key) or (key if key in ia else low.get(key.lower()))
        if key:
            done[key]+=1; return ia[key]+(m.group(2) or "")
        missing[m.group(1)]+=1; return m.group(0)
    n=LINK.sub(sub,t)
    if n!=t:
        files+=1
        if not dry: f.write_text(n,encoding="utf-8")
print(f"replaced {sum(done.values())} links ({len(done)} distinct) in {files} files; unresolved {sum(missing.values())} ({len(missing)} distinct)")
nfp=sum(v for k,v in missing.items() if k.lower().startswith("neue-freie-presse/"))
print("davon NFP:",nfp)
