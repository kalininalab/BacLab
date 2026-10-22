#!/bin/bash
# Downloads the zol annotation databases (minimal set: Pfam + PGAP, ~9GB incl. pressed profiles)
# into the given folder, for PanBGC. Copy that folder to the production server's databases/ZolDB.
#
# Uses zol's own setup_annotation_dbs.py, patched to skip the V-Score file: its upstream URL
# (anantharamanlab.github.io/V-Score-Search/dataFixed.csv) returns 404 and the unpatched script
# aborts on it even in minimal mode. It is only needed for the non-minimal (VOG) annotations.
#
# NOTE: afterwards the database paths refer to /databases/ZolDB, i.e. they only resolve inside the
# containers (or where the folder is mounted there).
#
# Usage: bash download_zol_db.sh /path/to/databases/ZolDB   (server_panbgc conda env available)
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_zol_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
eval "$(conda shell.bash hook)"
conda activate --no-stack server_panbgc
PATCHED=$(mktemp --suffix=.py)
sed "s|download_links = \['https://anantharamanlab.github.io/V-Score-Search/dataFixed.csv',|download_links = [|" "$(which setup_annotation_dbs.py)" > "$PATCHED"
# The script wants to create the directory itself and asks before deleting an existing one.
rm -rf "$TARGET"
mkdir -p "$TARGET"
echo yes | ZOL_DATA_PATH="${TARGET%/}/" python "$PATCHED" -m -c 8
rm -f "$PATCHED"

# zol records ABSOLUTE paths of its database files in database_location_paths.txt. Rewrite them to
# the path the folder has inside the containers (/databases/ZolDB), so the folder can be copied to
# another machine as-is instead of pointing at this machine's download location.
sed -i "s|${TARGET%/}/|/databases/ZolDB/|g" "$TARGET/database_location_paths.txt"
