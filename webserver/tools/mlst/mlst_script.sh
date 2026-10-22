#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_mlst 2>/dev/null || true

echo "Running MLST"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}

mkdir -p "$OUTPUT_DIR"

FASTA_FILES=()
for FILE in "$INPUT_DIR"/*; do
    if [ -f "$FILE" ]; then
        FASTA_FILES+=("$FILE")
    fi
done

if [ ${#FASTA_FILES[@]} -eq 0 ]; then
    echo "No input files found" >&2
    exit 0
fi

if command -v mlst &> /dev/null; then
    mlst --threads "$CORES_PER_JOB" "${FASTA_FILES[@]}" > "$OUTPUT_DIR/mlst_results.tsv" 2>"$OUTPUT_DIR/mlst.log" || true
else
    echo "mlst executable not found in PATH" >&2
fi
