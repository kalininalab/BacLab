#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_kraken2 2>/dev/null || true

echo "Running Kraken2"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}
DB_PATH=${4:-/databases/Kraken2DB}

mkdir -p "$OUTPUT_DIR"

if [ ! -d "$DB_PATH" ] || [ -z "$(ls -A "$DB_PATH" 2>/dev/null)" ]; then
    echo "Kraken2 database not found at $DB_PATH. Download a memory-capped index (e.g. Standard-8 / PlusPF-8, ~8GB) - see webserver/tools/README.md." >&2
    exit 1
fi

for FILE in "$INPUT_DIR"/*; do
    if [ -f "$FILE" ]; then
        filename="$(basename "$FILE")"
        base="${filename%.*}"

        if command -v kraken2 &> /dev/null; then
            kraken2 --db "$DB_PATH" --threads "$CORES_PER_JOB" --use-names \
                --report "$OUTPUT_DIR/${base}_kraken2_report.tsv" \
                --output "$OUTPUT_DIR/${base}_kraken2_output.tsv" \
                "$FILE" 2>>"$OUTPUT_DIR/kraken2.log" || true
        else
            echo "kraken2 executable not found in PATH" >&2
        fi
    fi
done

FIRST_REPORT="$(ls "$OUTPUT_DIR"/*_kraken2_report.tsv 2>/dev/null | head -1)"
if [ -n "$FIRST_REPORT" ]; then
    cp "$FIRST_REPORT" "$OUTPUT_DIR/kraken2_results.tsv"
fi
