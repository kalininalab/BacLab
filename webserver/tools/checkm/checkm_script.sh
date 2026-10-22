#!/bin/bash
eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_spades 2>/dev/null || true

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES=${3:-4}

# CheckM's lineage_wf takes one -x extension for the whole bins directory, but the
# UI accepts .fasta/.fa/.fna interchangeably - stage every input file under a
# uniform .fasta extension so mixed uploads all actually get picked up.
BINS_DIR="$OUTPUT_DIR/.checkm_bins"
mkdir -p "$BINS_DIR"
for FILE in "$INPUT_DIR"/*; do
    [ -f "$FILE" ] || continue
    base="$(basename "$FILE")"
    ln -sf "$FILE" "$BINS_DIR/${base%.*}.fasta"
done

checkm lineage_wf -t "$CORES" -x fasta -f "$OUTPUT_DIR/checkm_results.tsv" --tab_table "$BINS_DIR" "$OUTPUT_DIR" || echo "CheckM failed"
