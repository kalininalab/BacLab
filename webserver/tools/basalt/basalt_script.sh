#!/bin/bash

# See bigscape_script.sh: without this a failure would be masked by the trailing steps.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_basalt

echo "Running BASALT"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
BASALT_DB_PATH=$4
CHECKM2_DB_PATH=$5
RAM_GB=$6
SENSITIVITY=$7

# Trained models (see download_basalt_db.sh) and the CheckM2 DIAMOND database, both from the
# shared databases folder.
export BASALT_WEIGHT="$BASALT_DB_PATH/BASALT_WEIGHT"
export CHECKM2DB=$(find "$CHECKM2_DB_PATH" -name "*.dmnd" | head -n1)

# The web layer renames the uploads to these fixed names (keeping their extensions).
ASSEMBLY=$(ls "$INPUT_DIR"/assembly.* | head -n1)
READ1=$(ls "$INPUT_DIR"/read1.* | head -n1)
READ2=$(ls "$INPUT_DIR"/read2.* | head -n1)

# BASALT writes its working files and the final bins into the current directory. Its -s option
# uses "/" to separate samples, so reads cannot be given as absolute paths: link the inputs into the
# working directory (keeping their extensions) and pass bare file names.
cd "$OUTPUT_DIR"
ln -sf "$ASSEMBLY" "assembly.${ASSEMBLY#*assembly.}"
ln -sf "$READ1" "read1.${READ1#*read1.}"
ln -sf "$READ2" "read2.${READ2#*read2.}"
BASALT -a "assembly.${ASSEMBLY#*assembly.}" -s "read1.${READ1#*read1.},read2.${READ2#*read2.}" -t "$CORES_PER_JOB" -m "$RAM_GB" -o basalt \
    --sensitive "$SENSITIVITY" --refinepara quick

# The final bins are written to <-o name>/ (here ./basalt/) as bin*.fa, next to OLC_quality_report.tsv.
if ! ls "$OUTPUT_DIR"/basalt/bin*.fa > /dev/null 2>&1; then
    echo "ERROR: BASALT produced no bins." >&2
    exit 1
fi
mkdir -p "$OUTPUT_DIR/basalt_bins"
cp "$OUTPUT_DIR"/basalt/bin*.fa "$OUTPUT_DIR/basalt_bins/"
cp "$OUTPUT_DIR/basalt/OLC_quality_report.tsv" "$OUTPUT_DIR/basalt_quality_report.tsv"
