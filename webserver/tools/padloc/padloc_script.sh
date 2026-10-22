#!/bin/bash

# Without this, a failure in `padloc` wouldn't fail the script - the trailing combine step below
# always exits 0 on its own, silently masking a real tool failure as a "successful" job.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_padloc

echo "Running PADLOC"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
PADLOC_DB_PATH=$4

RAW_DIR="$OUTPUT_DIR/padloc_raw"
mkdir -p "$RAW_DIR"

COMBINED_CSV="$OUTPUT_DIR/padloc_results.csv"
COMBINED_GFF="$OUTPUT_DIR/padloc_results.gff"
: > "$COMBINED_CSV"
: > "$COMBINED_GFF"

for GENOME in "$INPUT_DIR"/*; do
    NAME=$(basename "$GENOME")
    NAME="${NAME%.*}"
    mkdir -p "$RAW_DIR/$NAME"

    # --data points at the shared, pre-downloaded PADLOC-DB (see download_padloc_db.sh) so nothing
    # is fetched at run time.
    padloc --fna "$GENOME" --data "$PADLOC_DB_PATH" --outdir "$RAW_DIR/$NAME" --cpu "$CORES_PER_JOB"

    CSV=$(find "$RAW_DIR/$NAME" -maxdepth 1 -name "*_padloc.csv" | head -n1)
    # One table for all genomes: keep a single header and prefix every row with its genome name.
    if [ ! -s "$COMBINED_CSV" ]; then
        echo "genome,$(head -n1 "$CSV")" > "$COMBINED_CSV"
    fi
    tail -n +2 "$CSV" | sed "s|^|$NAME,|" >> "$COMBINED_CSV"

    GFF=$(find "$RAW_DIR/$NAME" -maxdepth 1 -name "*_padloc.gff" | head -n1)
    if [ -n "$GFF" ]; then
        grep -v '^#' "$GFF" >> "$COMBINED_GFF" || true
    fi
done
