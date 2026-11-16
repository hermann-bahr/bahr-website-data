#!/bin/bash
# Ersetzt shellscripts/fetch_data.sh im mit dse-static-cookiecutter erzeugten Repo.
# bahr-website-data hat kein data/-Verzeichnis, daher wird die Struktur hier hergestellt:
#   editions/     -> data/editions/
#   mapping.csv   -> data/mapping.csv   (alte Drupal-Pfade -> neue Dateinamen)
#   raw/files/    -> html/files/        (Bilder, auf die <graphic url="files/…"> zeigt)
set -e

DATA_REPO=https://github.com/hermann-bahr/bahr-website-data
DATA_DIR=bahr-website-data

echo "fetching data from ${DATA_REPO}"
rm -rf data/ "${DATA_DIR}/" html/files/
git clone --depth=1 --branch main --single-branch "${DATA_REPO}.git"
git -C "./${DATA_DIR}" rev-parse HEAD | tr -d '\n' > ./datahash.txt

mkdir -p data html
mv "./${DATA_DIR}/editions" ./data/editions
mv "./${DATA_DIR}/mapping.csv" ./data/mapping.csv
mv "./${DATA_DIR}/raw/files" ./html/files
rm -rf "./${DATA_DIR}"

# Kein ./shellscripts/dl_imprint.sh: Impressum und Barrierefreiheit kommen aus den Daten
# (impressum-und-datenschutz.xml, barrierefreiheit.xml). Siehe ANLEITUNG.md, Abschnitt 6.
