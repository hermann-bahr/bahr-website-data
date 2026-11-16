#!/usr/bin/env python3
"""Wandelt obsolete/forschung__sekundaerliteratur.xml (Listen mit Freitext-Zitaten)
heuristisch in listBibl/biblStruct um.

    python3 scripts/sekundaerliteratur_to_listbibl.py

Ergebnis: editions/forschung__sekundaerliteratur.xml (wird überschrieben!)
Die Zerlegung ist heuristisch. Jeder Eintrag behält deshalb das Originalzitat in
<note type="original">; was sich nicht zuordnen ließ, steht in <note type="rest">.
"""
import copy
import re
import sys
from datetime import date
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "obsolete" / "forschung__sekundaerliteratur.xml"
OUT = ROOT / "editions" / "forschung__sekundaerliteratur.xml"
TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"t": TEI}
MARK = "\x00"

MONTHS = {
    "januar": 1, "jänner": 1, "februar": 2, "feber": 2, "märz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
    "dezember": 12, "december": 12, "january": 1, "february": 2, "march": 3, "may": 5,
    "june": 6, "july": 7, "october": 10,
}
PARTICLES = {
    "von", "van", "de", "te", "und", "u.", "zu", "le", "la", "du", "y", "et", "ten", "vom",
    "del", "della", "dal", "der", "den", "di", "&", "and", "v.", "d.", "e",
}
HG = r"(?:Hgg?|Hrsg|Hrsgg|Ed|Eds|eds|ed|Red)\.?"
HG_MARK = re.compile(r"\s*[\(\[]\s*" + HG + r"\s*[\)\]]\s*")
THESIS = re.compile(
    r"Dissertation|Diplomarbeit|Diss\.|Masterarbeit|Magisterarbeit|Habil|Laurea|Hausarbeit|"
    r"Zulassungsarbeit|Thesis|Thèse|Mémoire|masch\.", re.I)
ABBREV = {
    "Hg", "Hgg", "Hrsg", "hg", "hrsg", "von", "Bd", "Bde", "Nr", "Jg", "Aufl", "Univ", "Diss",
    "St", "vgl", "bzw", "usw", "Ders", "Dies", "ed", "eds", "No", "Vol", "Mspt", "masch", "geb",
    "Ts", "Br", "Fr", "Dr", "Prof", "Jr", "Aug", "Th", "Verl", "Chr", "Joh", "Jos", "Phil",
    "Mitarb", "Red", "Zs", "Ztg", "Übers", "übers", "Einl", "eingel", "Nachw", "bearb", "Bearb",
    "erw", "verb", "hist", "phil", "Wiss", "Ges", "Abt", "Tl", "Sp", "Bl", "Beil", "Erg", "Kr",
}
CAP = r"[A-ZÄÖÜŠŽČÉÈ][\w'’./-]*"
PERIODICAL = re.compile(
    r"zeitung|blatt|[Pp]ost\b|[Jj]ournal|[Nn]achrichten|[Kk]urier|[Pp]resse|[Rr]undschau|[Bb]ote\b|"
    r"[Cc]hronik|[Aa]nzeiger|[Zz]eitschrift|[Jj]ahrbuch|[Hh]efte\b|Review|Magazin|Welt\b|"
    r"[Ww]ochenschrift|Revue|[Mm]onatsschrift|Zukunft|Merker|\bTag\b|Volksstimme|Wacht|Beiträge|"
    r"Quarterly|Studies|Literatur\b|Echo|Kunstwart|Hochland|Gral\b|Bühne|Fackel|Furche|Zeit\b|"
    r"Listy|Lloyd|Courier|Kourier|Tribüne|Volkswille|Vaterland|Germania|Reichswart|Türmer")
PLACE1 = (r"(?:(?:St\.|Bad|New|Ville|Casale|Den|La|Le|Los|San|Saint|Ann)\s)?" + CAP +
          r"(?:\s(?:a\.\s?M\.|am Main|a\.\s?d\.\s?\w+|i\.\s?Br\.|im Breisgau|an der \w+))?"
          r"(?:\s(?:u\.\s?a\.?|et al\.|usw\.|etc\.|\[?u\.\s?a\.\]?|\[etc\.\]))?")
PLACES = PLACE1 + r"(?:(?:,\s?|\s?/\s?|\s[–-]\s|\sund\s|\s&\s|;\s)" + PLACE1 + r"){0,7}"
YEAR = r"(?:1[89]|20)\d{2}"


def E(tag, text=None, **attrs):
    el = etree.Element("{%s}%s" % (TEI, tag))
    for k, v in attrs.items():
        if v is not None:
            el.set(k.rstrip("_"), v)
    if text is not None:
        el.text = text
    return el


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def trim(s):
    """Whitespace und lose Interpunktion an den Rändern entfernen."""
    s = clean(s.replace(MARK, " "))
    s = re.sub(r"^[\s,;:.]+", "", s)
    s = re.sub(r"[\s,;:]+$", "", s)
    if s.endswith(".") and not re.search(r"(?:\b\w{1,3}|\.\.)\.$", s):
        s = s[:-1]
    return s.strip()


def sentences(s):
    """Satzgrenzen an '. ', aber nicht nach Initialen und Abkürzungen."""
    out, start = [], 0
    for m in re.finditer(r"[.?!][“”\"»«]?\s+(?=[\[„“\"»«(]?[A-ZÄÖÜŠŽČÉ0-9])", s):
        before = s[start:m.start()]
        word = re.search(r"([\w]+)$", before)
        if s[m.start()] == "." and word and (len(word.group(1)) <= 2 or word.group(1) in ABBREV):
            continue
        out.append(s[start:m.end()].strip())
        start = m.end()
    if s[start:].strip():
        out.append(s[start:].strip())
    return out


def looks_like_names(s):
    s = HG_MARK.sub(" ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = s.strip(" ,;")
    if not s or len(s) > 140 or re.search(r"\d|[!?„“»«\"]", s) or re.search(r"\w{4,}\.\s", s):
        return False
    toks = s.replace(";", " ").replace(",", " ").replace("/", " ").split()
    if not toks or len(toks) > 16:
        return False
    for t in toks:
        if t in PARTICLES:
            continue
        if not re.match(r"[A-ZÄÖÜŠŽČÉÈ]", t) and not re.match(r"^[a-zäöü]{1,3}\.(?:[\w–-]{1,4}\.?)*$", t):
            return False
    return True


def persons(s):
    """Namensliste -> Liste von Elementinhalten (surname, forename) oder (None, text)."""
    s = HG_MARK.sub(" ", s)
    s = clean(s).strip(" ,;:")
    out = []
    for piece in re.split(r"\s*;\s*|\s+und\s+|\s*/\s*|\s+&\s+|\s+and\s+|\s+u\.\s+|\s+e\s+", s):
        piece = piece.strip(" ,")
        if not piece:
            continue
        parts = [p.strip() for p in piece.split(",") if p.strip()]
        first = [t for t in parts[0].split() if t not in PARTICLES]
        if len(parts) >= 2 and len(first) == 1 and "." not in parts[0] and "[" not in piece:
            out.append((parts[0], parts[1]))
            out.extend((None, p) for p in parts[2:])
        else:
            out.extend((None, p) for p in parts)
    return out


def person_el(tag, sur, fore):
    el = E(tag)
    if sur:
        pn = E("persName")
        pn.append(E("surname", sur))
        pn.append(E("forename", fore))
        el.append(pn)
    elif re.search(r"[\[\]=?]", fore) or re.fullmatch(r"(?:[\w–-]{1,3}\.\s?)+[\w–-]{0,3}\.?", fore) \
            or fore in ("Ders.", "Dies.", "Ders", "Dies"):
        el.text = fore  # Kürzel, erschlossene oder fehlende Namen
    else:
        el.append(E("persName", fore))
    return el


def iso(d, m, y):
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


class Parsed:
    def __init__(self):
        self.authors, self.a_title = [], None
        self.m_authors, self.editors, self.m_title, self.level = [], [], None, "m"
        self.place = self.publisher = None
        self.year = self.when = self.date_text = None
        self.volume = self.issue = self.pages = None
        self.series, self.notes, self.rest = [], [], []
        self.idnos = []
        self.kind = "book"


def take(s, pattern, flags=0, last=False):
    """Ersten (oder letzten) Treffer durch MARK ersetzen; (neuer String, Match) zurückgeben."""
    ms = list(re.finditer(pattern, s, flags))
    if not ms:
        return s, None
    m = ms[-1] if last else ms[0]
    return s[:m.start()] + MARK + s[m.end():], m


def extract_tail(s, p, sub=False):
    """Zieht Anmerkungen, Reihe, Datum, Zählung, Seiten und Impressum aus s heraus."""
    # Anmerkungen in eckigen Klammern am Ende
    while True:
        m = re.search(r"\s*\[([^\[\]]*)\][\s.,;]*$", s)
        if not m or re.fullmatch(r"\s*" + HG + r"\s*", m.group(1)) or re.search(r"S\.\s*\[?\d*\]?[–-]?$", s[:m.start()]):
            break
        p.notes.insert(0, m.group(1).strip())
        s = s[:m.start()]
    # Reihe in runden Klammern
    for m in list(re.finditer(r"\((=\s*[^()]*(?:\([^()]*\)[^()]*)*|[^()=]*(?:Bd\.?|Band|Vol\.|Heft|Reihe|;)\s*\d+[^()]*|[A-ZÄÖÜ][^()\d]{8,}[,\s]\s?\d{1,4})\)", s)):
        txt = m.group(1).lstrip("= ").strip()
        if re.fullmatch(r"\d{1,2}\.\s?\d{1,2}\.\s?\d{4}", txt):
            continue
        p.series.append(txt)
        s = s.replace(m.group(0), MARK, 1)
    # genaues Datum
    s, m = take(s, r"\(?(\d{1,2})\.\s?(\d{1,2})\.\s?(" + YEAR + r")\)?")
    if m:
        p.when, p.date_text = iso(*m.groups()), re.sub(r"[()\s]", "", m.group(0))
        p.year = m.group(3)
        s = re.sub(r"\(?\d{1,2}\.\s?\d{1,2}\.\s?" + YEAR + r"\)?", MARK, s)  # Wiederholungen
    else:
        s, m = take(s, r"\(?(\d{1,2})\.\s?(" + "|".join(MONTHS) + r")\s(" + YEAR + r")\)?", re.I)
        if m:
            p.when = iso(m.group(1), MONTHS[m.group(2).lower()], m.group(3))
            p.date_text, p.year = m.group(0).strip("()"), m.group(3)
    # Seiten mit "S."
    s, m = take(s, r",?\s*\bS\.\s*(\[?\d+\]?[a-z]?(?:\s?[-–—]\s?\[?\d+\]?[a-z]?)?(?:\s?ff?\.)?)", last=True)
    if m:
        p.pages = m.group(1)
    # Band (Jahr)
    s, m = take(s, r",?\s*(?:(?:Jg\.|Jahrgang|Bd\.|Band|Vol\.)\s*)?(\d{1,3})\.?\s*(?:Jg\.\s*)?\((" + YEAR + r")(?:[/=–-]\d{2,4})?(?:,[^()]*)?\)")
    if m:
        p.volume, p.level = m.group(1), "j"
        p.year = p.year or m.group(2)
    else:
        s, m = take(s, r",?\s*(?:Jg\.|Jahrgang|Bd\.|Band|Vol\.|Volume)\s*(\d{1,3})\b")
        if m:
            p.volume = m.group(1)
    # Heft / Nummer
    s, m = take(s, r",?\s*(?:#\s?|Nr\.\s?|No\.\s?|H\.\s?|Heft\s|Issue\s)(\d+[a-z]?(?:\s?[-–/]\s?\d+)*)(?:/(" + YEAR + r"))?")
    if m:
        p.issue, p.level = m.group(1), "j"
        p.year = p.year or m.group(2)
    # Impressum: Ort: Verlag Jahr
    ms = [m for m in re.finditer(
        r"(?:^|(?<=[.,;)\]»“”\"]\s)|(?<=\x00)\s?)(" + PLACES + r"):\s([^:\x00]{2,80}?),?\s\(?(" + YEAR + r")\)?(?![\d-])", s)
        if not re.search(r"\w{3,}\.\s[A-ZÄÖÜ]\w{3,}\s\w+\s\w+", m.group(2))]
    if ms:
        m = ms[-1]
        p.place, p.publisher = m.group(1), m.group(2).strip(" ,(")
        p.year = p.year or m.group(3)
        s = s[:m.start()] + MARK + s[m.end():]
    else:
        ms = list(re.finditer(
            r"(?:^|(?<=[.,;)\]»“”\"]\s)|(?<=\x00)\s?)((?:Universität|Univ\.|Université|University of|Università)\s[\w.\s-]{2,40}?),?\s\(?(" + YEAR + r")\)?(?![\d-])", s))
        if ms:
            m = ms[-1]
            p.publisher, p.year = m.group(1), p.year or m.group(2)
            s = s[:m.start()] + MARK + s[m.end():]
        else:
            ms = list(re.finditer(
                r"(?:^|(?<=[.,;)\]»“”\"]\s)|(?<=\x00)\s?)(" + PLACES + r"),?\s\(?(" + YEAR + r")\)?(?![\d-]|\s?#)", s))
            ms = [m for m in ms if not re.match(r"(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\b", m.group(1))]
            if ms and not p.level == "j":
                m = ms[-1]
                if PERIODICAL.search(m.group(1)) and not sub:
                    p.level, p.year = "j", p.year or m.group(2)
                    s = s[:m.end(1)] + MARK + s[m.end():]
                elif not (sub and m.start() == 0 and not s[m.end():].strip(" ." + MARK)):
                    p.place, p.year = m.group(1), p.year or m.group(2)
                    s = s[:m.start()] + MARK + s[m.end():]
    # Seiten ohne "S." am Ende
    if not p.pages and sub:
        m = re.search(r"\s(\d{1,4}\s?[-–—]\s?\d{1,4})[\s.]*$", s)
        if m:
            p.pages = m.group(1)
            s = s[:m.start()] + MARK
    if not p.pages:
        m = re.search(r"[,.\x00]\s*(\[?\d{1,4}[a-z]?\]?(?:\s?[-–—]\s?\[?\d{1,4}[a-z]?\]?)?(?:\s?ff?\.)?)[\s.,\x00]*$", s)
        if m and not (re.fullmatch(YEAR, m.group(1)) and not p.year):
            p.pages = m.group(1)
            s = s[:m.start()] + MARK
        elif m:
            p.year = m.group(1)
            s = s[:m.start()] + MARK
    if not p.year and not sub:
        s, m = take(s, r"[,\s]\(?(" + YEAR + r")\)?(?=[\s.,\x00]*$)")
        if m:
            p.year = m.group(1)
    return s


def split_editor(s, p, names_first=True):
    """'X (Hg.): Titel' oder 'Titel. Hg. von X' -> Herausgeber abtrennen; Titel zurückgeben."""
    m = re.match(r"(.{3,160}?)[\(\[]\s*" + HG + r"\s*[\)\]]\s*[:,.]?\s*(.*)$", s)
    if m and looks_like_names(m.group(1)):
        p.editors += persons(m.group(1))
        return m.group(2)
    m = re.match(r"(?:(Ders|Dies)\.|(.{3,90}?)):\s+(.+)$", s)
    if m and names_first and (m.group(1) or looks_like_names(m.group(2))):
        if m.group(1):
            p.m_authors.append((None, m.group(1) + "."))
        else:
            p.m_authors += persons(m.group(2))
        return m.group(3)
    sents = sentences(s)
    keep = []
    for sent in sents:
        m = re.match(r"(?:[Hh](?:rs)?gg?\.|[Hh]erausgegeben|[Ee]d(?:ited|s)?\.?)\s*(?:und kommentiert\s)?(?:von|v\.|by)?:?\s+(.+)$", sent)
        if m and keep:
            names = re.split(r"\s+unter Mitarbeit\s+|\s+in Zusammenarbeit\s+", m.group(1))[0]
            names = re.sub(r"\s+u\.\s?a\.?$|\s+et al\.?$", "", names.strip(" ."))
            if looks_like_names(names):
                p.editors += persons(names)
                continue
        m2 = re.match(r"(.+?),\s*(?:[Hh](?:rs)?gg?\.|herausgegeben)\s*(?:von|v\.)?:?\s+(.+)$", sent)
        if m2:
            names = re.sub(r"\s+u\.\s?a\.?$|\s+et al\.?$", "", m2.group(2).strip(" ."))
            if looks_like_names(names):
                p.editors += persons(names)
                keep.append(m2.group(1))
                continue
        keep.append(sent)
    return " ".join(keep)


def parse(text, sub=False, review=False):
    p = Parsed()
    s = clean(text)
    # ISBN / DOI
    m = re.search(r",?\s*ISBN:?\s*([\dXx–-]{10,17})", s)
    if m:
        p.idnos.append(("ISBN", m.group(1)))
        s = s[:m.start()] + s[m.end():]
    m = re.search(r",?\s*DOI:?\s*(?:https?://(?:dx\.)?doi\.org/)?(10\.\S+)", s)
    if m:
        p.idnos.append(("DOI", m.group(1).rstrip(".,")))
        s = s[:m.start()] + s[m.end():]
    s = re.sub(r"[,\s]*\bDOI:?\s*$", "", s).strip()
    # Trennung an "In:"
    head, cont, lower_in = s, None, False
    m = re.search(r"[,.]?\s+([Ii])n:\s+", s)
    if m:
        head, cont, lower_in = s[:m.start()], s[m.end():], m.group(1) == "i"
        if s[m.start()] in ".," and not s[m.start()] == ",":
            head += "." if re.search(r"\b\w{1,3}$", head) else ""
    # Verfasser
    m = re.match(r"(.{2,160}?):\s+(.+)$", head)
    sig = re.match(r"([^\s:]{1,8}):\s+(.+)$", head)
    if sig and not re.match(r"[A-ZÄÖÜ][a-zäöüß]{3,}$", sig.group(1)) and not sig.group(1).isdigit() \
            and not looks_like_names(sig.group(1)):
        p.authors.append((None, sig.group(1)))
        head, m = sig.group(2), None
    if m and looks_like_names(m.group(1)):
        names, head = m.group(1), m.group(2)
        if HG_MARK.search(names):
            p.editors += persons(names)
        else:
            p.authors += persons(names)
    elif cont is not None and lower_in and looks_like_names(head):
        p.authors += persons(head)
        head = ""
    elif re.match(r"\[(?:[Oo]\.\s?[NV]\.|Anonym|anonym):?\]:?\s", head):
        m = re.match(r"\[([^\]]+?):?\]:?\s+(.*)$", head)
        p.authors.append((None, "[" + m.group(1) + "]"))
        head = m.group(2)
    elif re.match(r"\[[^\]]{3,40}\]:\s", head) and looks_like_names(head[1:head.index("]")]):
        p.authors += [(a, b) if a else (None, "[" + b + "]") for a, b in persons(head[1:head.index("]")])]
        head = head[head.index("]") + 2:].strip()

    if cont is None and review and not p.authors:
        m = re.match(r"((?:[A-ZÄÖÜ][\w.-]+\s){1,3}[A-ZÄÖÜ][\w-]+)[,:]\s+(.+)$", head)
        if m:
            p.authors += persons(m.group(1))
            head = m.group(2)
    if cont is not None:
        p.a_title = trim(head) or None
        c = extract_tail(cont, p, sub)
        pre, _, post = c.partition(MARK)
        pre = split_editor(pre.strip(), p)
        p.m_title = trim(pre) or None
        crumbs = trim(" ".join(x for x in post.split(MARK)))
        if crumbs and re.search(r"\w", crumbs):
            p.rest.append(crumbs)
        if p.level == "j" or (not p.publisher and not p.place and not p.editors and not p.m_authors):
            p.level = "j"
            p.kind = "newspaperArticle" if (p.when and not p.volume) else "journalArticle"
        else:
            p.kind = "bookSection"
    else:
        c = extract_tail(head, p, sub)
        pre, _, post = c.partition(MARK)
        crumbs = trim(" ".join(x for x in post.split(MARK)))
        if crumbs and re.search(r"\w", crumbs):
            p.rest.append(crumbs)
        periodical = p.level == "j" or (p.when and not p.publisher and not p.place)
        if periodical and not p.publisher:
            sents = sentences(pre.strip())
            p.level = "j"
            p.kind = "newspaperArticle" if (p.when and not p.volume) else "journalArticle"
            if len(sents) > 1:
                p.a_title = trim(" ".join(sents[:-1])) or None
                p.m_title = trim(sents[-1]) or None
            else:
                p.m_title = trim(pre) or None
        else:
            pre = split_editor(pre.strip(), p, names_first=not p.authors)
            if p.m_authors and not p.authors:  # 'Name: Titel' wurde schon als Verfasser erkannt
                p.authors, p.m_authors = p.m_authors, []
            p.m_title = trim(pre) or None
            p.kind = "thesis" if THESIS.search(text) and not (
                p.place and p.publisher and "niv" not in p.publisher) else "book"
            if sub and not review and not p.place and not p.publisher:
                p.a_title, p.m_title, p.kind = p.m_title, None, "bookSection"
    return p


def pages_from_rest(p):
    """Seitenangabe, die hinter Ausgabenbezeichnung o. Ä. im Rest gelandet ist."""
    if p.pages or not p.rest:
        return
    m = re.search(r"(?:^|,\s)(?:S\.\s?)?(\d{1,4}(?:\s?[-–—]\s?\d{1,4})?)\.?(?=\s|$)", p.rest[0])
    if m:
        p.pages = m.group(1)
        left = trim(p.rest[0][:m.start()] + " " + p.rest[0][m.end():])
        p.rest = [left] if re.search(r"\w", left) else []


def build(p, bid, label_year, original, refs):
    pages_from_rest(p)
    if p.level == "j" and p.m_title:
        m = re.search(r",?\s*\(?(" + YEAR + r")\)?$", p.m_title)
        if m and m.start() > 3:
            p.m_title, p.year = trim(p.m_title[:m.start()]), p.year or m.group(1)
    bs = E("biblStruct", type=p.kind)
    bs.set("{%s}id" % XML, bid)
    doi = [v for t, v in p.idnos if t == "DOI"]
    isbn = [v for t, v in p.idnos if t == "ISBN"]
    monogr = E("monogr")
    if p.a_title or (p.authors and p.kind in ("journalArticle", "newspaperArticle", "bookSection")):
        an = E("analytic")
        for sur, fore in p.authors:
            an.append(person_el("author", sur, fore))
        if p.a_title:
            an.append(E("title", p.a_title, level="a"))
        for v in doi:
            an.append(E("idno", v, type="DOI"))
        doi = []
        bs.append(an)
    else:
        for sur, fore in p.authors:
            monogr.append(person_el("author", sur, fore))
    for sur, fore in p.m_authors:
        monogr.append(person_el("author", sur, fore))
    for sur, fore in p.editors:
        monogr.append(person_el("editor", sur, fore))
    if not p.m_title and (p.editors or p.m_authors or (p.authors and not len(bs))):
        # monogr braucht nach author/editor einen Titel
        for el in list(monogr):
            monogr.remove(el)
        p.rest.append("Nicht zugeordnete Namen: " + "; ".join(
            clean(" ".join(x for x in pair if x)) for pair in p.m_authors + p.editors + (
                p.authors if not len(bs) else [])))
    if p.m_title:
        monogr.append(E("title", p.m_title, level=p.level))
    for v in isbn:
        monogr.append(E("idno", v, type="ISBN"))
    for v in doi:
        monogr.append(E("idno", v, type="DOI"))
    imprint = E("imprint")
    if p.place:
        imprint.append(E("pubPlace", p.place))
    if p.publisher:
        imprint.append(E("publisher", p.publisher))
    if p.when:
        imprint.append(E("date", p.date_text, when=p.when))
    elif p.year:
        imprint.append(E("date", p.year, when=p.year))
    elif label_year:
        imprint.append(E("date", when=label_year, type="heading"))
    else:
        imprint.append(E("date", "o. J."))
    monogr.append(imprint)
    if p.volume:
        monogr.append(E("biblScope", p.volume, unit="volume"))
    if p.issue:
        monogr.append(E("biblScope", p.issue, unit="issue"))
    if p.pages:
        pg = re.sub(r"\s", "", p.pages)
        m = re.fullmatch(r"\[?(\d+)\]?[a-z]?(?:[-–—]\[?(\d+)\]?[a-z]?)?", pg)
        bsc = E("biblScope", p.pages, unit="page")
        if m:
            bsc.set("from", m.group(1))
            bsc.set("to", m.group(2) or m.group(1))
        monogr.append(bsc)
    bs.append(monogr)
    for stxt in p.series:
        se = E("series")
        m = re.match(r"(.+?)[,;.]?\s+(?:(?:Bd\.?|Band|Vol\.|Nr\.|Heft|#)\s*)?(\d+)$", stxt)
        if m:
            se.append(E("title", m.group(1).strip(" ,;"), level="s"))
            se.append(E("biblScope", m.group(2), unit="volume"))
        else:
            se.append(E("title", stxt, level="s"))
        bs.append(se)
    for n in p.notes:
        bs.append(E("note", n))
    for r in p.rest:
        bs.append(E("note", r, type="rest"))
    bs.append(E("note", original, type="original"))
    for target, rtext, rtype in refs:
        bs.append(E("ref", rtext or None, target=target, type=rtype))
    return bs


# ---------------------------------------------------------------- Quelle lesen

def item_parts(item):
    """Zerlegt ein <item>: Haupttext, Nachträge nach <lb/>, Unterlisten, Links."""
    main, extras, sublists, refs = [], [], [], []
    cur = main

    def walk(node, cur):
        if node.text:
            cur.append(node.text)
        for ch in node:
            tag = etree.QName(ch).localname
            if tag == "list":
                sublists.append(ch)
            elif tag == "lb":
                extras.append([])
                cur = extras[-1]
            elif tag == "ref":
                rt = clean("".join(ch.itertext()))
                refs.append((ch.get("target"), rt, len(extras)))
                if "doi.org" in (ch.get("target") or "") and re.search(r"10\.\d{4}", rt):
                    cur.append(" DOI: " + re.sub(r"^.*?(10\.\d{4})", r"\1", rt) + " ")
            else:
                cur = walk(ch, cur)
            if ch.tail:
                cur.append(ch.tail)
        return cur

    walk(item, cur)
    return clean("".join(main)), [clean("".join(x)) for x in extras], sublists, refs


class Counter:
    def __init__(self):
        self.n = 0
        self.stats = {}

    def next(self):
        self.n += 1
        return "sekundaerliteratur_%04d" % self.n


def ref_tuple(target, text):
    text = text.strip("[] ")
    rtype = None
    if target and not re.match(r"https?:|mailto:", target):
        rtype = "internal"
    return target, text, rtype


def convert_item(item, year, cnt, parent=None, review=False):
    """Gibt ein biblStruct- oder (bei reinen Gruppenüberschriften) listBibl-Element zurück."""
    main, extras, sublists, refs = item_parts(item)
    original = clean("".join(t for t in item.xpath("text()|*[not(self::t:list)]//text()", namespaces=NS)))
    sub_items = [si for sl in sublists for si in sl.xpath("t:item", namespaces=NS)]
    if not main and not sub_items:
        return None
    # Gruppenüberschrift ohne eigene bibliografische Angabe
    if sub_items and len(main) < 45 and not re.search(r"\d{4}", main):
        lb = E("listBibl", type="group")
        lb.append(E("head", main.rstrip(": ")))
        for si in sub_items:
            el = convert_item(si, year, cnt)
            if el is not None:
                lb.append(el)
        return lb
    p = parse(main, sub=parent is not None, review=review)
    main_refs = []
    for target, rtext, where in refs:
        if "doi.org" in (target or "") and re.search(r"10\.\d{4}", rtext):
            continue  # steht schon als idno
        main_refs.append(ref_tuple(target, rtext))
    if parent is not None and not p.year and not p.when:
        year = parent
    bs = build(p, cnt.next(), year, original, main_refs)
    cnt.stats[p.kind] = cnt.stats.get(p.kind, 0) + 1
    pos = bs.index(bs.find("t:note[@type='original']", NS))
    rel_type = "part"
    for ex in extras:
        ex = ex.strip()
        if not ex:
            continue
        if re.match(r"Rezension", ex):
            rel_type = "review"
        if re.fullmatch(r"(Darin|Rezensionen|Rezension)\s*:?", ex):
            continue
        ntype = ("review" if re.match(r"Rezens", ex) else
                 "part" if re.match(r"Darin", ex) else
                 "reprint" if re.match(r"Dass\.|Nachgedruckt|Weiterer Abdruck", ex) else "supplement")
        bs.insert(pos, E("note", ex, type=ntype))
        pos += 1
    for si in sub_items:
        el = convert_item(si, year, cnt, parent=year, review=rel_type == "review")
        if el is None:
            continue
        ri = E("relatedItem", type=rel_type)
        ri.append(el)
        bs.append(ri)
    return bs


def main():
    parser = etree.XMLParser(remove_blank_text=False)
    src = etree.parse(str(SRC), parser)
    root = src.getroot()
    cnt = Counter()
    empty_years = []

    out = E("TEI")
    out = etree.Element("{%s}TEI" % TEI, nsmap={None: TEI})
    out.set("{%s}id" % XML, "forschung__sekundaerliteratur")
    out.set("{%s}lang" % XML, "de")
    header = copy.deepcopy(root.find("t:teiHeader", NS))
    header.tail = None
    rev = header.find("t:revisionDesc", NS)
    ch = E("change", "aus der Listenfassung (obsolete/forschung__sekundaerliteratur.xml) heuristisch in listBibl/biblStruct "
           "umgewandelt, scripts/sekundaerliteratur_to_listbibl.py", when=date.today().isoformat(),
           type="converted")
    rev.append(ch)
    out.append(header)
    text = E("text")
    body = E("body")
    text.append(body)
    out.append(text)

    for div in root.xpath("//t:body/t:div", namespaces=NS):
        lists = div.xpath("t:list[@type='gloss']", namespaces=NS)
        if not lists:
            intro = copy.deepcopy(div)
            intro.tail = None
            body.append(intro)
            continue
        ndiv = E("div")
        if div.get("{%s}id" % XML):
            ndiv.set("{%s}id" % XML, div.get("{%s}id" % XML))
        ndiv.append(E("head", clean("".join(div.find("t:head", NS).itertext()))))
        for gl in lists:
            year = None
            for ch in gl:
                tag = etree.QName(ch).localname
                if tag == "label":
                    year = clean("".join(ch.itertext()))
                elif tag == "item":
                    entries = ch.xpath("t:list/t:item", namespaces=NS)
                    els = [e for e in (convert_item(i, year, cnt) for i in entries) if e is not None]
                    if not els:
                        if year:
                            empty_years.append(year)
                        continue
                    lb = E("listBibl", n=year)
                    lb.append(E("head", year))
                    lb.extend(els)
                    ndiv.append(lb)
        body.append(ndiv)

    etree.indent(out, space="  ")
    OUT.parent.mkdir(exist_ok=True)
    etree.ElementTree(out).write(str(OUT), encoding="UTF-8", xml_declaration=True)
    print("geschrieben:", OUT.relative_to(ROOT))
    print("biblStruct:", cnt.n, cnt.stats)
    print("Jahre ohne Einträge:", ", ".join(empty_years) or "-")


if __name__ == "__main__":
    sys.exit(main())
