<?xml version="1.0" encoding="UTF-8"?>
<!-- Erzeugt data/menu.xml: den Menübaum der alten Website aus
     teiHeader//keywords[@scheme='menu'] aller Dateien in data/editions -->
<xsl:stylesheet version="2.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="#all">
    <xsl:output indent="yes"/>
    <xsl:variable name="docs" select="collection('../data/editions?select=*.xml')/tei:TEI"/>

    <xsl:template match="/">
        <menus>
            <xsl:for-each select="('main-menu', 'footer')">
                <xsl:variable name="name" select="."/>
                <menu name="{$name}">
                    <xsl:call-template name="level">
                        <xsl:with-param name="items"
                            select="$docs[.//tei:keywords[@scheme = 'menu']/@n = $name]"/>
                        <xsl:with-param name="prefix" select="''"/>
                    </xsl:call-template>
                </menu>
            </xsl:for-each>
        </menus>
    </xsl:template>

    <!-- Kinder von $prefix: xml:id = "$prefix__slug", also genau ein Menü-Term mehr -->
    <xsl:template name="level">
        <xsl:param name="items"/>
        <xsl:param name="prefix" as="xs:string"/>
        <xsl:variable name="depth"
            select="if ($prefix = '') then 1 else count(tokenize($prefix, '__')) + 1"/>
        <xsl:for-each select="$items[count(.//tei:keywords[@scheme = 'menu']/tei:term) = $depth]
                                    [$prefix = '' or starts-with(@xml:id, concat($prefix, '__'))]">
            <xsl:sort select="xs:integer(.//tei:keywords[@scheme = 'menu']/tei:term[last()]/@n)"/>
            <xsl:variable name="term" select=".//tei:keywords[@scheme = 'menu']/tei:term[last()]"/>
            <item id="{@xml:id}" href="{@xml:id}.html" eintrag="{$term/@type = 'eintrag'}">
                <label><xsl:value-of select="normalize-space($term)"/></label>
                <xsl:call-template name="level">
                    <xsl:with-param name="items" select="$items"/>
                    <xsl:with-param name="prefix" select="string(@xml:id)"/>
                </xsl:call-template>
            </item>
        </xsl:for-each>
    </xsl:template>
</xsl:stylesheet>
