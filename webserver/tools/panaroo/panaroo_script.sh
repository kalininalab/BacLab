#!/bin/bash
set -e

source /opt/conda/etc/profile.d/conda.sh
conda activate server_panaroo

# Expected arguments:
# $1: Input directory containing GFF files
# $2: Output directory
# $3: Number of cores
# $4: Clean mode (strict, moderate, light)

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES=$3
CLEAN_MODE=$4

if [ -z "$CLEAN_MODE" ]; then
    CLEAN_MODE="strict"
fi

# Run Panaroo
panaroo -i "$INPUT_DIR"/*.gff -o "$OUTPUT_DIR" -t "$CORES" --clean-mode "$CLEAN_MODE"

echo "Panaroo analysis finished."
