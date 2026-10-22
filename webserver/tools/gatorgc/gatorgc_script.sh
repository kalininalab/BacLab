#!/bin/bash

# See bigscape_script.sh: without this a failure would be masked by the trailing steps.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_gatorgc

echo "Running GATOR-GC"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3

# The two query files are renamed to fixed names by the web layer; every other upload is a genome.
REQUIRED=$(ls "$INPUT_DIR"/required_proteins.* | head -n1)
OPTIONAL=$(ls "$INPUT_DIR"/optional_proteins.* 2>/dev/null | head -n1 || true)

GENOMES_DIR="$OUTPUT_DIR/gator_genomes"
mkdir -p "$GENOMES_DIR"
for F in "$INPUT_DIR"/*; do
    case "$(basename "$F")" in
        required_proteins.*|optional_proteins.*) ;;
        *) cp "$F" "$GENOMES_DIR/$(basename "$F")" ;;
    esac
done

# Step 1: DIAMOND database + modular-domain table of all genomes; step 2: the actual search.
# The trailing slashes matter: without them GATOR-GC treats the directory as a single file.
pre-gator-gc -g "$GENOMES_DIR/" -o "$OUTPUT_DIR/gator_db" -t "$CORES_PER_JOB"

OPTIONAL_ARGS=()
if [ -n "$OPTIONAL" ]; then
    OPTIONAL_ARGS=(-op "$OPTIONAL")
fi
gator-gc -rq "$REQUIRED" "${OPTIONAL_ARGS[@]}" -g "$GENOMES_DIR/" -d "$OUTPUT_DIR/gator_db/" -o "$OUTPUT_DIR/gator_results" -t "$CORES_PER_JOB"

cp "$OUTPUT_DIR/gator_results/windows_genbanks/gator_hits.tsv" "$OUTPUT_DIR/gatorgc_results.tsv"
