#!/bin/bash
# Downloads the RRE-Finder exploratory-mode databases (~470MB, Zenodo record 3733240) into the given folder, plus the small
# RRE_short files that ship with the RRE-Finder repository (fetched from GitHub at the commit the image is built from).
# Files that are already there are kept, so an interrupted run can simply be repeated.
# Copy that folder to the production server's databases/RreFinderDB.
#
# Usage: bash download_rrefinder_db.sh /path/to/databases/RreFinderDB
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_rrefinder_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
COMMIT=1be526f1566036c461d24b7149cae1449480be79   # keep in step with install/server_rrefinder.post.sh
FETCH=$(command -v baclab-fetch || echo "$(dirname "$0")/../_bin/baclab-fetch")
mkdir -p "$TARGET"
cd "$TARGET"

for BASE in a3m cs219 hhm; do
    for EXT in ffindex ffdata; do
        FILE="RRE_v7_3_$BASE.$EXT"
        [ -s "$FILE" ] || "$FETCH" "https://zenodo.org/records/3733240/files/$FILE?download=1" "$FILE"
    done
done

for FILE in RRE_short.fasta RRE_short_a3m.ffdata RRE_short_a3m.ffindex RRE_short_cs219.ffdata RRE_short_cs219.ffindex \
            RRE_short_fas.ffdata RRE_short_fas.ffindex RRE_short_hhm.ffdata RRE_short_hhm.ffindex; do
    [ -s "$FILE" ] || "$FETCH" "https://raw.githubusercontent.com/Alexamk/RREFinder/$COMMIT/data/database/$FILE" "$FILE"
done
