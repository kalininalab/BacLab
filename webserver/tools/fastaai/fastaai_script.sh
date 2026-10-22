#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_fastaai 2>/dev/null || true

echo "Running FastAAI"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}

mkdir -p "$OUTPUT_DIR"

GENOME_COUNT=$(find "$INPUT_DIR" -maxdepth 1 -type f | wc -l)
if [ "$GENOME_COUNT" -lt 2 ]; then
    echo "FastAAI needs at least 2 genome assemblies to compare (found $GENOME_COUNT)." >&2
    exit 1
fi

if command -v fastaai &> /dev/null; then
    # Split build_db (gene calling + HMM search, safely parallel) from db_query
    # (the AAI comparison step) instead of using the combined `aai_index`
    # convenience command. db_query's own multiprocessing.Pool silently drops
    # results when run with more than 1 thread from inside this platform's
    # Celery worker (reproducibly: partial or zero result files, exit code 0,
    # no error) - a fastaai bug specific to that comparison step, not to gene
    # calling. Single-threaded db_query is reliable and still fast for the
    # small genome sets this tool is meant to compare.
    fastaai build_db -g "$INPUT_DIR" -o "$OUTPUT_DIR" --threads "$CORES_PER_JOB" \
        2>"$OUTPUT_DIR/fastaai.log" || true

    DB_FILE="$OUTPUT_DIR/database/FastAAI_database.sqlite.db"
    if [ -f "$DB_FILE" ]; then
        fastaai db_query -q "$DB_FILE" -t "$DB_FILE" -o "$OUTPUT_DIR" \
            --output_style tsv --threads 1 2>>"$OUTPUT_DIR/fastaai.log" || true
    else
        echo "FastAAI build_db did not produce a database - see fastaai.log" >&2
    fi
else
    echo "fastaai executable not found in PATH" >&2
fi

if compgen -G "$OUTPUT_DIR/results/"*_results.txt > /dev/null; then
    awk 'FNR==1 && NR!=1 {next} {print}' "$OUTPUT_DIR"/results/*_results.txt > "$OUTPUT_DIR/fastaai_results.tsv"
fi
