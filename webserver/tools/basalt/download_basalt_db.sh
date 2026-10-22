#!/bin/bash
# Downloads the BASALT trained models (~1GB, Hugging Face PKU-EMBL/BASALT_WEIGHT) into
# <target>/BASALT_WEIGHT. Copy that folder to the production server's databases/BasaltDB.
# BASALT also needs the CheckM2 database, which is shared with the CheckM2 tool (databases/Checkm2DB).
#
# Usage: bash download_basalt_db.sh /path/to/databases/BasaltDB   (server_basalt env, BASALT installed)
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_basalt_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
eval "$(conda shell.bash hook)"
conda activate --no-stack server_basalt
mkdir -p "$TARGET"
BASALT_models_download.py --source huggingface --path "$TARGET/BASALT_WEIGHT"
