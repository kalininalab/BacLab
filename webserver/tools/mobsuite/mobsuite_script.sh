#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_mobsuite 2>/dev/null || true

echo "Running MOB-suite (mob_recon)"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=${3:-4}

mkdir -p "$OUTPUT_DIR"

# The plasmid reference database lives in the shared databases folder (baclab db install mobsuite), not inside the
# conda environment, so it survives image updates.
DB_ROOT="${MOBSUITE_DB_PATH:-/databases/MobsuiteDB}"
DB_ARGS=()
if [ -f "$DB_ROOT/ncbi_plasmid_full_seqs.fas" ]; then
    DB_ARGS=(-d "$DB_ROOT")
fi

for FILE in "$INPUT_DIR"/*; do
    if [ -f "$FILE" ]; then
        filename="$(basename "$FILE")"
        base="${filename%.*}"
        sample_out="$OUTPUT_DIR/$base"
        mkdir -p "$sample_out"

        if command -v mob_recon &> /dev/null; then
            mob_recon -i "$FILE" -o "$sample_out" -n "$CORES_PER_JOB" "${DB_ARGS[@]}" --force 2>>"$OUTPUT_DIR/mobsuite.log" || true
        else
            echo "mob_recon executable not found in PATH" >&2
        fi

        if [ -f "$sample_out/mobtyper_results.txt" ]; then
            cp "$sample_out/mobtyper_results.txt" "$OUTPUT_DIR/${base}_mobtyper_results.tsv"
        fi
    fi
done

if compgen -G "$OUTPUT_DIR"/*_mobtyper_results.tsv > /dev/null; then
    awk 'FNR==1 && NR!=1 {next} {print}' "$OUTPUT_DIR"/*_mobtyper_results.tsv > "$OUTPUT_DIR/mobsuite_results.tsv" 2>/dev/null || true
fi
