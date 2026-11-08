#!/usr/bin/env python3
"""Harvest the published content of https://bahr.univie.ac.at/ (Drupal 11) as raw data.

Read-only. Writes into <out>/ (default: raw/):

  jsonapi/<entity>/<bundle>/<id>.json   one JSON:API resource object per file
  index.json                            nid -> type, title, alias, created, changed
  menu.json                             main + footer menu tree, parsed from the homepage HTML
  files/<public path>                   binaries of all file entities
  html/<alias>.html                     HTML snapshot of every node (except events) + view pages

Run:  python3 -I scripts/harvest.py [--out raw] [--skip-html] [--skip-files]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://bahr.univie.ac.at"
UA = "bahr-website-backup/1.0 (Drupal-to-TEI migration)"
DELAY = 0.5

RESOURCES = {
    # resource path: include parameter (related entities resolved into "included")
    "node/page": None,
    "node/article": "field_image,field_tags",
    "node/bibliographie": "field_bibliographie_type",
    "node/image": "field_images",
    "node/list": None,
    "node/event": "field_event_type",  # backup only, timeline exists in ../bahr-zeitleiste
    "taxonomy_term/bibliografie_type": None,
    "taxonomy_term/event_type": None,
    "taxonomy_term/tags": None,
    "media/image": "field_media_image",
    "media/image_vdg": None,
    "media/document": None,
    "media/audio": None,
    "media/video": None,
    "media/remote_video": None,
    "file/file": None,
    "block_content/basic": None,
}
# pages produced by Drupal views (not nodes) – snapshot only
VIEW_PAGES = ["/", "/leben", "/forschungsnotizen", "/bilder", "/textverzeichnis"]

ID_KEYS = ("drupal_internal__nid", "drupal_internal__tid", "drupal_internal__mid",
           "drupal_internal__fid", "drupal_internal__id")


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            time.sleep(DELAY)
            return data if binary else data.decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 406):
                raise
            err = e
        except (urllib.error.URLError, TimeoutError) as e:
            err = e
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"failed: {url}: {err}")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def local_id(obj):
    a = obj.get("attributes", {})
    for k in ID_KEYS:
        if a.get(k) is not None:
            return str(a[k])
    return obj["id"]


def harvest_resource(res, include, out):
    entity, bundle = res.split("/")
    q = {"page[limit]": "50"}
    if include:
        q["include"] = include
    url = f"{BASE}/jsonapi/{res}?{urllib.parse.urlencode(q)}"
    n = 0
    while url:
        try:
            d = json.loads(fetch(url))
        except urllib.error.HTTPError as e:
            print(f"  {res}: HTTP {e.code}, skipped", file=sys.stderr)
            return []
        items = d.get("data", [])
        for obj in items:
            write_json(out / "jsonapi" / entity / bundle / f"{local_id(obj)}.json", obj)
        for inc in d.get("included", []):
            e2, b2 = inc["type"].split("--")
            write_json(out / "jsonapi" / e2 / b2 / f"{local_id(inc)}.json", inc)
        n += len(items)
        url = d.get("links", {}).get("next", {}).get("href")
    print(f"  {res}: {n}")
    return n


class MenuParser(HTMLParser):
    """Builds a tree from <nav id="block-..."> <ul><li><a> structures."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.menus, self.stack, self.nav, self.cur_a = {}, [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "nav" and a.get("id", "").startswith("block-"):
            self.nav = a["id"].removeprefix("block-bootstrap-bahr-")
            root = {"children": []}
            self.menus[self.nav] = root["children"]
            self.stack = [root]
        elif self.nav is None:
            return
        elif tag == "ul" and len(self.stack) > 1:
            self.stack[-1].setdefault("children", [])
        elif tag == "li":
            item = {"label": "", "href": None, "system_path": None, "children": []}
            parent = self.stack[-1]
            item["weight"] = len(parent["children"]) + 1
            parent["children"].append(item)
            self.stack.append(item)
        elif tag == "a" and len(self.stack) > 1:
            self.stack[-1]["href"] = a.get("href")
            self.stack[-1]["system_path"] = a.get("data-drupal-link-system-path")
            self.cur_a = self.stack[-1]

    def handle_endtag(self, tag):
        if self.nav is None:
            return
        if tag == "li":
            self.stack.pop()
        elif tag == "a":
            self.cur_a = None
        elif tag == "nav":
            self.nav = None

    def handle_data(self, data):
        if self.cur_a is not None:
            self.cur_a["label"] = (self.cur_a["label"] + data).strip()


def merge_items(base, new):
    """Drupal renders sub-menus of collapsed items only on pages in their active trail:
    merge the trees seen on all pages."""
    known = {(i["system_path"] or i["href"]): i for i in base}
    for it in new:
        k = it["system_path"] or it["href"]
        if k not in known:
            base.append(it)
            known[k] = it
        else:
            merge_items(known[k]["children"], it["children"])
    for i, it in enumerate(base, 1):
        it["weight"] = i


def harvest_menu(out):
    pages = sorted((out / "html").rglob("*.html")) if (out / "html").exists() else []
    sources = [p.read_text(encoding="utf-8") for p in pages] or [fetch(BASE + "/")]
    menus = {}
    for h in sources:
        p = MenuParser()
        p.feed(h)
        for k in ("main-menu", "footer"):
            merge_items(menus.setdefault(k, []), p.menus.get(k, []))
    write_json(out / "menu.json", menus)
    count = lambda items: sum(1 + count(i["children"]) for i in items)
    print(f"  menu: {', '.join(f'{k} ({count(v)} Einträge)' for k, v in menus.items())} aus {len(sources)} Seiten")


def build_index(out):
    idx = {}
    for f in sorted((out / "jsonapi" / "node").glob("*/*.json")):
        o = json.loads(f.read_text(encoding="utf-8"))
        a = o["attributes"]
        idx[str(a["drupal_internal__nid"])] = {
            "type": o["type"].split("--")[1], "title": a["title"],
            "alias": (a.get("path") or {}).get("alias"),
            "created": a["created"], "changed": a["changed"],
        }
    write_json(out / "index.json", dict(sorted(idx.items(), key=lambda kv: int(kv[0]))))
    return idx


def safe_rel(path):
    rel = Path(urllib.parse.unquote(path.lstrip("/")))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe path {path}")
    return rel


def harvest_files(out):
    n = 0
    for f in sorted((out / "jsonapi" / "file" / "file").glob("*.json")):
        url = json.loads(f.read_text(encoding="utf-8"))["attributes"]["uri"]["url"]
        target = out / "files" / safe_rel(url.removeprefix("/sites/default/files/"))
        if target.exists():
            continue
        try:
            data = fetch(BASE + urllib.parse.quote(url), binary=True)
        except urllib.error.HTTPError as e:
            print(f"  file {url}: HTTP {e.code}", file=sys.stderr)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        n += 1
    print(f"  files: {n} downloaded")


def harvest_sites_all(out):
    """Files linked from node bodies that live in /sites/all/ (not Drupal file entities):
    PDFs of the Kritische Schriften, full texts, indices, old images."""
    import re
    paths = set()
    for f in (out / "jsonapi" / "node").glob("*/*.json"):
        body = (json.loads(f.read_text(encoding="utf-8"))["attributes"].get("body") or {}).get("value") or ""
        for h in re.findall(r'(?:href|src)\s*=\s*"([^"]*)"', body):
            h = h.strip().strip("\"'“”„ ")
            m = re.match(r"^(?:https?://(?:bahr\.univie\.ac\.at|(?:www\.)?univie\.ac\.at/bahr))?(/sites/all/[^#?]+)$", h)
            if m:
                paths.add(urllib.parse.unquote(m.group(1)))
    missing, n = [], 0
    for p in sorted(paths):
        target = out / "sites-all" / safe_rel(p.removeprefix("/sites/all/"))
        if target.exists():
            continue
        try:
            data = fetch(BASE + urllib.parse.quote(p), binary=True)
        except urllib.error.HTTPError as e:
            missing.append(f"{e.code}\t{p}")
            continue
        except RuntimeError as e:
            missing.append(f"ERR\t{p}\t{e}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        n += 1
        if n % 100 == 0:
            print(f"  sites-all: {n} …", flush=True)
    (out / "sites-all-missing.tsv").write_text("".join(x + "\n" for x in missing), encoding="utf-8")
    print(f"  sites-all: {len(paths)} verlinkt, {n} neu geladen, {len(missing)} nicht abrufbar (sites-all-missing.tsv)")


def harvest_html(out, idx):
    paths = VIEW_PAGES + [v["alias"] or f"/node/{nid}" for nid, v in idx.items() if v["type"] != "event"]
    n = 0
    for p in paths:
        target = out / "html" / (safe_rel(p if p != "/" else "/index").as_posix() + ".html")
        if target.exists():
            continue
        try:
            html = fetch(BASE + urllib.parse.quote(p))
        except urllib.error.HTTPError as e:
            print(f"  html {p}: HTTP {e.code}", file=sys.stderr)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        n += 1
    print(f"  html: {n} pages")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="raw")
    ap.add_argument("--skip-html", action="store_true")
    ap.add_argument("--skip-files", action="store_true")
    ap.add_argument("--menu-only", action="store_true", help="rebuild menu.json from raw/html only")
    ap.add_argument("--sites-all-only", action="store_true",
                    help="only download files linked below /sites/all/ (not part of the default run)")
    args = ap.parse_args()
    out = Path(args.out)
    if args.menu_only:
        harvest_menu(out)
        return
    if args.sites_all_only:
        harvest_sites_all(out)
        return
    print("jsonapi")
    for res, inc in RESOURCES.items():
        harvest_resource(res, inc, out)
    idx = build_index(out)
    print(f"  index: {len(idx)} nodes")
    if not args.skip_files:
        print("files"); harvest_files(out)
    if not args.skip_html:
        print("html"); harvest_html(out, idx)
    print("menu"); harvest_menu(out)  # needs the HTML snapshot (see merge_items)
    # /sites/all/ (PDFs, ~2–3 GB) is not downloaded by default: use --sites-all-only


if __name__ == "__main__":
    main()
