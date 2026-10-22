#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_amrfinderplus 2>/dev/null || true

echo "Running AMRFinderPlus"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}
ORGANISM=${4:-none}

mkdir -p "$OUTPUT_DIR"

# The reference database lives in the shared databases folder (baclab db install amrfinderplus), not inside the
# conda environment, so it survives image updates. amrfinder_update keeps one folder per version: take the newest.
DB_ROOT="${AMRFINDERPLUS_DB_PATH:-/databases/AmrfinderplusDB}"
DB_ARGS=()
DB_DIR=$(find "$DB_ROOT" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n1)
if [ -n "$DB_DIR" ]; then
    DB_ARGS=(--database "$DB_DIR")
fi

for FILE in "$INPUT_DIR"/*; do
    if [ -f "$FILE" ]; then
        filename="$(basename "$FILE")"
        base="${filename%.*}"

        EXTRA_ARGS=""
        if [ -n "$ORGANISM" ] && [ "$ORGANISM" != "none" ]; then
            EXTRA_ARGS="--organism $ORGANISM"
        fi

        if command -v amrfinder &> /dev/null; then
            amrfinder -n "$FILE" --threads "$CORES_PER_JOB" "${DB_ARGS[@]}" $EXTRA_ARGS \
                -o "$OUTPUT_DIR/${base}_amrfinder.tsv" 2>>"$OUTPUT_DIR/amrfinder.log" || true
        else
            echo "amrfinder executable not found in PATH" >&2
        fi
    fi
done

if compgen -G "$OUTPUT_DIR"/*_amrfinder.tsv > /dev/null; then
    awk 'FNR==1 && NR!=1 {next} {print}' "$OUTPUT_DIR"/*_amrfinder.tsv > "$OUTPUT_DIR/amrfinderplus_results.tsv" 2>/dev/null || true
fi
