#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_ani 2>/dev/null || true

echo "Running FastANI"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}

mkdir -p "$OUTPUT_DIR"

GENOME_LIST="$OUTPUT_DIR/genome_list.txt"
find "$INPUT_DIR" -maxdepth 1 -type f > "$GENOME_LIST"
GENOME_COUNT=$(wc -l < "$GENOME_LIST")

if [ "$GENOME_COUNT" -lt 2 ]; then
    echo "FastANI needs at least 2 genome assemblies to compare (found $GENOME_COUNT)." >&2
    exit 1
fi

if command -v fastANI &> /dev/null; then
    fastANI --ql "$GENOME_LIST" --rl "$GENOME_LIST" -t "$CORES_PER_JOB" \
        -o "$OUTPUT_DIR/ani_raw.tsv" --matrix 2>"$OUTPUT_DIR/fastani.log" || true
else
    echo "fastANI executable not found in PATH" >&2
fi

if [ -f "$OUTPUT_DIR/ani_raw.tsv" ]; then
    {
        printf 'Query\tReference\tANI\tMapped_Fragments\tTotal_Query_Fragments\n'
        awk 'BEGIN{FS=OFS="\t"} {sub(".*/", "", $1); sub(".*/", "", $2); print}' "$OUTPUT_DIR/ani_raw.tsv"
    } > "$OUTPUT_DIR/ani_results.tsv"
fi
