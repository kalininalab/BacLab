#!/bin/bash

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_spades 2>/dev/null || true

echo "Running Assembly & QC Pipeline (fastp -> SPAdes -> QUAST -> MultiQC)"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES=${3:-4}
READ_TYPE=${4:-single}

mkdir -p "$OUTPUT_DIR/fastp"
mkdir -p "$OUTPUT_DIR/quast"
mkdir -p "$OUTPUT_DIR/multiqc"

if [ "$READ_TYPE" = "paired" ]; then
    R1=$(find "$INPUT_DIR" -maxdepth 1 -type f \( -name "*_1.*" -o -name "*_R1_*" -o -name "*R1.*" -o -name "*_1_*" \) | head -n 1)
    R2=$(find "$INPUT_DIR" -maxdepth 1 -type f \( -name "*_2.*" -o -name "*_R2_*" -o -name "*R2.*" -o -name "*_2_*" \) | head -n 1)
    
    if [ -n "$R1" ] && [ -n "$R2" ]; then
        echo "Running fastp QC..."
        fastp -i "$R1" -I "$R2" -o "$OUTPUT_DIR/fastp/cleaned_R1.fastq.gz" -O "$OUTPUT_DIR/fastp/cleaned_R2.fastq.gz" --json "$OUTPUT_DIR/fastp/fastp.json" --html "$OUTPUT_DIR/fastp/fastp.html" --thread "$CORES"
        
        echo "Running SPAdes assembly..."
        spades.py -1 "$OUTPUT_DIR/fastp/cleaned_R1.fastq.gz" -2 "$OUTPUT_DIR/fastp/cleaned_R2.fastq.gz" -o "$OUTPUT_DIR" -t "$CORES"
    else
        files=("$INPUT_DIR"/*)
        if [ ${#files[@]} -ge 2 ]; then
            echo "Running fastp QC..."
            fastp -i "${files[0]}" -I "${files[1]}" -o "$OUTPUT_DIR/fastp/cleaned_R1.fastq.gz" -O "$OUTPUT_DIR/fastp/cleaned_R2.fastq.gz" --json "$OUTPUT_DIR/fastp/fastp.json" --html "$OUTPUT_DIR/fastp/fastp.html" --thread "$CORES"
            
            echo "Running SPAdes assembly..."
            spades.py -1 "$OUTPUT_DIR/fastp/cleaned_R1.fastq.gz" -2 "$OUTPUT_DIR/fastp/cleaned_R2.fastq.gz" -o "$OUTPUT_DIR" -t "$CORES"
        else
            echo "Not enough files for paired-end assembly." >&2
            exit 1
        fi
    fi
else
    # Single-end logic
    READ=$(find "$INPUT_DIR" -maxdepth 1 -type f | head -n 1)
    if [ -f "$READ" ]; then
        echo "Running fastp QC..."
        fastp -i "$READ" -o "$OUTPUT_DIR/fastp/cleaned_R1.fastq.gz" --json "$OUTPUT_DIR/fastp/fastp.json" --html "$OUTPUT_DIR/fastp/fastp.html" --thread "$CORES"
        
        echo "Running SPAdes assembly..."
        spades.py -s "$OUTPUT_DIR/fastp/cleaned_R1.fastq.gz" -o "$OUTPUT_DIR" -t "$CORES"
    else
        echo "No input files found." >&2
        exit 1
    fi
fi

if [ -f "$OUTPUT_DIR/contigs.fasta" ]; then
    echo "Running QUAST assembly metrics..."
    quast.py "$OUTPUT_DIR/contigs.fasta" -o "$OUTPUT_DIR/quast" -t "$CORES"
    
    echo "Running CheckM completeness/contamination..."
    mkdir -p "$OUTPUT_DIR/checkm"
    checkm lineage_wf -t "$CORES" -x fasta "$OUTPUT_DIR" "$OUTPUT_DIR/checkm" || echo "CheckM failed (perhaps missing database?)"
    
    echo "Running MultiQC..."
    multiqc "$OUTPUT_DIR" -o "$OUTPUT_DIR/multiqc"
else
    echo "SPAdes did not produce contigs.fasta." >&2
    exit 1
fi

echo "Pipeline completed successfully!"
