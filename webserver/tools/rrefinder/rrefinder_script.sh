#!/bin/bash

# See bigscape_script.sh: without this a failure would be masked by the trailing steps.
set -e

eval "$(conda shell.bash hook)"

# Activating the env (not just calling its binaries) sets HHLIB, which exploratory mode needs.
conda activate --no-stack server_rrefinder

echo "Running RRE-Finder"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
MODE=$4

# All uploaded files must be of one kind: protein FASTA, or GenBank.
FIRST=$(ls "$INPUT_DIR"/* | head -n1)
case "${FIRST,,}" in
    *.gbk|*.gb|*.gbff) INTYPE=genbank ;;
    *) INTYPE=fasta ;;
esac
for F in "$INPUT_DIR"/*; do
    case "${F,,}" in
        *.gbk|*.gb|*.gbff) KIND=genbank ;;
        *) KIND=fasta ;;
    esac
    if [ "$KIND" != "$INTYPE" ]; then
        echo "ERROR: please upload either only protein FASTA files or only GenBank files." >&2
        exit 1
    fi
done

# RRE.py resolves data/... paths (config.ini) relative to its own folder and makes the output
# folder with a plain mkdir (so its parent must exist).
cd ~/rrefinder
python RRE.py -i "$INPUT_DIR" -t "$INTYPE" -m "$MODE" -c "$CORES_PER_JOB" -o "$OUTPUT_DIR/rrefinder_run" rrefinder

RUN_DIR="$OUTPUT_DIR/rrefinder_run/rrefinder"
cp "$RUN_DIR"/rrefinder_rrefam_results.txt "$OUTPUT_DIR/rrefinder_precision.tsv" 2>/dev/null || true
cp "$RUN_DIR"/rrefinder_rrefinder_results.txt "$OUTPUT_DIR/rrefinder_exploratory.tsv" 2>/dev/null || true
cp "$RUN_DIR"/rrefinder_rrefinder_RRE_resubmit_results.txt "$OUTPUT_DIR/rrefinder_exploratory_resubmit.tsv" 2>/dev/null || true
