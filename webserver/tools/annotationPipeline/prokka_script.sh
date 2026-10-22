#!/bin/bash

eval "$(conda shell.bash hook)"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3

for FILE in "$INPUT_DIR"/*; do

    case "$FILE" in
        *.fasta|*.fa|*.fna|*.fasta.gz|*.fa.gz|*.fna.gz) ;;
        *) echo "Skipping non-fasta file: $FILE"; continue ;;
    esac

    FILENAME=$(basename -- "$FILE")
    FILE_OUT_DIR="$OUTPUT_DIR/$FILENAME"

    mkdir -- "$FILE_OUT_DIR"

    echo "Processing file: $FILE"

    conda activate --no-stack server_prokka

    prokka --outdir "$FILE_OUT_DIR/prokka/" --cpus "$CORES_PER_JOB" "$FILE" --force

done