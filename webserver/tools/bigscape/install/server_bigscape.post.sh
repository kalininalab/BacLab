#!/bin/bash
# BiG-SCAPE keeps the MIBiG reference clusters in <its package folder>/MIBiG and downloads them there the first
# time they are asked for. Make that folder a link to the shared database folder instead (see download_mibig_db.sh).
set -e

eval "$(conda shell.bash hook)"
conda activate server_bigscape
PACKAGE_DIR=$(python -c 'import os, big_scape; print(os.path.dirname(big_scape.__file__))')
rm -rf "$PACKAGE_DIR/MIBiG"
ln -s /databases/BigscapeDB/MIBiG "$PACKAGE_DIR/MIBiG"
