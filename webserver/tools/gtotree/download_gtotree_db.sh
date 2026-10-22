#!/bin/bash
# Downloads GToTree's single-copy-gene HMM sets (all the sets of `gtt-hmms`, a few hundred MB) into the given
# folder, with retries and the md5 check from GToTree's own table. Sets already in the folder are kept.
# GToTree would fetch a set from zenodo.org the first time a job asks for it - slowly, with one attempt, and
# not at all when /databases is read-only as in production - so the jobs use this folder instead.
# Copy that folder to the production server's databases/GtotreeDB.
#
# Usage: bash download_gtotree_db.sh /path/to/databases/GtotreeDB   (server_gtotree env available)
set -e
if [ "$#" -ne 1 ]; then
    echo "Usage: download_gtotree_db.sh <target-dir>" >&2
    exit 1
fi
TARGET=$1
eval "$(conda shell.bash hook)"
conda activate --no-stack server_gtotree
mkdir -p "$TARGET"
cp -n "$GToTree_HMM_dir/hmm-sources-and-info.tsv" "$TARGET/"

fetch() {   # <target> <file> <link> <md5>: up to 5 attempts
    local target=$1 file=$2 link=$3 md5=$4
    for attempt in 1 2 3 4 5; do
        if [ -f "$target/$file" ] && [ "$(md5sum "$target/$file" | cut -d ' ' -f 1)" = "$md5" ]; then
            return 0
        fi
        curl --silent --location --max-time 900 -o "$target/$file" "$link" || true
        sleep 2
    done
    [ "$(md5sum "$target/$file" | cut -d ' ' -f 1)" = "$md5" ] || { echo "Could not download $file" >&2; rm -f "$target/$file"; return 1; }
}
export -f fetch

# columns of the table: file, source, target_taxa, num_genes, link, pfam_names, pfam_accessions, md5; four downloads at a time
tail -n +2 "$TARGET/hmm-sources-and-info.tsv" | cut -f 1,5,8 | tr '\t' ' ' | xargs -P 4 -L 1 bash -c 'fetch "'"$TARGET"'" "$0" "$1" "$2"'
