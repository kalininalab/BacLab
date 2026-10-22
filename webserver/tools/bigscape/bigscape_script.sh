#!/bin/bash

# Without this, a BiG-SCAPE failure wouldn't fail the script and would look like a successful job.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_bigscape

echo "Running BiG-SCAPE"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
PFAM_DB_PATH=$4
GCF_CUTOFF=$5
INCLUDE_MIBIG=$6   # yes: also compare with the MIBiG 4.0 reference clusters (-m 4.0)
BIGSCAPE_DB_PATH=$7

# BiG-SCAPE looks for MIBiG in its own package folder and would download it there on first use; that folder is a
# link to $BIGSCAPE_DB_PATH/MIBiG (see install/server_bigscape.post.sh and download_mibig_db.sh).
MIBIG_ARGS=()
if [ "$INCLUDE_MIBIG" = "yes" ]; then
    if [ ! -d "$BIGSCAPE_DB_PATH/MIBiG/mibig_antismash_4.0_gbk" ]; then
        echo "ERROR: MIBiG 4.0 is not in $BIGSCAPE_DB_PATH (run tools/bigscape/download_mibig_db.sh, see tools/DATABASES.md)" >&2
        exit 1
    fi
    MIBIG_ARGS=(-m 4.0)
fi

# --include-gbk '*' takes every uploaded file (BiG-SCAPE's default only keeps names containing
# "cluster"/"region"). The Pfam file is pre-pressed in the shared database folder
# (see download_pfam_db.sh), so BiG-SCAPE never has to write next to it. No MIBiG reference set is
# requested by default (-m).
bigscape cluster \
    --input-dir "$INPUT_DIR" \
    --input-mode flat \
    --include-gbk '*' \
    --output-dir "$OUTPUT_DIR/bigscape_run" \
    --pfam-path "$PFAM_DB_PATH/Pfam-A.hmm" \
    --gcf-cutoffs "$GCF_CUTOFF" \
    --include-singletons \
    --cores "$CORES_PER_JOB" \
    "${MIBIG_ARGS[@]}"

# The BiG-SCAPE viewer only loads its database by itself when served from localhost (from a fixed
# /data_sqlite.db path); anywhere else it asks the user to pick the file by hand. Patch the copy in
# this job's output so it always loads the .db next to it - this lets the results page embed it.
RUN_DIR="$OUTPUT_DIR/bigscape_run"
DB_NAME=$(basename "$(ls "$RUN_DIR"/*.db | head -n1)")
sed -i \
    -e "s#if (location.hostname === \"localhost\" || location.hostname === \"127.0.0.1\") {#if (true) {#" \
    -e "s#xhr.open('GET', '/data_sqlite.db', true);#xhr.open('GET', './$DB_NAME', true);#" \
    -e "s#\$(\"\#status\").html(\"Loaded: data_sqlite.db\")#\$(\"\#status\").html(\"Loaded: $DB_NAME\")#" \
    "$RUN_DIR/index.html"
if ! grep -q "xhr.open('GET', './$DB_NAME', true);" "$RUN_DIR/index.html"; then
    echo "WARNING: could not patch the BiG-SCAPE viewer to auto-load its database (viewer layout changed?)" >&2
fi

# BiG-SCAPE writes one family table per product class; merge them into one table.
RESULTS="$OUTPUT_DIR/bigscape_results.tsv"
printf 'Class\tRecord\tGBK\tRecord_Type\tRecord_Number\tCC\tFamily\n' > "$RESULTS"
for TABLE in "$OUTPUT_DIR"/bigscape_run/output_files/*_c"$GCF_CUTOFF"/*/*_clustering_c"$GCF_CUTOFF".tsv; do
    CLASS=$(basename "$(dirname "$TABLE")")
    tail -n +2 "$TABLE" | sed "s|^|$CLASS\t|" >> "$RESULTS"
done
