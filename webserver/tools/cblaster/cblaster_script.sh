#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

eval "$(conda shell.bash hook)"

conda activate server_snakemake

INPUT_DIR=$1
OUTPUT_DIR=$2
MODE=$3
DATABASE=$4
SEARCH_INTERMEDIATE=$5
OUTPUT_DECIMALS=$6
BINARY_DECIMALS=$7
BINARY_KEY=$8
HITLIST_SIZE=$9
GAP=${10}
UNIQUE=${11}
MIN_HITS=${12}
PERCENTAGE=${13}
MAX_E_VALUE=${14}
MIN_IDENTITY=${15}
MIN_QUERY_COVERAGE=${16}
MAX_DISTANCE=${17}
MAX_CLUSTERS=${18}
DMND_SENSITIVITY=${19}
CORES_PER_JOB=${20}

for FILE in "$INPUT_DIR"/*; do
    if [ ! -f "$FILE" ]; then continue; fi
    FILENAME=$(basename -- "$FILE")
    YAML_FILE=${FILENAME}.yml

    cat <<EOF > "$YAML_FILE"
query_file: '$FILE'

mode: '$MODE'
database: '$DATABASE'

path_output: '$OUTPUT_DIR/$FILENAME'
retries: 0
# num_threads: 40
search_intermediate: $SEARCH_INTERMEDIATE

search_kwargs:
  # output options
  output_decimals: $OUTPUT_DECIMALS
  binary_decimals: $BINARY_DECIMALS
  binary_key: '$BINARY_KEY'
  # search options
  hitlist_size: $HITLIST_SIZE
  # clustering options
  gap: $GAP
  unique: $UNIQUE
  min_hits: $MIN_HITS
  percentage: $PERCENTAGE
  # filtering options
  max_evalue: $MAX_E_VALUE
  min_identity: $MIN_IDENTITY
  min_coverage: $MIN_QUERY_COVERAGE
  dmnd_sensitivity: '$DMND_SENSITIVITY'

# kwargs for searching intermediate genes (runs separately):
intermediate_kwargs:
  max_distance: $MAX_DISTANCE
  max_clusters: $MAX_CLUSTERS
EOF

    snakemake -s "$SCRIPT_DIR/cblaster-single-run.smk" --configfile "$YAML_FILE" --use-conda --cores "$CORES_PER_JOB"
    rm -- "$YAML_FILE"
done

# Clean up snakemake's shadow directory, we don't need to send that to the user
rm -rf .snakemake