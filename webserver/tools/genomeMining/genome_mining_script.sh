#!/bin/bash

eval "$(conda shell.bash hook)"
conda activate server_genomemining

echo "Running GenomeMining"

INPUT_DIR=$1
OUTPUT_DIR=$2
CDS_POSITIONS_FASTA=$3
BGC_INFO_CORE_PATH=$4
BGC_INFO_PATH=$5
PROKKA_INFO_PATH=$6
HOMOLOG_SEARCH=$7
CORES_PER_JOB=$8

SCRIPT_DIR="$(dirname "$0")"

python3 "$SCRIPT_DIR/genome_mining.py" "$INPUT_DIR" "$OUTPUT_DIR" "$CDS_POSITIONS_FASTA" "$BGC_INFO_CORE_PATH" "$BGC_INFO_PATH" "$PROKKA_INFO_PATH" "$HOMOLOG_SEARCH" "$CORES_PER_JOB"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "GenomeMining completed successfully."
elif [ $EXIT_CODE -eq 10 ]; then
    echo "GenomeMining Error: Failed to download InterPro family fasta."
    exit $EXIT_CODE
elif [ $EXIT_CODE -eq 11 ]; then
    echo "GenomeMining Error: phmmer command failed."
    exit $EXIT_CODE
elif [ $EXIT_CODE -eq 12 ]; then
    echo "GenomeMining Error: mafft alignment command failed."
    exit $EXIT_CODE
elif [ $EXIT_CODE -eq 13 ]; then
    echo "GenomeMining Error: hmmbuild command failed."
    exit $EXIT_CODE
elif [ $EXIT_CODE -eq 14 ]; then
    echo "GenomeMining Error: hmmsearch command failed."
    exit $EXIT_CODE
elif [ $EXIT_CODE -ne 0 ]; then
    echo "GenomeMining Error: Python script failed with exit code $EXIT_CODE."
    exit $EXIT_CODE
fi