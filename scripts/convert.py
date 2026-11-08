#!/usr/bin/env python3
"""Convert the harvested Drupal data (raw/) into TEI files (editions/).

File names follow the menu: menu levels are slugified and joined with "__"
(e.g. briefe__arthur-schnitzler.xml). Entries listed below a menu page
(bibliography entries, images, research notes, derivative pages) get
<parent>__<slug>.xml. Pages that are not reachable from the menu keep their old
alias as file name and are marked <keywords scheme="menu" n="none">.

The menu position is stored in teiHeader/profileDesc/textClass:
  <keywords scheme="menu" n="main-menu"><term n="5" key="briefe">Briefe</term>…</keywords>

Also writes mapping.csv (nid, old alias, new file) and convert-report.txt.

Run:  python3 -I scripts/convert.py [--raw raw] [--out editions]
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from lxml import etree
from lxml import html as lhtml
from lxml.builder import ElementMaker

BASE = "https://bahr.univie.ac.at"
TODAY = date.today().isoformat()
PUBLISHER = "Hermann Bahr (bahr.univie.ac.at)"
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
T = ElementMaker(namespace=TEI_NS, nsmap={None: TEI_NS})

FRONT_PAGE = "1"
EXCLUDE = {"17877", "81341", "49398", "90886"}  # seite-nicht-gefunden, zeitleiste, ueber-die-zeitleiste, textverzeichnis
LABEL_FIXES = {"Gerhart Hauptmanm": "Gerhart Hauptmann"}
BIB_TYPE_PARENT = {  # taxonomy bibliografie_type -> menu node listing these entries
    "Theaterstücke": "49644", "Literarische Prosa": "9596", "Kritische Schriften": "28269",
    "Schriften für das Theater": "9598", "Tagebücher": "9597", "Herausgaben": "22102",
    "Posthume Veröffentlichungen": "49643", "Schriften in Einzelausgaben": "38750",
}
IMAGES_PARENT = "28237"  # Bilder
VIEW_ONLY_MENU = {"forschungsnotizen": "forschung__forschungsnotizen"}  # menu items that are Drupal views
ARTICLES_PARENT = "forschungsnotizen"
TIMELINE_PAGE = "90887"  # Leben – timeline lives in ../bahr-zeitleiste

KNOWN_TAGS = set("""a abbr b blockquote br caption cite code col colgroup dd div dl dt em font h1 h2 h3 h4 h5 h6
hr i img ins del li ol p pre q quote s small span strike strong sub sup table tbody td tfoot th thead tr u ul
drupal-media style meta center""".split())
PHRASE = {"a", "abbr", "b", "cite", "code", "em", "font", "i", "ins", "del", "q", "s", "small", "span",
          "strike", "strong", "sub", "sup", "u", "br", "img", "drupal-media"}
HI_REND = {"i": "italic", "em": "italic", "cite": "italic", "b": "bold", "strong": "bold", "small": "small",
           "sup": "superscript", "sub": "subscript", "u": "underline", "s": "strikethrough",
           "strike": "strikethrough", "del": "strikethrough", "code": "code"}
HEADINGS = {f"h{i}": i for i in range(1, 7)}
WS = re.compile(r"[ \t\n\r\f\v]+")  # not \s: keep non-breaking spaces

report = defaultdict(list)


# ---------------------------------------------------------------- helpers
def slug(s, maxlen=None):
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if maxlen and len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]
    return s


def ncname(s):
    s = re.sub(r"[^\w.\-]", "_", s.strip())
    return s if re.match(r"[^\W\d]", s) else "id_" + s


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append(parent, nodes):
    for n in nodes:
        if isinstance(n, str):
            if len(parent):
                parent[-1].tail = (parent[-1].tail or "") + n
            else:
                parent.text = (parent.text or "") + n
        else:
            parent.append(n)
    return parent


def has_content(el):
    if (el.text or "").strip():
        return True
    return any(c.tag != f"{{{TEI_NS}}}lb" or (c.tail or "").strip() for c in el)


def trim(el):
    """strip leading/trailing whitespace and line breaks inside a mixed-content element"""
    while len(el) and el[-1].tag == f"{{{TEI_NS}}}lb" and not (el[-1].tail or "").strip():
        el.remove(el[-1])
    while len(el) and el[0].tag == f"{{{TEI_NS}}}lb" and not (el.text or "").strip():
        tail = el[0].tail
        el.remove(el[0])
        el.text = (el.text or "") + (tail or "")
    if el.text:
        el.text = el.text.lstrip(" ") or None
    if len(el):
        if el[-1].tail:
            el[-1].tail = el[-1].tail.rstrip(" ") or None
    elif el.text:
        el.text = el.text.rstrip(" ") or None
    return el


def clean_html(s):
    s = s.replace("\r\n", "\n")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f￾￿]", "", s)  # not allowed in XML
    s = re.sub(r"<style\b.*?</style>|<meta\b[^>]*>|<!--.*?-->", "", s, flags=re.S | re.I)
    fixes = [(r"<(/?)df\b", r"<\1dd"), (r"<(/?)bold\b", r"<\1b"), (r"</l>", "</li>"),
             (r"<p(?=[A-ZÄÖÜ])", "<p>"), (r"<t>", "<tr>"), (r"<class=", "<p class=")]
    for a, b in fixes:
        s = re.sub(a, b, s)

    def esc(m):  # pseudo tags like <Wien>, <?>, <Bestellnr. 1> are literal text
        if m.group(2).lower() in KNOWN_TAGS:
            return m.group(0)
        return m.group(0).replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"<(/?)([^\s>/!]+)([^>]*)>", esc, s)


# ---------------------------------------------------------------- site model
class Site:
    def __init__(self, raw):
        self.raw = raw
        self.nodes = {}
        for f in (raw / "jsonapi" / "node").glob("*/*.json"):
            o = load(f)
            self.nodes[str(o["attributes"]["drupal_internal__nid"])] = o
        self.alias2nid = {o["attributes"]["path"]["alias"]: nid for nid, o in self.nodes.items()
                          if (o["attributes"].get("path") or {}).get("alias")}
        self.files = {}  # file uuid -> public path below sites/default/files
        for f in (raw / "jsonapi" / "file" / "file").glob("*.json"):
            o = load(f)
            self.files[o["id"]] = o["attributes"]["uri"]["url"].removeprefix("/sites/default/files/")
        self.media = {}  # media uuid -> (file path, name)
        for f in (raw / "jsonapi" / "media").glob("*/*.json"):
            o = load(f)
            rels = [(k, v["data"]) for k, v in o.get("relationships", {}).items()
                    if isinstance(v.get("data"), dict) and v["data"].get("type") == "file--file"]
            rels.sort(key=lambda kv: kv[0] == "thumbnail")
            if rels:
                self.media[o["id"]] = (self.files.get(rels[0][1]["id"]), o["attributes"].get("name"),
                                       rels[0][1].get("meta", {}).get("alt"))
        self.terms = {}
        for f in (raw / "jsonapi" / "taxonomy_term").glob("*/*.json"):
            o = load(f)
            self.terms[o["id"]] = (o["type"].split("--")[1], o["attributes"]["name"])
        self.menu = load(raw / "menu.json")

    def html_main(self, nid):
        alias = self.nodes[nid]["attributes"]["path"]["alias"] if nid in self.nodes else "/" + nid
        f = self.raw / "html" / (alias.lstrip("/") + ".html")
        if not f.exists():
            return ""
        h = f.read_text(encoding="utf-8")
        m = re.search(r'role="main".*?(?=<footer|$)', h, re.S)
        return m.group(0) if m else h

    def body(self, nid):
        return ((self.nodes[nid]["attributes"].get("body") or {}).get("value")) or ""

    def links_in(self, text):
        """internal node ids linked from html text, in order of first appearance"""
        out = []
        for h in re.findall(r'href="([^"]*)"', text):
            nid = self.nid_for(h)[0]
            if nid and nid not in out:
                out.append(nid)
        return out

    def nid_for(self, href):
        """-> (nid or None, path, fragment) for links pointing into the old site"""
        h = href.strip().strip("\"'“”„ ")
        h = re.sub(r"^https?://(bahr\.univie\.ac\.at|(www\.)?univie\.ac\.at/bahr)", "", h)
        if re.match(r"^[a-z]+:", h):
            return None, None, None
        path, _, frag = h.partition("#")
        path = path.split("?")[0].rstrip("/")
        if path and not path.startswith("/"):
            path = "/" + path
        path = re.sub(r"^/bahr(?=/|$)", "", path)
        m = re.match(r"^/node/(\d+)$", path)
        nid = m.group(1) if m else self.alias2nid.get(path)
        return nid, path, frag


# ---------------------------------------------------------------- mapping
def build_mapping(site):
    """nid -> dict(file, menu, terms, order)"""
    m = {}

    def walk(items, menu_name, trail, prefix):
        for it in items:
            label = LABEL_FIXES.get(it["label"], it["label"])
            key = slug(label)
            terms = trail + [(it["weight"], key, label)]
            name = "__".join(t[1] for t in terms) if menu_name == "main-menu" else key
            sp = it["system_path"] or ""
            if sp.startswith("node/"):
                nid = sp[5:]
                if nid not in EXCLUDE:
                    m[nid] = {"file": name, "menu": menu_name, "terms": terms}
            elif sp in VIEW_ONLY_MENU:
                m["view:" + sp] = {"file": VIEW_ONLY_MENU[sp], "menu": menu_name, "terms": terms, "stub": sp}
            else:
                report["menu-ohne-datei"].append(f"{label} -> {it['href']}")
            walk(it["children"], menu_name, terms, name)

    for menu_name, items in site.menu.items():
        walk(items, menu_name, [], "")
    m[FRONT_PAGE] = {"file": "index", "menu": "front", "terms": []}

    def add_children(parent_key, nids, slugger):
        parent = m[parent_key]
        nids = [n for n in nids if n not in m]  # a menu position always wins
        listing = site.html_main(parent_key) if not parent_key.startswith("view:") else ""
        order = site.links_in(listing) + site.links_in(site.body(parent_key) if parent_key in site.nodes else "")
        nids = sorted(nids, key=lambda n: (order.index(n) if n in order else len(order),
                                           site.nodes[n]["attributes"]["title"]))
        used = set()
        for i, nid in enumerate(nids, 1):
            title = site.nodes[nid]["attributes"]["title"]
            s = slugger(nid)
            base, k = s, 2
            while s in used:
                s, k = f"{base}-{k}", k + 1
            used.add(s)
            m[nid] = {"file": f"{parent['file']}__{s}", "menu": parent["menu"],
                      "terms": parent["terms"] + [(i, s, title)], "child": True}

    title_slug = lambda n: slug(site.nodes[n]["attributes"]["title"], 60)

    # bibliography entries by taxonomy
    by_type = defaultdict(list)
    for nid, o in site.nodes.items():
        if o["type"] == "node--bibliographie" and nid not in m:
            rel = o["relationships"]["field_bibliographie_type"]["data"]
            rel = rel[0] if isinstance(rel, list) and rel else rel
            tname = site.terms.get(rel["id"], (None, None))[1] if rel else None
            if tname in BIB_TYPE_PARENT:
                by_type[BIB_TYPE_PARENT[tname]].append(nid)
            else:
                report["bibliografie-ohne-typ"].append(nid)
    for parent, nids in by_type.items():
        add_children(parent, nids, title_slug)
    add_children(IMAGES_PARENT, [n for n, o in site.nodes.items() if o["type"] == "node--image"], title_slug)
    arts = sorted((n for n, o in site.nodes.items() if o["type"] == "node--article" and n not in m),
                  key=lambda n: site.nodes[n]["attributes"]["created"], reverse=True)
    pk = "view:" + ARTICLES_PARENT
    for i, nid in enumerate(arts, 1):
        s = title_slug(nid)
        m[nid] = {"file": f"{m[pk]['file']}__{s}", "menu": m[pk]["menu"],
                  "terms": m[pk]["terms"] + [(i, s, site.nodes[nid]["attributes"]["title"])], "child": True}

    # remaining pages/lists: child of the first menu page linking to them, else "not in menu"
    rest = [n for n, o in site.nodes.items()
            if o["type"] in ("node--page", "node--list") and n not in m and n not in EXCLUDE]
    menu_nodes = [n for n, v in m.items() if not v.get("child") and n in site.nodes and v["menu"] == "main-menu"]
    children = defaultdict(list)
    linked = {p: set(site.links_in(site.body(p))) | set(site.links_in(site.html_main(p))) for p in menu_nodes}
    for n in rest:
        for p in menu_nodes:
            if n in linked[p]:
                children[p].append(n)
                break

    def alias_slug(n):
        a = site.nodes[n]["attributes"]["path"]["alias"]
        last = a.rstrip("/").rsplit("/", 1)[-1]
        s = title_slug(n) if last.isdigit() else slug(last)
        return re.sub(r"^derivate-", "", s) or s
    for p, nids in children.items():
        add_children(p, nids, alias_slug)
    for n in rest:
        if n not in m:
            m[n] = {"file": alias_slug(n), "menu": "none", "terms": []}

    # duplicates?
    seen = {}
    for k, v in m.items():
        if v["file"] in seen:
            report["doppelte-dateinamen"].append(f"{v['file']}: {seen[v['file']]} {k}")
        seen[v["file"]] = k
    return m


# ---------------------------------------------------------------- HTML -> TEI
class Converter:
    def __init__(self, site, mapping, nid):
        self.site, self.mapping, self.nid = site, mapping, nid
        self.ids = set()

    # --- links
    def target(self, href):
        nid, path, frag = self.site.nid_for(href)
        if path is None:  # external / mailto
            return re.sub(r"(&quot;|[\"'“”„])+$", "", href.strip().strip("\"'“”„ ")), None
        if re.match(r"^/(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(/|$)", path):
            return "https://" + href.strip().lstrip("/"), None  # scheme-less external URL
        if path == "" and frag:
            return "#" + ncname(frag), None
        if path.startswith("/sites/default/files/"):
            rel = path.removeprefix("/sites/default/files/")
            from urllib.parse import unquote
            if (self.site.raw / "files" / unquote(rel)).exists():
                return "files/" + unquote(rel), None
            report["fehlende-dateien"].append(f"{self.nid}: {href}")
            return BASE + path, "legacy"
        if path.startswith("/sites/all/"):  # PDFs etc. not harvested: keep pointing to the old server
            report["links-auf-sites-all"].append(f"{self.nid}: {path}")
            return BASE + path + ("#" + frag if frag else ""), "sites-all"
        if path == "/contact":
            return BASE + path, "kontaktformular"
        if nid and nid in self.mapping:
            t = self.mapping[nid]["file"] + ".xml"
            return (t + "#" + ncname(frag)) if frag else t, None
        if nid in self.site.nodes and self.site.nodes[nid]["type"] == "node--event":
            report["links-auf-zeitleiste"].append(f"{self.nid}: {path}")
            return BASE + path, "zeitleiste"
        if nid in EXCLUDE:
            report["links-auf-weggelassene-seiten"].append(f"{self.nid}: {path}")
        elif path not in ("", "/"):
            report["unaufgeloeste-interne-links"].append(f"{self.nid}: {href}")
        return BASE + path + ("#" + frag if frag else ""), "legacy"

    def xmlid(self, raw):
        i = ncname(raw)
        if i in self.ids:
            return None
        self.ids.add(i)
        return i

    def graphic(self, el):
        if el.tag == "drupal-media":
            path, name, alt = self.site.media.get(el.get("data-entity-uuid"), (None, None, None))
            if not path:
                report["unaufgeloeste-medien"].append(f"{self.nid}: {el.get('data-entity-uuid')}")
                return None, None
            return "files/" + path, alt or name
        src = el.get("src") or ""
        t, _ = self.target(src)
        if not src.startswith(("/", "http")) or "univie.ac.at/bahr/sites/all" in src:
            report["externe-oder-tote-bilder"].append(f"{self.nid}: {src}")
        return t, el.get("alt")

    # --- conversion; ctx: div | special (item/cell/quote) | para (p, hi, head) | phrase (label)
    def flow(self, el, ctx):
        out = []
        if el.text:
            out.append(WS.sub(" ", el.text))
        for c in el:
            if isinstance(c, (lhtml.HtmlComment, etree._Comment, etree._ProcessingInstruction)):
                pass
            else:
                out.extend(self.node(c, ctx))
            if c.tail:
                out.append(WS.sub(" ", c.tail))
        return out

    def inline(self, tei_el, html_el, ctx):
        inner = "phrase" if ctx == "phrase" else "para"
        return append(tei_el, self.flow(html_el, inner))

    def node(self, el, ctx):
        tag = el.tag.lower() if isinstance(el.tag, str) else ""
        if tag == "br":
            return [T.lb()]
        if tag in HI_REND:
            hi = self.inline(T.hi(rend=HI_REND[tag]), el, ctx)
            return [hi] if has_content(hi) else list(self.flow(el, ctx))
        if tag == "span":
            cls = el.get("class") or ""
            if "fett" in cls or "bold" in cls:
                return [self.inline(T.hi(rend="bold"), el, ctx)]
            if "kursiv" in cls or "italic" in cls:
                return [self.inline(T.hi(rend="italic"), el, ctx)]
            return self.flow(el, ctx)
        if tag in ("font", "abbr", "ins", "center"):
            return self.flow(el, ctx)
        if tag == "q":
            return [self.inline(T.q(), el, ctx)]
        if tag == "a":
            out = []
            for idattr in (el.get("id"), el.get("name")):
                if idattr and (i := self.xmlid(idattr)):
                    a = T.anchor()
                    a.set(XML_ID, i)
                    out.append(a)
            href = el.get("href")
            if href and href.strip() and href.strip() != "#":
                tgt, typ = self.target(href)
                ref = T.ref(target=tgt.replace(" ", "%20"))
                if typ:
                    ref.set("type", typ)
                out.append(self.inline(ref, el, ctx))
            else:
                out.extend(self.flow(el, ctx))
            return out
        if tag in ("img", "drupal-media"):
            url, desc = self.graphic(el)
            if not url:
                return []
            g = T.graphic(url=url.replace(" ", "%20"))
            if ctx in ("div", "special"):
                fig = T.figure(g)
                if desc:
                    fig.append(T.figDesc(desc))
                return [fig]
            return [g]
        # ---- block-level
        if ctx == "phrase" or (ctx == "para" and (tag in ("p", "div", "pre") or tag in HEADINGS)):
            # flatten blocks where TEI allows no block content
            if tag in HEADINGS:
                return [self.inline(T.hi(rend=tag), el, ctx), T.lb()]
            return [T.lb(), *self.flow(el, ctx), T.lb()] if tag in ("p", "div", "pre", "li", "tr", "dd", "dt") \
                else self.flow(el, ctx)
        if tag in HEADINGS:
            if ctx == "div":
                head = trim(self.inline(T.head(), el, ctx))
                return [("HEAD", HEADINGS[tag], head, el.get("id"))] if has_content(head) else []
            return [self.inline(T.hi(rend=tag), el, ctx)]
        if tag in ("p", "pre"):
            if ctx == "div":
                return [("P", self.flow(el, "para"))]
            p = trim(append(T.p(), self.flow(el, "para")))
            return [p] if has_content(p) else []
        if tag == "div":
            return self.flow(el, ctx)
        if tag in ("blockquote", "quote"):
            q = self.block_container(T.quote(), el)
            return [q] if has_content(q) else []
        if tag in ("ul", "ol"):
            return self.list_(el, tag)
        if tag == "dl":
            return self.gloss(el)
        if tag in ("li", "dd", "dt"):  # stray list item outside a list
            return [T.list(self.block_container(T.item(), el))]
        if tag == "table":
            return self.table(el)
        if tag in ("tbody", "thead", "tfoot", "tr", "td", "th", "caption"):
            return self.flow(el, ctx)
        if tag in ("colgroup", "col"):
            return []
        if tag == "hr":
            return [T.milestone(unit="section")]
        report["unbekannte-elemente"].append(f"{self.nid}: <{tag}>")
        return self.flow(el, ctx)

    def block_container(self, tei_el, html_el):
        """item, cell, quote: mixed content incl. paragraphs"""
        append(tei_el, self.unwrap_p(self.flow(html_el, "special")))
        return trim(tei_el)

    def unwrap_p(self, nodes):
        out = []
        for n in nodes:
            if isinstance(n, tuple) and n[0] == "P":
                p = trim(append(T.p(), n[1]))
                if has_content(p):
                    out.append(p)
            elif isinstance(n, tuple):  # heading inside a container
                out.append(n[2])
            else:
                out.append(n)
        return out

    def list_(self, el, tag):
        lst = T.list(rend="numbered" if tag == "ol" else "bulleted")
        loose = []
        for c in el:
            ctag = c.tag.lower() if isinstance(c.tag, str) else ""
            if ctag == "li":
                if loose:
                    lst.append(trim(append(T.item(), loose)))
                    loose = []
                item = self.block_container(T.item(), c)
                if c.get("id") and (i := self.xmlid(c.get("id"))):
                    item.set(XML_ID, i)
                lst.append(item)
                if c.tail and c.tail.strip():
                    loose.append(WS.sub(" ", c.tail))
            elif ctag in ("ul", "ol") and len(lst):
                lst[-1].extend(self.list_(c, ctag))
            elif ctag:
                loose.extend(self.unwrap_p(self.node(c, "special")))
                if c.tail and c.tail.strip():
                    loose.append(WS.sub(" ", c.tail))
        if el.text and el.text.strip():
            loose.insert(0, WS.sub(" ", el.text))
        if loose and any(not isinstance(x, str) or x.strip() for x in loose):
            lst.append(trim(append(T.item(), loose)))
        return [lst] if len(lst) else []

    def gloss(self, el):
        lst = T.list(type="gloss")

        def children(e):  # flatten nested <dl><dl>…
            for c in e:
                if c.tag == "dl":
                    yield from children(c)
                else:
                    yield c
        if el.text and el.text.strip():
            lst.extend([T.label(), T.item(WS.sub(" ", el.text).strip())])
        for c in children(el):
            tail = WS.sub(" ", c.tail).strip() if isinstance(c.tag, str) and c.tail and c.tail.strip() else None
            if tail:  # text after </dt> or </dd> without its own <dd> (frequent in the source)
                c = lhtml.fromstring(etree.tostring(c, encoding="unicode", with_tail=False))
                if c.tag == "dt":
                    lst.append(trim(append(T.label(), self.flow(c, "phrase"))))
                    lst.append(T.item(tail))
                    continue
                c.append(lhtml.fromstring(f"<span> {tail.replace('&', '&amp;').replace('<', '&lt;')}</span>"))
            if not isinstance(c.tag, str):
                continue
            if c.tag not in ("dt", "dd"):  # stray element inside <dl>: keep as its own entry
                item = trim(append(T.item(), self.unwrap_p(self.node(c, "special"))))
                if has_content(item):
                    if len(lst) and lst[-1].tag == f"{{{TEI_NS}}}label":
                        lst.append(T.item())
                    lst.extend([T.label(), item])
                continue
            if c.tag == "dt":
                lab = trim(append(T.label(), self.flow(c, "phrase")))
                if len(lst) and lst[-1].tag == f"{{{TEI_NS}}}label":
                    lst.append(T.item())
                lst.append(lab)
            else:
                item = self.block_container(T.item(), c)
                if not len(lst) or lst[-1].tag != f"{{{TEI_NS}}}label":
                    if not has_content(item):
                        continue  # stray empty <dd>
                    lst.append(T.label())  # gloss lists need label/item pairs
                lst.append(item)
        if len(lst) and lst[-1].tag == f"{{{TEI_NS}}}label":
            lst.append(T.item())
        return [lst] if len(lst) else []

    def table(self, el):
        tbl = T.table()
        cap = el.find("caption")
        if cap is not None:
            tbl.append(trim(append(T.head(), self.flow(cap, "para"))))
        # cells without <tr> directly in table/tbody: wrap consecutive ones into a row
        for container in [el] + [c for c in el if c.tag in ("tbody", "thead", "tfoot")]:
            run = []
            for c in list(container) + [None]:
                if c is not None and c.tag in ("td", "th"):
                    run.append(c)
                    continue
                if run:
                    tr = lhtml.Element("tr")
                    run[0].addprevious(tr)
                    for cell in run:
                        tr.append(cell)
                    run = []
        rows = [r for r in el.iter("tr") if r.getparent() is not None and
                next((a for a in r.iterancestors("table")), None) is el]
        # rows the HTML parser nested into a cell (unclosed <em> etc.): detach, so they are not output twice
        for r in rows:
            parent = r.getparent()
            if parent.tag not in ("table", "tbody", "thead", "tfoot"):
                if r.tail and r.tail.strip():
                    prev = r.getprevious()
                    if prev is not None:
                        prev.tail = (prev.tail or "") + r.tail
                    else:
                        parent.text = (parent.text or "") + r.tail
                r.tail = None
                parent.remove(r)
        for r in rows:
            row = T.row()
            for c in r:
                ctag = c.tag.lower() if isinstance(c.tag, str) else ""
                if ctag not in ("td", "th"):
                    continue
                cell = self.block_container(T.cell(), c)
                if ctag == "th":
                    cell.set("role", "label")
                for a, b in (("colspan", "cols"), ("rowspan", "rows")):
                    if (c.get(a) or "").isdigit() and c.get(a) != "1":
                        cell.set(b, c.get(a))
                row.append(cell)
            if len(row):
                tbl.append(row)
        if el.get("class"):
            tbl.set("type", el.get("class"))
        return [tbl] if tbl.find(f"{{{TEI_NS}}}row") is not None else []

    # --- body assembly
    def body(self, html_text):
        frag = lhtml.fragment_fromstring(clean_html(html_text), create_parent="div")
        events = self.flow(frag, "div")
        body = T.body()
        stack = []  # (level, div)
        run = []

        def current():
            if not stack:
                d = T.div()
                body.append(d)
                stack.append((99, d))
            return stack[-1][1]

        def flush():
            nonlocal run
            if not run:
                return
            # split at double line breaks into paragraphs
            paras, cur, lbs = [], [], 0
            for n in run:
                if not isinstance(n, str) and n.tag == f"{{{TEI_NS}}}lb":
                    lbs += 1
                    cur.append(n)
                    continue
                if isinstance(n, str) and not n.strip():
                    cur.append(n)
                    continue
                if lbs >= 2:
                    paras.append(cur)
                    cur = []
                lbs = 0
                cur.append(n)
            paras.append(cur)
            for p in paras:
                p = trim(append(T.p(), p))
                if has_content(p):
                    current().append(p)
            run = []

        for ev in events:
            if isinstance(ev, tuple) and ev[0] == "HEAD":
                flush()
                _, level, head, hid = ev
                while stack and stack[-1][0] >= level:
                    stack.pop()
                d = T.div(head)
                if hid and (i := self.xmlid(hid)):
                    d.set(XML_ID, i)
                (stack[-1][1] if stack else body).append(d)
                stack.append((level, d))
            elif isinstance(ev, tuple) and ev[0] == "P":
                flush()
                p = trim(append(T.p(), ev[1]))
                if has_content(p):
                    current().append(p)
            elif isinstance(ev, str) or ev.tag in (f"{{{TEI_NS}}}{t}" for t in ("hi", "ref", "lb", "anchor", "q", "graphic")):
                run.append(ev)
            else:
                flush()
                current().append(ev)
        flush()
        # headed divs without content
        for d in body.iter(f"{{{TEI_NS}}}div"):
            if len(d) == 1 and d[0].tag == f"{{{TEI_NS}}}head":
                d.append(T.p())
        return body


# ---------------------------------------------------------------- bibliography table -> <bibl>
BIBL_FIELDS = {"autor": "author", "titel": "title", "übers": "editor", "ort": "pubPlace", "stadt": "pubPlace",
               "verlag": "publisher", "jahr": "date", "seiten": "extent", "aufl": "edition", "ausg": "edition",
               "reihe": "series", "anm": "note"}


def bibl_from_table(html_text):
    frag = lhtml.fragment_fromstring(clean_html(html_text), create_parent="div")
    tbl = frag.find('.//table[@class="bibliografie"]')
    if tbl is None:
        return None
    bibl, last = T.bibl(type="beschriebene-ausgabe"), None
    for tr in tbl.iter("tr"):
        cells = [c for c in tr if isinstance(c.tag, str) and c.tag in ("td", "th")]
        if len(cells) < 2:
            continue
        label = WS.sub(" ", cells[0].text_content()).strip().rstrip(":. ").lower()
        value = WS.sub(" ", cells[1].text_content()).strip()
        if not value:
            continue
        key = next((v for k, v in BIBL_FIELDS.items() if label.startswith(k)), None)
        if not label and last:
            key = "title-sub" if last in ("title", "title-sub") else last
        key = key or "note"
        if key == "title-sub":
            e = T.title(value, type="sub")
        elif key == "editor":
            e = T.editor(value, role="translator")
        elif key == "series":
            e = T.series(T.title(value, level="s"))
        else:
            e = getattr(T, key)(value)
            if key == "title" and bibl.find(f"{{{TEI_NS}}}title") is None:
                e.set("type", "main")
            if key == "note" and label and not label.startswith("anm"):
                e.set("type", slug(label))
        bibl.append(e)
        last = key
    return bibl if len(bibl) else None


# ---------------------------------------------------------------- document
def tei_doc(site, mapping, key):
    info = mapping[key]
    node = site.nodes.get(key)
    a = node["attributes"] if node else {}
    title = a.get("title") or info["terms"][-1][2]
    conv = Converter(site, mapping, key)

    title_stmt = T.titleStmt(T.title(title, level="a"))
    pub = T.publicationStmt(T.publisher(PUBLISHER))
    if node:
        pub.append(T.idno(key, type="drupal-nid"))
        pub.append(T.idno(a["path"]["alias"], type="drupal-alias"))
    url = BASE + (a["path"]["alias"] if node else "/" + info.get("stub", ""))
    source = T.sourceDesc(T.bibl(T.ref(url, target=url), ", abgerufen am ",
                                 T.date(TODAY, when=TODAY), type="drupal"))
    if node and node["type"] == "node--bibliographie" and (b := bibl_from_table(site.body(key))) is not None:
        source.append(b)

    tc = T.textClass()
    if info["menu"] in ("main-menu", "footer"):
        kw = T.keywords(scheme="menu", n=info["menu"])
        for n, k, label in info["terms"]:
            t = T.term(label, n=str(n), key=k)
            kw.append(t)
        if info.get("child"):
            kw[-1].set("type", "eintrag")
        tc.append(kw)
    elif info["menu"] == "front":
        tc.append(T.keywords(T.term("Startseite"), scheme="menu", n="front"))
    else:
        tc.append(T.keywords(T.term("nicht im Menü"), scheme="menu", n="none"))
    if node:
        tc.append(T.classCode(node["type"].split("--")[1], scheme="drupal-type"))
        for rel in node.get("relationships", {}).values():
            data = rel.get("data")
            for d in (data if isinstance(data, list) else [data] if data else []):
                if d.get("type", "").startswith("taxonomy_term--") and d["id"] in site.terms:
                    voc, name = site.terms[d["id"]]
                    tc.append(T.keywords(T.term(name), scheme=voc))

    rev = T.revisionDesc()
    if node:
        rev.append(T.change("angelegt in Drupal", when=a["created"], type="created"))
        rev.append(T.change("zuletzt geändert in Drupal", when=a["changed"], type="changed"))
    rev.append(T.change("aus Drupal (JSON:API) nach TEI konvertiert, scripts/convert.py", when=TODAY, type="converted"))

    header = T.teiHeader(T.fileDesc(title_stmt, pub, source), T.profileDesc(tc), rev)

    body = conv.body(site.body(key)) if node else T.body()
    # attached images (image nodes, articles)
    if node:
        figs = []
        for fld in ("field_images", "field_image"):
            data = node.get("relationships", {}).get(fld, {}).get("data")
            for d in (data if isinstance(data, list) else [data] if data else []):
                if d["type"] == "file--file":
                    path, desc = site.files.get(d["id"]), (d.get("meta") or {}).get("alt")
                else:
                    path, name, alt = site.media.get(d["id"], (None, None, None))
                    desc = alt or name
                if path:
                    fig = T.figure(T.graphic(url=("files/" + path).replace(" ", "%20")))
                    if desc:
                        fig.append(T.figDesc(desc))
                    figs.append(fig)
                else:
                    report["unaufgeloeste-medien"].append(f"{key}: {fld} {d['id']}")
        if figs:
            if not len(body):
                body.append(T.div())
            for f in reversed(figs):
                body[0].insert(0 if body[0].find(f"{{{TEI_NS}}}head") is None else 1, f)
    # generated listings
    has_children = any(v.get("child") and v["file"].startswith(info["file"] + "__") and
                       v["file"].count("__") == info["file"].count("__") + 1 for v in mapping.values())
    if not len(body):
        body.append(T.div(T.p()))
    if key == TIMELINE_PAGE:
        body.append(T.divGen(type="zeitleiste"))
    elif has_children and (key in BIB_TYPE_PARENT.values() or key == IMAGES_PARENT or "stub" in info):
        body.append(T.divGen(type="eintraege"))
    if not len(body):
        body.append(T.div(T.p()))

    tei = T.TEI(header, T.text(body))
    tei.set(XML_ID, ncname(info["file"]))
    tei.set("{http://www.w3.org/XML/1998/namespace}lang", "de")
    return tei


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="raw")
    ap.add_argument("--out", default="editions")
    args = ap.parse_args()
    site = Site(Path(args.raw))
    mapping = build_mapping(site)
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    for old in out.glob("*.xml"):
        old.unlink()
    rows = []
    for key, info in sorted(mapping.items(), key=lambda kv: kv[1]["file"]):
        tei = tei_doc(site, mapping, key)
        etree.ElementTree(tei).write(str(out / (info["file"] + ".xml")), encoding="UTF-8",
                                     xml_declaration=True, pretty_print=True)
        node = site.nodes.get(key)
        rows.append({"nid": key if node else "", "drupal_type": node["type"].split("--")[1] if node else "view",
                     "old_alias": node["attributes"]["path"]["alias"] if node else "/" + info.get("stub", ""),
                     "file": info["file"] + ".xml", "menu": info["menu"],
                     "menu_path": " > ".join(t[2] for t in info["terms"])})
    with open("mapping.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open("convert-report.txt", "w", encoding="utf-8") as f:
        for k, v in sorted(report.items()):
            f.write(f"## {k} ({len(v)})\n" + "".join(f"  {x}\n" for x in v) + "\n")
    print(f"{len(rows)} TEI-Dateien in {out}/, mapping.csv, convert-report.txt")
    for k, v in sorted(report.items()):
        print(f"  {k}: {len(v)}")


if __name__ == "__main__":
    main()
