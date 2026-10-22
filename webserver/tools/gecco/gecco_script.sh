#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_gecco 2>/dev/null || true

echo "Running GECCO"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}

mkdir -p "$OUTPUT_DIR"

for FILE in "$INPUT_DIR"/*; do
    if [ -f "$FILE" ]; then
        filename="$(basename "$FILE")"
        base="${filename%.*}"
        sample_out="$OUTPUT_DIR/$base"
        mkdir -p "$sample_out"

        if command -v gecco &> /dev/null; then
            # First run downloads and caches GECCO's HMM model (~1GB, CPU only).
            gecco run --genome "$FILE" -o "$sample_out" -j "$CORES_PER_JOB" 2>>"$OUTPUT_DIR/gecco.log" || true
        else
            echo "gecco executable not found in PATH" >&2
        fi

        if [ -f "$sample_out/${base}.clusters.tsv" ]; then
            cp "$sample_out/${base}.clusters.tsv" "$OUTPUT_DIR/${base}_gecco_clusters.tsv"
        fi
    fi
done

if compgen -G "$OUTPUT_DIR"/*_gecco_clusters.tsv > /dev/null; then
    awk 'FNR==1 && NR!=1 {next} {print}' "$OUTPUT_DIR"/*_gecco_clusters.tsv > "$OUTPUT_DIR/gecco_results.tsv" 2>/dev/null || true
fi
