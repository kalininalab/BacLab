#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_gubbins 2>/dev/null || true

echo "Running Gubbins"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}

mkdir -p "$OUTPUT_DIR"

ALIGNMENT_FILE="$(ls "$INPUT_DIR"/*.fasta "$INPUT_DIR"/*.fa "$INPUT_DIR"/*.aln "$INPUT_DIR"/*.full 2>/dev/null | head -1)"

if [ -z "$ALIGNMENT_FILE" ]; then
    echo "No alignment FASTA found in input directory" >&2
    exit 0
fi

cd "$OUTPUT_DIR" || exit 1

if command -v run_gubbins.py &> /dev/null; then
    run_gubbins.py --threads "$CORES_PER_JOB" --prefix gubbins_output "$ALIGNMENT_FILE" 2>&1 || true
else
    echo "run_gubbins.py executable not found in PATH" >&2
fi
