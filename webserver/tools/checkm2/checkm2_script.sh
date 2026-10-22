#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_checkm2 2>/dev/null || true

echo "Running CheckM2"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}
DB_PATH=${4:-/databases/Checkm2DB}

mkdir -p "$OUTPUT_DIR"

# CheckM2's DIAMOND-based model needs its reference DB; point it at the actual
# .dmnd file (DIAMOND fails immediately if handed the containing directory).
DMND_FILE="$(find "$DB_PATH" -name '*.dmnd' 2>/dev/null | head -1)"

EXT="fasta"
FIRST_FILE="$(ls "$INPUT_DIR" 2>/dev/null | head -1)"
case "$FIRST_FILE" in
    *.fna) EXT="fna" ;;
    *.fa) EXT="fa" ;;
    *.fasta) EXT="fasta" ;;
esac

if command -v checkm2 &> /dev/null; then
    DB_ARGS=()
    [ -n "$DMND_FILE" ] && DB_ARGS=(--database_path "$DMND_FILE")
    checkm2 predict --threads "$CORES_PER_JOB" --input "$INPUT_DIR" -x "$EXT" \
        --output-directory "$OUTPUT_DIR" --force "${DB_ARGS[@]}" 2>&1 || true
else
    echo "checkm2 executable not found in PATH" >&2
fi

if [ -f "$OUTPUT_DIR/quality_report.tsv" ]; then
    cp "$OUTPUT_DIR/quality_report.tsv" "$OUTPUT_DIR/checkm2_results.tsv"
fi
