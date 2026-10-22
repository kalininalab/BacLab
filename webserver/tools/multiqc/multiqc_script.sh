#!/bin/bash
set -e

eval "$(conda shell.bash hook)" 2>/dev/null || true
# MultiQC is installed as part of server_spades (see conda_environments/server_spades.yml)
conda activate --no-stack server_spades 2>/dev/null || true

echo "Running MultiQC"

INPUT_DIR=$1
OUTPUT_DIR=$2

mkdir -p "$OUTPUT_DIR"

# Users commonly upload a zip of QC reports from other tools; MultiQC does not
# look inside archives on its own, so extract any zips before scanning.
for ZIP_FILE in "$INPUT_DIR"/*.zip; do
    [ -f "$ZIP_FILE" ] || continue
    python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$ZIP_FILE" "$INPUT_DIR" \
        && rm -f "$ZIP_FILE"
done

if command -v multiqc &> /dev/null; then
    multiqc "$INPUT_DIR" -o "$OUTPUT_DIR" -n multiqc_report --force 2>&1 || true
else
    echo "multiqc executable not found in PATH" >&2
fi
