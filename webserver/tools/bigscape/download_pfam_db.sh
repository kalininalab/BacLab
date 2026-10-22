#!/bin/bash
# Downloads and presses Pfam-A (~2.2GB hmm + ~2.5GB press files) into the given folder. Used by
# BiG-SCAPE; copy that folder to the production server's databases/PfamDB.
#
# Usage: bash download_pfam_db.sh /path/to/databases/PfamDB   (needs hmmpress, e.g. from the server_panbgc env)
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_pfam_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
mkdir -p "$TARGET"
cd "$TARGET"
baclab-fetch https://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz Pfam-A.hmm.gz
gunzip -f Pfam-A.hmm.gz
baclab-fetch https://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.dat.gz Pfam-A.hmm.dat.gz
gunzip -f Pfam-A.hmm.dat.gz
hmmpress -f Pfam-A.hmm
