#!/bin/bash

eval "$(conda shell.bash hook)"

INPUT_DIR=$1
OUTPUT_DIR=$2
TYPE=$3
ADDITIONAL_FILE=$4
CORES_PER_JOB=$5

SCRIPT_DIR="$(dirname "$0")"

conda activate --no-stack server_phylogeny

TEMP_INPUT_DIR=""
if [ -n "${ADDITIONAL_FILE}" ] && [ -f "${ADDITIONAL_FILE}" ]; then
    TEMP_INPUT_DIR="$OUTPUT_DIR/tmp_input_with_additional"
    mkdir -p "$TEMP_INPUT_DIR"
    echo "Creating concatenated input files in $TEMP_INPUT_DIR using additional file: $ADDITIONAL_FILE"
    for FILE in "$INPUT_DIR"/*; do
        if [ -f "$FILE" ]; then
            filename="$(basename "$FILE")"
            base="${filename%.*}"
            out="$TEMP_INPUT_DIR/${base}_with_additional.fasta"
            # If file is empty, create a header-only file
            if [ ! -s "$FILE" ]; then
                printf '>USER_INPUT\n' > "$out"
            else
                # Get first non-empty line to check for a FASTA header
                first_line=$(awk 'NF{print; exit}' "$FILE" 2>/dev/null || true)
                if [[ "$first_line" == ">"* ]]; then
                    cat "$FILE" > "$out"
                else
                    # Prepend the required header exactly as requested
                    printf '>USER_INPUT\n' > "$out"
                    cat "$FILE" >> "$out"
                fi
            fi

            # Ensure there's a newline before appending the additional file
            lastchar=$(tail -c 1 "$out" 2>/dev/null || printf '')
            if [ -n "$lastchar" ] && [ "$lastchar" != $'\n' ]; then
                printf '\n' >> "$out"
            fi

            # Append the additional file
            cat "$ADDITIONAL_FILE" >> "$out"
        fi
    done
fi

# Use the temp dir if it exists, otherwise the original input dir
PROC_INPUT_DIR="$INPUT_DIR"
if [ -n "$TEMP_INPUT_DIR" ] && [ -d "$TEMP_INPUT_DIR" ]; then
    PROC_INPUT_DIR="$TEMP_INPUT_DIR"
fi

if [ "$TYPE" == "iqtree" ]; then
    for FILE in "$PROC_INPUT_DIR"/*; do
        filename="$(basename "$FILE")"
        base="${filename%.*}"
        aln="$OUTPUT_DIR/${base}_aligned.aln"
        prefix="$OUTPUT_DIR/${base}_tree"
        mafft --auto --thread "$CORES_PER_JOB" "$FILE" > "$aln"
        dnd_file="$INPUT_DIR/${base}.dnd"
        if [ -f "$dnd_file" ]; then
            cp -- "$dnd_file" "$OUTPUT_DIR/"
        fi
        iqtree -s "$aln" -nt "$CORES_PER_JOB" -bb 1000 -alrt 1000 -czb -pre "$prefix"
    done
fi

if [ "$TYPE" == "fasttree" ]; then
    for FILE in "$PROC_INPUT_DIR"/*; do
        echo "Processing file: $FILE"
        filename="$(basename "$FILE")"
        base="${filename%.*}"
        aln="$OUTPUT_DIR/${base}_aligned.fasta"
        tree="$OUTPUT_DIR/${base}_tree.nwk"
        mafft --auto --thread "$CORES_PER_JOB" "$FILE" > "$aln"
        dnd_file="$INPUT_DIR/${base}.dnd"
        if [ -f "$dnd_file" ]; then
            cp -- "$dnd_file" "$OUTPUT_DIR/"
        fi
        FastTree -gtr -nt -pseudo -spr 4 -mlacc 2 -slownni "$aln" > "$tree"
    done
fi

# Cleanup temporary input directory if it was created
if [ -n "$TEMP_INPUT_DIR" ] && [ -d "$TEMP_INPUT_DIR" ]; then
    rm -rf "$TEMP_INPUT_DIR"
fi