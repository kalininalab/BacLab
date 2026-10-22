#!/bin/bash

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_plasmidfinder 2>/dev/null || true

echo "Running PlasmidFinder"

INPUT_DIR=$1
OUTPUT_DIR=$2
MINIMUM_IDENTITY_RAW=${3:-60}
MINIMUM_COVERAGE_RAW=${4:-60}
MINIMUM_IDENTITY=$(awk "BEGIN {print $MINIMUM_IDENTITY_RAW/100}")
MINIMUM_COVERAGE=$(awk "BEGIN {print $MINIMUM_COVERAGE_RAW/100}")
CORES_PER_JOB=${5:-4}
DATABASE=${6:-"all"}

SCRIPT_DIR="$(dirname "$0")"

mkdir -p "$OUTPUT_DIR"

for FILE in "$INPUT_DIR"/*; do
    if [ -f "$FILE" ]; then
        filename="$(basename "$FILE")"
        base="${filename%.*}"
        sample_out="$OUTPUT_DIR/$base"
        mkdir -p "$sample_out"

        EXTRA_ARGS=""
        if [ -n "$DATABASE" ] && [ "$DATABASE" != "all" ]; then
            EXTRA_ARGS="-d $DATABASE"
        fi

        # Resolve databases directory dynamically based on script location
        DB_PATH="$(cd "$SCRIPT_DIR/../../.." && pwd)/databases/PlasmidFinderDB"
        EXTRA_ARGS="-x $EXTRA_ARGS -p $DB_PATH"

        if command -v plasmidfinder.py &> /dev/null; then
            plasmidfinder.py -i "$FILE" -o "$sample_out" -l "$MINIMUM_COVERAGE" -t "$MINIMUM_IDENTITY" $EXTRA_ARGS 2>&1 || true
        elif command -v plasmidfinder &> /dev/null; then
            plasmidfinder -i "$FILE" -o "$sample_out" -l "$MINIMUM_COVERAGE" -t "$MINIMUM_IDENTITY" $EXTRA_ARGS 2>&1 || true
        else
            echo "plasmidfinder executable not found in PATH" >&2
        fi

        # Consolidate standard output files to main output directory
        if [ -f "$sample_out/results_tab.tsv" ]; then
            cp "$sample_out/results_tab.tsv" "$OUTPUT_DIR/${base}_results.tsv"
        elif [ -f "$sample_out/results_tab.txt" ]; then
            cp "$sample_out/results_tab.txt" "$OUTPUT_DIR/${base}_results.tsv"
        fi

        if [ -f "$sample_out/data.json" ]; then
            cp "$sample_out/data.json" "$OUTPUT_DIR/${base}_data.json"
        fi
    fi
done

# Combine TSV results if available
if compgen -G "$OUTPUT_DIR/*_results.tsv" > /dev/null; then
    awk 'FNR==1 && NR!=1 {next} {print}' "$OUTPUT_DIR"/*_results.tsv > "$OUTPUT_DIR/plasmidfinder_results.tsv" 2>/dev/null || true
fi
