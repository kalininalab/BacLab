#!/bin/bash

eval "$(conda shell.bash hook)"

conda activate --no-stack server_abricate

echo "Running Abricate"

INPUT_DIR=$1
OUTPUT_DIR=$2
DATABASE=$3
MINIMUM_IDENTITY=$4
MINIMUM_COVERAGE=$5
CORES_PER_JOB=$6
SCRIPT_DIR="$(dirname "$0")"

abricate --db "$DATABASE" --minid "$MINIMUM_IDENTITY" --mincov "$MINIMUM_COVERAGE" --threads "$CORES_PER_JOB" "$INPUT_DIR"/* > "$OUTPUT_DIR/abricate_results.tsv"

awk 'BEGIN{FS=OFS="\t"} {sub(".*/", "", $1); print}' "$OUTPUT_DIR/abricate_results.tsv" > "$OUTPUT_DIR/temp" && mv "$OUTPUT_DIR/temp" "$OUTPUT_DIR/abricate_results.tsv"

abricate --summary "$OUTPUT_DIR/abricate_results.tsv" > "$OUTPUT_DIR/abricate_summary.tsv"