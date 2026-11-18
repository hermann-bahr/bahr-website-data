#!/bin/bash
# Ersetzt shellscripts/fetch_data.sh im mit dse-static-cookiecutter erzeugten Repo.
# bahr-website-data hat kein data/-Verzeichnis, daher wird die Struktur hier hergestellt:
#   editions/     -> data/editions/
#   mapping.csv   -> data/mapping.csv   (alte Drupal-Pfade -> neue Dateinamen)
#   raw/files/    -> html/files/        (Bilder, auf die <graphic url="files/…"> zeigt)
#   ks/           -> html/ks/           (PDFs der Kritischen Schriften, <ref target="ks/…">)
set -e

DATA_REPO=https://github.com/hermann-bahr/bahr-website-data
DATA_DIR=bahr-website-data

echo "fetching data from ${DATA_REPO}"
rm -rf data/ "${DATA_DIR}/" html/files/ html/ks/
git clone --depth=1 --branch main --single-branch "${DATA_REPO}.git"
git -C "./${DATA_DIR}" rev-parse HEAD | tr -d '\n' > ./datahash.txt

mkdir -p data html
mv "./${DATA_DIR}/editions" ./data/editions
mv "./${DATA_DIR}/mapping.csv" ./data/mapping.csv
mv "./${DATA_DIR}/raw/files" ./html/files
mv "./${DATA_DIR}/ks" ./html/ks
rm -rf "./${DATA_DIR}"

# Impressum und Datenschutz: ACDH-Impressum (imprint.html), Barrierefreiheit aus den Daten
# (barrierefreiheit.xml). Siehe ANLEITUNG.md, Abschnitt 6.
./shellscripts/dl_imprint.sh
