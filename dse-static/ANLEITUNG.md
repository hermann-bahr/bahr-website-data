# bahr-website-data mit dse-static-cookiecutter verwenden

Diese Anleitung beschreibt, wie aus den Daten dieses Repos mit dem
[dse-static-cookiecutter](https://github.com/acdh-oeaw/dse-static-cookiecutter) eine statische
Nachfolge-Website von <https://bahr.univie.ac.at> gebaut wird. Sie richtet sich an alle, die das
Code-Repo (im Folgenden `bahr-static`) aufsetzen.

Im Ordner `dse-static/` liegen drei Dateien, die ins Code-Repo kopiert werden:

| Datei | Ziel im Code-Repo | Zweck |
|---|---|---|
| `fetch_data.sh` | `shellscripts/fetch_data.sh` | holt die Daten und legt sie so ab, wie der Cookiecutter sie erwartet |
| `make_menu.xsl` | `xslt/make_menu.xsl` | erzeugt `data/menu.xml`, den Menübaum der alten Website |
| `bahr.xsl` | `xslt/partials/bahr.xsl` | Templates für die TEI-Elemente, die der Cookiecutter nicht (passend) behandelt |

`make_menu.xsl` und `bahr.xsl` wurden mit Saxon 9 HE gegen alle 275 Dateien getestet: Die
Transformation läuft fehlerfrei durch, alle internen Links zeigen auf existierende Seiten und alle
Bildverweise auf vorhandene Dateien. Alle Änderungen aus Abschnitt 5 sind in `../bahr-website-static`
umgesetzt, dort läuft `ant` erfolgreich durch (rund 10 Sekunden).

---

## 1. Was in diesem Repo liegt

| Pfad | Für die Website nötig? | Inhalt |
|---|---|---|
| `editions/*.xml` | **ja** | 275 TEI-Dateien, eine pro Seite der alten Website |
| `raw/files/` | **ja** | Bilder (41 MB), auf die `<graphic url="files/…">` verweist |
| `mapping.csv` | optional | Drupal-Node-ID, alter Pfad, neuer Dateiname, Menüpfad (für Weiterleitungen) |
| `convert-report.txt` | nein | Liste der Probleme bei der Konvertierung (siehe Abschnitt 8) |
| `raw/jsonapi/`, `raw/html/`, `raw/*.json` | nein | Rohdaten aus Drupal, nur als Sicherung |
| `scripts/` | nein | `harvest.py` (Drupal → `raw/`) und `convert.py` (`raw/` → `editions/`) |

**Achtung:** `scripts/convert.py` löscht beim Lauf alle `editions/*.xml` und schreibt sie neu.
Sobald die TEI-Dateien von Hand bearbeitet werden, darf das Skript nicht mehr laufen.

## 2. Projekt erzeugen

```bash
cookiecutter gh:acdh-oeaw/dse-static-cookiecutter
```

Empfohlene Antworten:

| Frage | Antwort |
|---|---|
| `directory_name` | `bahr-static` |
| `project_title` | `Hermann Bahr` |
| `project_short_title` | `Hermann Bahr` |
| `default_lang` | `de` |
| `github_org` | `hermann-bahr` |
| `base_url` | die künftige Adresse **mit `https://` und abschließendem `/`**, z. B. `https://bahr.univie.ac.at/` (die Templates hängen den Dateinamen direkt an; korrigierbar in `xslt/partials/params.xsl`) |
| `redmine_id` | nur nötig, wenn das ACDH-Impressum verwendet wird (Abschnitt 6) |
| `translations` | `no` (alle Inhalte sind deutsch) |
| `use_remote_data` | `yes` |
| `data_dir` | `bahr-website-data` |
| `data_repo` | `https://github.com/hermann-bahr/bahr-website-data` |

## 3. Daten holen

Der mitgelieferte `shellscripts/fetch_data.sh` erwartet im Daten-Repo einen Ordner `data/`. Den gibt
es hier nicht. Deshalb `dse-static/fetch_data.sh` nach `shellscripts/fetch_data.sh` kopieren. Er legt
die Daten so ab:

```
data/editions/*.xml     ← editions/
data/mapping.csv        ← mapping.csv
html/files/…            ← raw/files/…
datahash.txt            ← Commit-Hash des Daten-Repos
```

`html/files/` in die `.gitignore` des Code-Repos eintragen. Die GitHub-Action `build.yml` ruft das
Skript schon vor `ant` auf, dort ist nichts zu ändern.

## 4. Das Datenmodell in Kürze

### Dateinamen und IDs

Der Dateiname folgt dem Menüpfad der alten Website. Die Ebenen sind mit `__` verbunden.
`/TEI/@xml:id` ist der Dateiname **ohne** `.xml`:

```
briefe.xml                                       Briefe
briefe__arthur-schnitzler.xml                    Briefe > Arthur Schnitzler
bibliografie__theaterstuecke__juana-1896.xml     Bibliografie > Theaterstücke > Juana (1896)
index.xml                                        Startseite
stammbaum.xml                                    nicht im Menü (19 Dateien)
```

Die HTML-Seite heißt dann `<xml:id>.html`.

### Menüposition im Header

```xml
<textClass>
  <keywords scheme="menu" n="main-menu">            <!-- main-menu | footer | front | none -->
    <term n="2" key="kritische-schriften">Kritische Schriften</term>
    <term n="12" key="austriaca-1911" type="eintrag">Austriaca (1911)</term>
  </keywords>
  <classCode scheme="drupal-type">bibliographie</classCode>   <!-- page | bibliographie | image | article | list -->
  <keywords scheme="bibliografie_type"><term>Kritische Schriften</term></keywords>
</textClass>
```

- Ein `term` pro Menüebene, `@n` ist die Reihenfolge innerhalb der Ebene.
- `term[@type='eintrag']` (220 Dateien): kein eigener Menüpunkt, sondern ein Eintrag in der
  Liste einer Übersichtsseite (Bibliografie-Einträge, Bilder, Forschungsnotizen, Derivate …).
  Für die Navigation gilt: Menüpunkte sind die Elemente ohne `@type`, Einträge bekommen
  Vor/Zurück-Links.

### Weitere Header-Felder

- `titleStmt/title[@level='a']`: Seitentitel
- `publicationStmt/idno[@type='drupal-nid']` und `[@type='drupal-alias']`: alte Node-ID und alter Pfad
- `sourceDesc/bibl[@type='drupal']`: alte URL und Abrufdatum
- `sourceDesc/bibl[@type='beschriebene-ausgabe']` (122 Bibliografie-Einträge): strukturierte Angaben
  zur Ausgabe (`author`, `title[@type='main'|'sub']`, `pubPlace`, `publisher`, `date`, `extent`,
  `edition`, `editor[@role='translator']`, `series`, `note`). Dieselben Angaben stehen auch als
  `table[@type='bibliografie']` im Text. Für die Anzeige reicht die Tabelle, die `bibl` eignet sich
  für die Suche oder das Inhaltsverzeichnis.
- `revisionDesc/change[@type='created'|'changed'|'converted']`

### Elemente im Text

| Element | Häufigkeit | Bemerkung |
|---|---|---|
| `div` mit `head`, verschachtelt | 1045 | `div/@xml:id` sind Sprungziele für Links |
| `p`, `lb` | 1980 / 5224 | |
| `hi/@rend` | 9437 | `italic`, `bold`, `small`, `superscript`, `strikethrough`, `h3`, `h4` – **`@rend`, nicht `@rendition`** |
| `list/@rend` | | `bulleted`, `numbered`; einige Listen ganz ohne Attribut |
| `list[@type='gloss']` mit `label`/`item` | 57 | Definitionslisten |
| `table`/`row`/`cell` | 284 | `cell/@role='label'`, `@cols`, `@rows`; `table/@type='bibliografie'` |
| `quote` | 148 | Blockzitat |
| `figure`/`graphic`/`figDesc` | 92 | `graphic/@url="files/…"`, auch `graphic` direkt im Absatz |
| `ref/@target` | 4173 | siehe unten |
| `divGen[@type='eintraege']` | 9 | hier die Liste der Einträge (`type="eintrag"`) einsetzen |
| `divGen[@type='zeitleiste']` | 1 | in `leben.xml`, Daten in [bahr-zeitleiste](https://github.com/martinantonmueller/bahr-zeitleiste) |

Es gibt keine `note`, `rs`, `pb` oder Register im Text. Die Register des Cookiecutters
(`listperson` usw.) entfallen deshalb.

### Linkziele

| `ref/@target` | `ref/@type` | Behandlung |
|---|---|---|
| `datei.xml`, `datei.xml#id` | – | auf `datei.html`, `datei.html#id` umschreiben |
| `#id` | – | unverändert |
| `files/…` | – | unverändert (liegt unter `html/files/`) |
| `https://bahr.univie.ac.at/sites/all/…` | `sites-all` | 2954 Links auf PDFs, **die nicht geharvestet wurden** (Abschnitt 8) |
| `https://bahr.univie.ac.at/node/…` | `zeitleiste` | 2 Links auf Ereignisse der alten Zeitleiste |
| `https://bahr.univie.ac.at/contact` | `kontaktformular` | 2 Links auf das Drupal-Kontaktformular |
| `https://bahr.univie.ac.at/…` | `legacy` | 6 interne Links, die nicht aufgelöst werden konnten |
| sonstige `http(s)://…` | – | externe Links |

## 5. Anpassungen im Code-Repo

### 5.1 Menübaum erzeugen

`dse-static/make_menu.xsl` nach `xslt/make_menu.xsl` kopieren. Es liest alle
`data/editions/*.xml` und schreibt `data/menu.xml`:

```xml
<menus>
  <menu name="main-menu">
    <item id="briefe" href="briefe.html" eintrag="false">
      <label>Briefe</label>
      <item id="briefe__arthur-schnitzler" href="briefe__arthur-schnitzler.html" eintrag="false">…</item>
      …
    </item>
    …
  </menu>
  <menu name="footer">…</menu>
</menus>
```

Alle anderen Stylesheets lesen Navigation, Brotkrumen, Vor/Zurück und die Eintragslisten aus dieser
Datei. So muss nicht jede Seite die ganze Sammlung neu einlesen.

### 5.2 `build.xml`

1. **Als ersten Schritt** (vor allen anderen `xslt`-Aufrufen) einfügen:
   ```xml
   <xslt in="./xslt/make_menu.xsl" out="./data/menu.xml" style="./xslt/make_menu.xsl">
       <factory name="net.sf.saxon.TransformerFactoryImpl"/>
       <classpath location="${basedir}/saxon/saxon9he.jar"/>
   </xslt>
   ```
2. `<property name="index" value="./data/meta/about.xml"/>` ändern zu
   `<property name="index" value="./data/editions/index.xml"/>`. Die anderen Aufrufe brauchen
   `${index}` nur als Dummy-Eingabe.
3. Den Aufruf von `index.xsl` (→ `index.html`) **entfernen**. Die Startseite entsteht über
   `editions.xsl` aus `data/editions/index.xml`. Bleibt der Aufruf stehen, hängt es von der Reihenfolge ab,
   welche Fassung von `index.html` übrig bleibt.
4. Entfernen, weil die Eingabedateien fehlen:
   - `meta.xsl` (`data/meta/` gibt es nicht; alle Seiten liegen in `data/editions/`)
   - `listperson.xsl`, `listplace.xsl`, `listorg.xsl`, `listbibl.xsl`, `beacon.xsl`
   - `imprint.xsl`, wenn das ACDH-Impressum nicht verwendet wird (Abschnitt 6)
   - `noske-search.xsl`, solange es kein NoSketch-Korpus gibt
5. `api.xsl` liest `./data/imprint.xml`. Entweder auf `${index}` umstellen oder den Aufruf entfernen.
6. Die abschließende `copy`-Anweisung (`data/**/*.xml` → `html/`) bleibt. Sie stellt die
   TEI-Downloads bereit (und nebenbei `menu.xml`).

### 5.3 `xslt/partials/bahr.xsl` einbinden

`dse-static/bahr.xsl` nach `xslt/partials/bahr.xsl` kopieren und in `xslt/editions.xsl` als
**letztes** `xsl:import` eintragen. Später importierte Module haben Vorrang, so ersetzen die Templates
die gleichnamigen aus `shared.xsl`:

```xml
<xsl:import href="./partials/shared.xsl"/>
…
<xsl:import href="./partials/zotero.xsl"/>
<xsl:import href="./partials/bahr.xsl"/>
```

`bahr.xsl` behandelt `div/@xml:id`, `head` (als `h2`–`h6` je nach Tiefe), `hi/@rend`, `ref`
(mit Umschreibung `.xml` → `.html`), alle Listentypen, Tabellen samt `th`/`colspan`/`rowspan`,
`quote` als Blockzitat, `figure`/`graphic`, leere `p` sowie beide `divGen`. Außerdem stellt es die
Variable `$menu` bereit.

### 5.4 `xslt/editions.xsl`

**IDs, Links, Vor/Zurück.** Die Variablen `prev`, `next`, `teiSource` und `link` am Anfang ersetzen.
Die Vorlage nimmt an, dass `@xml:id` auf `.xml` endet und dass es `TEI/@prev` und `TEI/@next` gibt.
Beides trifft hier nicht zu:

```xml
<xsl:variable name="doc_id" select="string(/tei:TEI/@xml:id)"/>
<xsl:variable name="teiSource" select="concat($doc_id, '.xml')"/>
<xsl:variable name="link" select="concat($doc_id, '.html')"/>
<xsl:variable name="self" select="$menu//item[@id = $doc_id]"/>
<!-- Vor/Zurück nur zwischen Einträgen derselben Liste -->
<xsl:variable name="prev"
    select="string($self[@eintrag = 'true']/preceding-sibling::item[@eintrag = 'true'][1]/@href)"/>
<xsl:variable name="next"
    select="string($self[@eintrag = 'true']/following-sibling::item[@eintrag = 'true'][1]/@href)"/>
```

Die Prüfungen `ends-with($prev, '.html')` im Template bleiben so, wie sie sind.

**Brotkrumen.** Den Punkt „Inhaltsverzeichnis“ (Link auf `toc.html`) durch den Menüpfad ersetzen:

```xml
<li class="breadcrumb-item">
    <a href="index.html"><xsl:value-of select="$project_short_title"/></a>
</li>
<xsl:for-each select="$self/ancestor::item">
    <li class="breadcrumb-item"><a href="{@href}"><xsl:value-of select="label"/></a></li>
</xsl:for-each>
<li class="breadcrumb-item active" aria-current="page">
    <xsl:value-of select="$doc_title"/>
</li>
```

**Leere Übersichtsseiten.** `bibliografie.xml`, `briefe.xml` und `forschung.xml` haben keinen Text,
sie waren in Drupal reine Menüknoten. Direkt nach `<xsl:apply-templates select=".//tei:body"/>`
die Unterseiten auflisten:

```xml
<xsl:if test="not(normalize-space(string-join(.//tei:body//text(), '')))
              and not(.//tei:divGen) and $self/item">
    <ul class="unterseiten">
        <xsl:for-each select="$self/item">
            <li><a href="{@href}"><xsl:value-of select="label"/></a></li>
        </xsl:for-each>
    </ul>
</xsl:if>
```

**Fußnoten.** `<xsl:for-each select=".//tei:note[not(./tei:p)]">` greift vom Wurzelknoten aus auch auf
die 111 `note` im Header (`bibl[@type='beschriebene-ausgabe']`) zu. Das würde auf
Bibliografie-Seiten falsche Fußnoten erzeugen. Ändern zu `.//tei:body//tei:note[not(./tei:p)]`.

### 5.5 Navigation `xslt/partials/html_navbar.xsl`

Den Inhalt von `<ul class="navbar-nav …">` (Projekt, Editionseinheiten, Register, API, Suche …) durch
das Hauptmenü ersetzen. Untermenüs zeigen nur echte Menüpunkte, keine Einträge:

```xml
<ul class="navbar-nav me-auto mb-2 mb-lg-0">
    <xsl:for-each select="doc('../../data/menu.xml')/menus/menu[@name = 'main-menu']/item">
        <xsl:variable name="sub" select="item[@eintrag = 'false']"/>
        <xsl:choose>
            <xsl:when test="$sub">
                <li class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" role="button"
                       data-bs-toggle="dropdown" aria-expanded="false">
                        <xsl:value-of select="label"/>
                    </a>
                    <ul class="dropdown-menu">
                        <li><a class="dropdown-item" href="{@href}"><xsl:value-of select="label"/></a></li>
                        <li><hr class="dropdown-divider"/></li>
                        <xsl:for-each select="$sub">
                            <li><a class="dropdown-item" href="{@href}"><xsl:value-of select="label"/></a></li>
                        </xsl:for-each>
                    </ul>
                </li>
            </xsl:when>
            <xsl:otherwise>
                <li class="nav-item"><a class="nav-link" href="{@href}"><xsl:value-of select="label"/></a></li>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:for-each>
    <!-- optional: <li class="nav-item"><a class="nav-link" href="search.html">Suche</a></li> -->
</ul>
```

Ergebnis (getestet): Bibliografie (8 Unterpunkte) · Kritische Schriften (2) · Leben (1) · Briefe (5) ·
Forschung (11) · Bilder – also dieselbe Reihenfolge wie auf der alten Website. Der Pfad
`../../data/menu.xml` gilt relativ zu `xslt/partials/`. `doc()` wird hier direkt aufgerufen, weil
`toc.xsl`, `search.xsl` und `404.xsl` die Navigation auch einbinden, `bahr.xsl` aber nicht.

### 5.6 Footer `xslt/partials/html_footer.xsl`

Links auf Impressum und Barrierefreiheit aus dem Footer-Menü erzeugen:

```xml
<xsl:for-each select="doc('../../data/menu.xml')/menus/menu[@name = 'footer']/item">
    <a href="{@href}"><xsl:value-of select="label"/></a>
</xsl:for-each>
```

Der alte Footer-Punkt „Kontakt“ war ein Drupal-Formular (`/contact`) und hat keine Datei. Er wird
durch eine `mailto:`-Adresse ersetzt.

### 5.7 `xslt/toc.xsl`

`replace(./@xml:id, '.xml', '.html')` ergibt hier `briefe` statt `briefe.html`. Ändern zu
`concat(@xml:id, '.html')`. Die Spalte „ID“ ist für Leser wenig aussagekräftig, besser ist der
Menüpfad:
`string-join(.//tei:keywords[@scheme='menu']/tei:term, ' › ')`. Wird das Inhaltsverzeichnis gar nicht
gebraucht, den Aufruf in `build.xml` streichen.

### 5.8 CSS

Neue Klassen, die gestaltet werden sollten: `a.ref.sites-all`, `a.ref.legacy`, `a.ref.zeitleiste`
(zum Beispiel als Hinweis auf externe oder alte Ziele), `table.bibliografie`, `ul.eintraege`,
`ul.unterseiten`, `span.hi-h3`, `span.hi-h4`.

## 6. Impressum

Der Cookiecutter lädt mit `dl_imprint.sh` das ACDH-Impressum (über `redmine_id`). Die alte Website
hat ein eigenes Impressum (`impressum-und-datenschutz.xml`) und eine Erklärung zur Barrierefreiheit
(`barrierefreiheit.xml`). Beide werden über `editions.xsl` gerendert und stehen im Footer-Menü.

- **Hosting nicht beim ACDH:** `dl_imprint.sh` und `imprint.xsl` weglassen, wie im mitgelieferten
  `fetch_data.sh`. Den Inhalt von `impressum-und-datenschutz.xml` für den neuen Betreiber anpassen.
- **Hosting beim ACDH:** `dl_imprint.sh` wieder in `fetch_data.sh` aufnehmen, `imprint.xsl` in
  `build.xml` lassen und `impressum-und-datenschutz.xml` aus dem Footer nehmen.

## 7. Optional

### Weiterleitungen von alten URLs

Wenn die neue Website die alte Domain übernimmt, sollten zitierte Adressen wie
`/bibliografie/38703` weiter funktionieren. Ein Skript nach dem `ant`-Lauf, das aus
`data/mapping.csv` Weiterleitungsseiten schreibt:

```python
import csv
from pathlib import Path

with open("data/mapping.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        alias = row["old_alias"].strip("/")
        if not alias:
            continue
        up = "../" * (alias.count("/") + 1)
        target = up + row["file"].replace(".xml", ".html")
        d = Path("html", alias)
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(
            f'<!doctype html><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url={target}">'
            f'<link rel="canonical" href="{target}">',
            encoding="utf-8",
        )
```

### Bildergalerie

Auf `bilder.html` kann `divGen[@type='eintraege']` statt einer Liste Vorschaubilder zeigen. Das erste
Bild eines Eintrags ist
`doc(concat('../../data/editions/', @id, '.xml'))//tei:graphic[1]/@url`. Dafür in `bahr.xsl` ein
eigenes Template für `divGen[ancestor::tei:TEI/@xml:id = 'bilder']` anlegen.

### Volltextsuche (Typesense)

`pyscripts/make_ts_index.py` liest bereits `data/editions/*.xml`. Die Felder im Schema (Titel, Jahr
usw.) müssen an die Daten angepasst werden. Für Bibliografie-Einträge bieten sich die Angaben aus
`bibl[@type='beschriebene-ausgabe']` an. Solange es keinen Index gibt, „Suche“ aus der Navigation
weglassen.

## 8. Bekannte Lücken in den Daten

Details stehen in `convert-report.txt`.

1. **PDFs unter `/sites/all/` (2954 Links, `ref[@type='sites-all']`).** Die Bände der Kritischen
   Schriften, Sonderdrucke, Indizes und Zeitungsartikel lagen nicht in Drupal, sondern direkt auf dem
   Server. Sie wurden nicht geharvestet, die Links zeigen weiter auf `https://bahr.univie.ac.at/sites/all/…`.
   Wird der alte Server abgeschaltet, sind sie tot. Die PDFs müssen vorher gesichert und mit
   ins Code-Repo oder auf einen Datei-Server genommen werden. Danach die Links umschreiben, am
   einfachsten im `ref`-Template von `bahr.xsl` für `@type='sites-all'`.
2. **Zeitleiste** (`leben.xml`, `divGen[@type='zeitleiste']`, 2 Links mit `@type='zeitleiste'`):
   Die Daten liegen in [bahr-zeitleiste](https://github.com/martinantonmueller/bahr-zeitleiste).
   `bahr.xsl` setzt vorerst nur einen Link dorthin. Eine richtige Darstellung bräuchte einen
   zusätzlichen Fetch-Schritt und ein eigenes Stylesheet.
3. **Textverzeichnis:** Der Menüpunkt wurde bewusst ausgelassen, weil das Textverzeichnis unter
   <https://bahr-textverzeichnis.acdh.oeaw.ac.at/> liegt. Ein interner Link (`/textverzeichnis` in
   `bibliografie__zur-bibliografie.xml`) zeigt noch auf die alte Seite.
4. **6 unaufgelöste interne Links** (`ref[@type='legacy']`), unter anderem `/bahr/node/9595`, `9601` und
   `3087` in `bibliografie-der-buecher.xml`: von Hand prüfen.
5. **8 externe oder tote Bilder** (`http://www.univie.ac.at/bahr/sites/all/…`): Die Bilder fehlen, ihre
   Verweise stehen weiter in den TEI-Dateien.
6. **19 Seiten nicht im Menü** (`keywords[@n='none']`): Sie sind nur über Links erreichbar, zum Beispiel
   `einleitung.xml`, `danksagung.xml`, `stammbaum.xml` (parallel zu `leben__stammbaum.xml`). Sie
   werden gebaut, erscheinen aber in keiner Navigation.

## 9. Prüfen nach dem ersten Build

- `html/` enthält 275 Seiten aus `data/editions/` sowie `toc.html`, `search.html`, `404.html` und die
  TEI-Dateien zum Download.
- Die Navigation stimmt mit der alten Website überein (Abschnitt 5.5).
- `bibliografie.html`, `briefe.html` und `forschung.html` listen ihre Unterseiten auf.
- Die Seiten zu Theaterstücken, Literarischer Prosa, Kritischen Schriften, Schriften zum Theater,
  Tagebuch, Herausgaben, Bildern und Forschungsnotizen listen ihre Einträge (`divGen`).
- Einträge haben Vor- und Zurück-Links, Menüseiten haben keine.
- Bilder werden angezeigt (`html/files/bahr_bilder/…`, `html/files/bilder/vdg/…`).
- Kein Link endet auf `.xml"`, außer den TEI-Downloads:
  `grep -l 'href="[^"]*\.xml[#"]' html/*.html` sollte nur durch die Download-Buttons Treffer liefern.
