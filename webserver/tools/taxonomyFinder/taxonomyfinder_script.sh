#!/bin/bash

eval "$(conda shell.bash hook)"

conda activate --no-stack server_taxonomy

echo "Running Taxonomy Finder"

INPUT_DIR=$1
OUTPUT_DIR=$2
TYPE=$3
DATABASE=$4
GTDBTK_DB_PATH=$5
NCBI_TAXA_DB_PATH=$6
CORES_PER_JOB=$7
SCRIPT_DIR="$(dirname "$0")"

if [ "$TYPE" == "wholegenome" ]; then

    export GTDBTK_DATA_PATH="$GTDBTK_DB_PATH"

    mkdir "$OUTPUT_DIR/tmp"

    gtdbtk classify_wf --genome_dir "$INPUT_DIR" --out_dir "$OUTPUT_DIR" --cpus "$CORES_PER_JOB" --pplacer_cpus 1 --scratch_dir "$OUTPUT_DIR/tmp" || exit 1

    python3 "$SCRIPT_DIR/gtdbtk_output_parser.py" "$OUTPUT_DIR" || exit 1
    
fi

if [ "$TYPE" == "16s" ]; then
    for FILE in "$INPUT_DIR"/*; do
        python3 "$SCRIPT_DIR/taxonomyfinder_16s.py" "$FILE" "$OUTPUT_DIR" "$DATABASE/16S_ribosomal_RNA" "$NCBI_TAXA_DB_PATH"
    done
fi
