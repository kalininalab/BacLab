#!/bin/bash
eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_spades 2>/dev/null || true

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES=${3:-4}

ASSEMBLY=$(find "$INPUT_DIR" -maxdepth 1 -type f | head -n 1)
if [ -f "$ASSEMBLY" ]; then
    quast.py "$ASSEMBLY" -o "$OUTPUT_DIR" -t "$CORES"
fi
