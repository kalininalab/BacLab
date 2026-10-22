#!/bin/bash

# See bigscape_script.sh: without this a failure would be masked by the trailing steps.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_panbgc

echo "Running PanBGC"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
ZOL_DB_PATH=$4

# zol reads its annotation databases from here (see download_zol_db.sh). The path is concatenated
# with file names by zol, so it needs the trailing slash.
export ZOL_DATA_PATH="${ZOL_DB_PATH%/}/"

mkdir -p "$OUTPUT_DIR/panbgc_log"

# All uploaded GenBank files are treated as ONE gene cluster family: with .gbk files directly in
# the input folder PanBGC writes <output>/single_family/.
python ~/panbgc/"Pipeline scripts"/PanBGC.py \
    -i "$INPUT_DIR" \
    -o "$OUTPUT_DIR/panbgc_run" \
    -log "$OUTPUT_DIR/panbgc_log" \
    -c "$CORES_PER_JOB" \
    -al "$(which astral-pro3)"

# PanBGC.py exits 0 even when a step failed ("Failed: 1/1 folders"), so check for its end product.
VIS="$OUTPUT_DIR/panbgc_run/single_family/Final_Results/Visualisation.json"
if [ ! -s "$VIS" ]; then
    echo "ERROR: PanBGC did not produce Visualisation.json; see the log below." >&2
    cat "$OUTPUT_DIR"/panbgc_run/error.txt >&2 2>/dev/null || true
    exit 1
fi
cp "$VIS" "$OUTPUT_DIR/panbgc_visualisation.json"

FINAL="$OUTPUT_DIR/panbgc_run/single_family/Final_Results"
cp "$FINAL/Consolidated_Report.tsv" "$OUTPUT_DIR/panbgc_report.tsv"
cp "$FINAL/heaps_law.json" "$OUTPUT_DIR/panbgc_heaps_law.json"
cp "$FINAL/Heatmap_Overview.pdf" "$OUTPUT_DIR/panbgc_heatmap.pdf" 2>/dev/null || true
