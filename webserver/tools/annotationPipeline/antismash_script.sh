#!/bin/bash

eval "$(conda shell.bash hook)"

INPUT_DIR=$1
OUTPUT_DIR=$2
ANTISMASH_DB_PATH=$3
CORES_PER_JOB=$4
LOCAL_TESTING=$5

export OMPI_MCA_plm_rsh_agent=

for FILE in "$INPUT_DIR"/*; do
    case "$FILE" in
        *.fasta|*.fa|*.fna|*.fasta.gz|*.fa.gz|*.fna.gz|*.gbk|*.gb|*.gbff) ;;
        *) echo "Skipping non-allowed file: $FILE"; continue ;;
    esac
    
    FILENAME=$(basename -- "$FILE")
    FILE_OUT_DIR=$OUTPUT_DIR/$FILENAME

    mkdir -- "$FILE_OUT_DIR"

    echo "Processing file: $FILE with Antismash"

    conda activate --no-stack server_antismash
    if [ "LOCAL_TESTING" == "True" ]; then
        echo "ANTISMASH LOCAL TEST"
        antismash -c "$CORES_PER_JOB" --minimal --genefinding-tool prodigal --databases "$ANTISMASH_DB_PATH" --output-dir "$FILE_OUT_DIR/antismash/" --output-basename "$FILENAME" "$FILE"
    else
        echo "antismash -c '$CORES_PER_JOB' --cb-general --cb-knownclusters --cb-subclusters --asf --pfam2go --smcog-trees --genefinding-tool prodigal --databases '$ANTISMASH_DB_PATH' --output-dir '$FILE_OUT_DIR/antismash/' --output-basename '$FILENAME' '$FILE'"

        antismash -c "$CORES_PER_JOB" --cb-general --cb-knownclusters --cb-subclusters --asf --pfam2go --smcog-trees --genefinding-tool prodigal --databases "$ANTISMASH_DB_PATH" --output-dir "$FILE_OUT_DIR/antismash/" --output-basename "$FILENAME" "$FILE"
    fi

    # The way antiSMASH generates its HTML output causes it to apply an selinux
    # context with a constrained security level to some files. This level does
    # not allow access from the gunicorn process in the django container, which
    # breaks serving files from there. So unset this.
    if [ -d "$FILE_OUT_DIR/antismash/" ]; then
        chcon -R -l 's0' "$FILE_OUT_DIR/antismash/"
    fi

done