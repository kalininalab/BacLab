#!/bin/bash
# Downloads PADLOC-DB (~1GB once compiled) into the given folder (default: ./PadlocDB next to this
# script's repo's databases/ dir). Copy that folder to the production server's databases/PadlocDB.
# `padloc --db-update` itself always installs into the conda env, so the env's data dir is copied out.
#
# Usage: bash download_padloc_db.sh /path/to/databases/PadlocDB   (server_padloc conda env available)
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_padloc_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
eval "$(conda shell.bash hook)"
conda activate --no-stack server_padloc
padloc --db-update
mkdir -p "$TARGET"
cp -r "$(dirname "$(dirname "$(which padloc)")")/data/." "$TARGET/"
echo "PADLOC-DB copied to $TARGET"
