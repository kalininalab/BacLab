#!/bin/bash

# See gecco_script.sh: without this a tool failure would be masked by the trailing cp commands.
set -e

eval "$(conda shell.bash hook)"

# Activating the env (rather than just calling its binary) is what sets GToTree_HMM_dir, which lets
# -H take just an SCG-set name.
conda activate --no-stack server_gtotree

echo "Running GToTree"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
HMM_SET=$4
HMM_DIR=$5

# The HMM sets come from the shared database folder (see download_gtotree_db.sh), GToTree is not to download them.
# It insists on a writable HMM folder though, and the shared one is read-only in production: give it a folder
# in the job with links to the files it needs.
if [ ! -s "${HMM_DIR%/}/${HMM_SET}.hmm" ]; then
    echo "ERROR: the HMM set $HMM_SET is not in $HMM_DIR (run tools/gtotree/download_gtotree_db.sh, see tools/DATABASES.md)" >&2
    exit 1
fi
export GToTree_HMM_dir="$OUTPUT_DIR/hmm_sets/"
mkdir -p "$GToTree_HMM_dir"
ln -s "${HMM_DIR%/}/${HMM_SET}.hmm" "${HMM_DIR%/}/hmm-sources-and-info.tsv" "$GToTree_HMM_dir"

ls -1 "$INPUT_DIR"/* > "$OUTPUT_DIR/genome_paths.txt"

GToTree -f "$OUTPUT_DIR/genome_paths.txt" -H "$HMM_SET" -o "$OUTPUT_DIR/gtotree_raw" -n 1 -j "$CORES_PER_JOB"

cp "$OUTPUT_DIR"/gtotree_raw/gtotree_raw.tre "$OUTPUT_DIR/gtotree_tree.nwk"
cp "$OUTPUT_DIR/gtotree_raw/Genomes_summary_info.tsv" "$OUTPUT_DIR/gtotree_genomes_summary.tsv"
cp "$OUTPUT_DIR/gtotree_raw/SCG_hit_counts.tsv" "$OUTPUT_DIR/gtotree_scg_hit_counts.tsv"
cp "$OUTPUT_DIR/gtotree_raw/Aligned_SCGs.faa" "$OUTPUT_DIR/gtotree_aligned_scgs.faa"
