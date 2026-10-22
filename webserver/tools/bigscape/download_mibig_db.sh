#!/bin/bash
# Downloads the MIBiG 4.0 reference clusters (antiSMASH-processed GenBank files) that BiG-SCAPE can add to a run
# (-m 4.0) into <target>/MIBiG/mibig_antismash_4.0_gbk. BiG-SCAPE would download them on the first job that asks
# for them, which fails when /databases is read-only as in production. Copy that folder to the production
# server's databases/BigscapeDB.
#
# Usage: bash download_mibig_db.sh /path/to/databases/BigscapeDB   (server_bigscape env available)
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_mibig_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
eval "$(conda shell.bash hook)"
conda activate --no-stack server_bigscape
mkdir -p "$TARGET"
for attempt in 1 2 3 4 5; do
    if python -c 'import sys; from pathlib import Path; from big_scape.file_input import get_mibig; get_mibig("4.0", Path(sys.argv[1]))' "$TARGET" \
            && [ -n "$(ls -A "$TARGET/MIBiG/mibig_antismash_4.0_gbk" 2>/dev/null)" ]; then
        exit 0
    fi
    echo "Downloading MIBiG failed (attempt $attempt of 5), retrying in 30 s" >&2
    rm -rf "$TARGET/MIBiG/mibig_antismash_4.0_gbk" "$TARGET/MIBiG/mibig_antismash_4.0_gbk.tar.bz2"
    sleep 30
done
exit 1
