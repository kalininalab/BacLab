#!/bin/bash
# Downloads the BiG-SLiCE HMM models (~1.1GB extracted) into the given folder, as <target>/bigslice-models.
# Copy that folder to the production server's databases/BigsliceDB.
#
# Usage: bash download_bigslice_db.sh /path/to/databases/BigsliceDB
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_bigslice_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
mkdir -p "$TARGET/bigslice-models"
cd "$TARGET"
baclab-fetch https://github.com/medema-group/bigslice/releases/download/v2.0.0rc/bigslice-models.2022-11-30.tar.gz bigslice-models.tar.gz
tar --no-same-owner -xzf bigslice-models.tar.gz -C bigslice-models
rm bigslice-models.tar.gz
