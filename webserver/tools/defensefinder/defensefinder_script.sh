#!/bin/bash

# See padloc_script.sh: without this a tool failure would be masked by the combine step.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_defensefinder

echo "Running DefenseFinder"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
DEFENSEFINDER_DB_PATH=$4

RAW_DIR="$OUTPUT_DIR/defensefinder_raw"
mkdir -p "$RAW_DIR"

SYSTEMS="$OUTPUT_DIR/defensefinder_results.tsv"
GENES="$OUTPUT_DIR/defensefinder_genes.tsv"
: > "$SYSTEMS"
: > "$GENES"

for GENOME in "$INPUT_DIR"/*; do
    NAME=$(basename "$GENOME")
    NAME="${NAME%.*}"
    mkdir -p "$RAW_DIR/$NAME"

    # --models-dir points at the shared, pre-downloaded models (see download_defensefinder_db.sh).
    # Nucleotide FASTA is accepted - genes are predicted internally.
    defense-finder run --workers "$CORES_PER_JOB" --models-dir "$DEFENSEFINDER_DB_PATH" --out-dir "$RAW_DIR/$NAME" "$GENOME"

    for KIND in systems genes; do
        SRC=$(ls "$RAW_DIR/$NAME"/*_defense_finder_${KIND}.tsv | head -n1)
        if [ "$KIND" = systems ]; then DEST="$SYSTEMS"; else DEST="$GENES"; fi
        if [ ! -s "$DEST" ]; then
            printf 'genome\t%s\n' "$(head -n1 "$SRC")" > "$DEST"
        fi
        tail -n +2 "$SRC" | sed "s|^|$NAME\t|" >> "$DEST"
    done
done
