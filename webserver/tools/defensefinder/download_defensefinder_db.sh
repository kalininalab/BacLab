#!/bin/bash
# Downloads the DefenseFinder + CasFinder models (~350MB) into the given folder.
# Copy that folder to the production server's databases/DefenseFinderDB.
#
# Usage: bash download_defensefinder_db.sh /path/to/databases/DefenseFinderDB   (server_defensefinder env)
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_defensefinder_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
eval "$(conda shell.bash hook)"
conda activate --no-stack server_defensefinder
mkdir -p "$TARGET"
defense-finder update --models-dir "$TARGET"
