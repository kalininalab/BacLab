#!/bin/bash
eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_spades 2>/dev/null || true

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES=${3:-4}

READ=$(find "$INPUT_DIR" -maxdepth 1 -type f | head -n 1)
R1=$(find "$INPUT_DIR" -maxdepth 1 -type f \( -name "*_1.*" -o -name "*_R1_*" -o -name "*R1.*" -o -name "*_1_*" \) | head -n 1)
R2=$(find "$INPUT_DIR" -maxdepth 1 -type f \( -name "*_2.*" -o -name "*_R2_*" -o -name "*R2.*" -o -name "*_2_*" \) | head -n 1)

if [ -n "$R1" ] && [ -n "$R2" ]; then
    fastp -i "$R1" -I "$R2" -o "$OUTPUT_DIR/cleaned_R1.fastq.gz" -O "$OUTPUT_DIR/cleaned_R2.fastq.gz" --json "$OUTPUT_DIR/fastp.json" --html "$OUTPUT_DIR/fastp.html" --thread "$CORES"
elif [ -f "$READ" ]; then
    fastp -i "$READ" -o "$OUTPUT_DIR/cleaned_R1.fastq.gz" --json "$OUTPUT_DIR/fastp.json" --html "$OUTPUT_DIR/fastp.html" --thread "$CORES"
fi
