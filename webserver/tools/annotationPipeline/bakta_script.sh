#!/bin/bash

eval "$(conda shell.bash hook)"

INPUT_DIR=$1
OUTPUT_DIR=$2
BAKTA_DB_PATH=$3
CORES_PER_JOB=$4

for FILE in "$INPUT_DIR"/*; do
    FILENAME=$(basename -- "$FILE")
    FILE_OUT_DIR=$OUTPUT_DIR/$FILENAME

    mkdir -- "$FILE_OUT_DIR"

    echo "Processing file: $FILE with bakta"

    conda activate --no-stack server_bakta
    
    ACTUAL_DB_PATH="$BAKTA_DB_PATH"
    if [ -d "$BAKTA_DB_PATH/db" ]; then
        ACTUAL_DB_PATH="$BAKTA_DB_PATH/db"
    elif [ -d "$BAKTA_DB_PATH/db-light" ]; then
        ACTUAL_DB_PATH="$BAKTA_DB_PATH/db-light"
    fi

    bakta --db "$ACTUAL_DB_PATH" --output "$FILE_OUT_DIR/bakta/" "$FILE" -t "$CORES_PER_JOB"

done