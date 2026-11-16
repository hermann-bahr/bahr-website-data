<?xml version="1.0" encoding="UTF-8"?>
<!-- Templates für die aus Drupal konvertierten TEI-Dateien von bahr-website-data.
     In editions.xsl als LETZTES xsl:import einbinden (höchste Import-Präzedenz). -->
<xsl:stylesheet version="2.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="#all">

    <!-- Menübaum, erzeugt von xslt/make_menu.xsl -->
    <xsl:variable name="menu" select="doc('../../data/menu.xml')"/>

    <!-- Abschnitte; @xml:id sind Sprungziele für target="datei.xml#id" -->
    <xsl:template match="tei:div">
        <div>
            <xsl:if test="@xml:id"><xsl:attribute name="id" select="@xml:id"/></xsl:if>
            <xsl:apply-templates/>
        </div>
    </xsl:template>
    <xsl:template match="tei:div/tei:head">
        <xsl:element name="h{min((count(ancestor::tei:div) + 1, 6))}">
            <xsl:apply-templates/>
        </xsl:element>
    </xsl:template>
    <xsl:template match="tei:p[not(node())]"/>

    <!-- Hervorhebungen: die Daten verwenden @rend, nicht @rendition -->
    <xsl:template match="tei:hi[@rend]">
        <xsl:choose>
            <xsl:when test="@rend = 'italic'"><em><xsl:apply-templates/></em></xsl:when>
            <xsl:when test="@rend = 'bold'"><strong><xsl:apply-templates/></strong></xsl:when>
            <xsl:when test="@rend = 'small'"><small><xsl:apply-templates/></small></xsl:when>
            <xsl:when test="@rend = 'superscript'"><sup><xsl:apply-templates/></sup></xsl:when>
            <xsl:when test="@rend = 'subscript'"><sub><xsl:apply-templates/></sub></xsl:when>
            <xsl:when test="@rend = 'underline'"><u><xsl:apply-templates/></u></xsl:when>
            <xsl:when test="@rend = 'strikethrough'"><s><xsl:apply-templates/></s></xsl:when>
            <xsl:when test="@rend = 'code'"><code><xsl:apply-templates/></code></xsl:when>
            <!-- h3/h4: Zwischenüberschriften, die im Original in Absätzen/Listen standen -->
            <xsl:otherwise><span class="hi-{@rend}"><xsl:apply-templates/></span></xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <!-- Links: interne Ziele "datei.xml" bzw. "datei.xml#id" auf .html umbiegen -->
    <xsl:template match="tei:ref">
        <a class="ref {@type}"
           href="{replace(@target, '^([^/:#]+)\.xml(#|$)', '$1.html$2')}">
            <xsl:apply-templates/>
        </a>
    </xsl:template>

    <!-- Listen -->
    <xsl:template match="tei:list">
        <ul><xsl:apply-templates/></ul>
    </xsl:template>
    <xsl:template match="tei:list[@rend = 'numbered']">
        <ol><xsl:apply-templates/></ol>
    </xsl:template>
    <xsl:template match="tei:item">
        <li>
            <xsl:if test="@xml:id"><xsl:attribute name="id" select="@xml:id"/></xsl:if>
            <xsl:apply-templates/>
        </li>
    </xsl:template>
    <xsl:template match="tei:list[@type = 'gloss']">
        <dl><xsl:apply-templates/></dl>
    </xsl:template>
    <xsl:template match="tei:list[@type = 'gloss']/tei:label">
        <dt><xsl:apply-templates/></dt>
    </xsl:template>
    <xsl:template match="tei:list[@type = 'gloss']/tei:item">
        <dd><xsl:apply-templates/></dd>
    </xsl:template>

    <!-- Tabellen (139 davon sind table[@type='bibliografie']) -->
    <xsl:template match="tei:table">
        <table class="table table-sm {@type}">
            <xsl:apply-templates select="tei:head"/>
            <tbody><xsl:apply-templates select="tei:row"/></tbody>
        </table>
    </xsl:template>
    <xsl:template match="tei:table/tei:head">
        <caption><xsl:apply-templates/></caption>
    </xsl:template>
    <xsl:template match="tei:row">
        <tr><xsl:apply-templates/></tr>
    </xsl:template>
    <xsl:template match="tei:cell">
        <xsl:element name="{if (@role = 'label') then 'th' else 'td'}">
            <xsl:if test="@cols"><xsl:attribute name="colspan" select="@cols"/></xsl:if>
            <xsl:if test="@rows"><xsl:attribute name="rowspan" select="@rows"/></xsl:if>
            <xsl:apply-templates/>
        </xsl:element>
    </xsl:template>

    <!-- Blockzitate (aus HTML-blockquote) -->
    <xsl:template match="tei:quote">
        <blockquote class="blockquote"><xsl:apply-templates/></blockquote>
    </xsl:template>

    <!-- Bilder: url="files/…" verweist auf html/files/… -->
    <xsl:template match="tei:figure">
        <figure class="figure d-block">
            <xsl:apply-templates select="tei:graphic"/>
            <xsl:if test="tei:figDesc">
                <figcaption class="figure-caption"><xsl:apply-templates select="tei:figDesc/node()"/></figcaption>
            </xsl:if>
        </figure>
    </xsl:template>
    <xsl:template match="tei:graphic">
        <img src="{@url}" alt="{normalize-space(../tei:figDesc)}" class="img-fluid" loading="lazy"/>
    </xsl:template>

    <!-- Generierte Inhalte -->
    <xsl:template match="tei:divGen[@type = 'eintraege']">
        <xsl:variable name="id" select="ancestor::tei:TEI/@xml:id"/>
        <ul class="eintraege">
            <xsl:for-each select="$menu//item[@id = $id]/item[@eintrag = 'true']">
                <li><a href="{@href}"><xsl:value-of select="label"/></a></li>
            </xsl:for-each>
        </ul>
    </xsl:template>
    <xsl:template match="tei:divGen[@type = 'zeitleiste']">
        <p><a href="https://github.com/martinantonmueller/bahr-zeitleiste">Zeitleiste (TEI-Daten auf GitHub)</a></p>
    </xsl:template>
</xsl:stylesheet>
