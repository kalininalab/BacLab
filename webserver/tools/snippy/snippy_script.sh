#!/bin/bash

eval "$(conda shell.bash hook)" 2>/dev/null || true
conda activate --no-stack server_snippy 2>/dev/null || true

echo "Running Snippy"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES=${3:-4}
REFERENCE_SOURCE=${4:-"upload"}
REFERENCE_TAXID=$5
REF_FILENAME=$6

mkdir -p "$OUTPUT_DIR"

# Identify Reference and Query Files
REF_FASTA=""

if [ "$REFERENCE_SOURCE" = "taxid" ] && [ -n "$REFERENCE_TAXID" ]; then
    echo "Fetching reference for TaxID: $REFERENCE_TAXID"
    datasets download genome taxon "$REFERENCE_TAXID" --reference --include genome,gbff --filename "$OUTPUT_DIR/ref.zip"
    if [ -f "$OUTPUT_DIR/ref.zip" ]; then
        unzip -q "$OUTPUT_DIR/ref.zip" -d "$OUTPUT_DIR/ref"
        
        # Try to find GenBank format first for annotations
        REF_FASTA=$(find "$OUTPUT_DIR/ref" -name "*.gbff" | head -n 1)
        if [ -z "$REF_FASTA" ]; then
            REF_FASTA=$(find "$OUTPUT_DIR/ref" -name "*.fna" -o -name "*.fasta" | head -n 1)
        fi
        
        if [ -n "$REF_FASTA" ]; then
            echo "Found reference: $REF_FASTA"
        else
            echo "Failed to find FASTA file in downloaded reference dataset."
        fi
    else
        echo "Failed to fetch reference for TaxID $REFERENCE_TAXID"
    fi
else
    if [ -n "$REF_FILENAME" ]; then
        REF_FASTA="$INPUT_DIR/$REF_FILENAME"
    else
        # Fallback to finding a fasta file that has "ref" in its name
        REF_FASTA=$(find "$INPUT_DIR" -maxdepth 1 -type f -name "*ref*.fna" -o -name "*ref*.fasta" | head -n 1)
    fi
    # If not found or example data is used
    if [ ! -f "$REF_FASTA" ]; then
        REF_FASTA=$(find "$INPUT_DIR" -maxdepth 1 -type f -name "*.fna" -o -name "*.fasta" | head -n 1)
    fi
    echo "Using uploaded reference: $REF_FASTA"
fi

# Stop if no reference
if [ ! -f "$REF_FASTA" ] || [ -z "$REF_FASTA" ]; then
    echo "Error: Reference genome not found." >&2
    exit 1
fi

# Run snippy for each reads/contigs file (excluding the reference itself)
# We support contigs for snippy (--ctgs)
for FILE in "$INPUT_DIR"/*; do
    if [ -f "$FILE" ]; then
        filename="$(basename "$FILE")"
        # Skip the reference file
        if [ "$FILE" = "$REF_FASTA" ]; then
            continue
        fi

        # Also skip other files like .zip if they ended up there, only process sequences
        if [[ "$filename" == *.fasta || "$filename" == *.fna || "$filename" == *.fa || "$filename" == *.fastq || "$filename" == *.fq || "$filename" == *.gz ]]; then
            base="${filename%.*}"
            # If gz, remove another extension
            if [[ "$filename" == *.gz ]]; then
                base2="${base%.*}"
                base=$base2
            fi

            sample_out="$OUTPUT_DIR/$base"
            echo "Running snippy for sample $base"
            
            # Determine if contigs or reads. snippy expects reads (--R1 --R2 or --se) or contigs (--ctgs).
            # If file extension is fasta/fna/fa, treat as contigs.
            if [[ "$filename" == *.fasta || "$filename" == *.fna || "$filename" == *.fa ]]; then
                snippy --cpus "$CORES" --outdir "$sample_out" --ref "$REF_FASTA" --ctgs "$FILE" --force
            else
                snippy --cpus "$CORES" --outdir "$sample_out" --ref "$REF_FASTA" --se "$FILE" --force
            fi
        fi
    fi
done

# Clean up reference files if they were fetched
if [ "$REFERENCE_SOURCE" = "taxid" ] && [ -n "$REFERENCE_TAXID" ]; then
    echo "Cleaning up reference dataset files..."
    rm -rf "$OUTPUT_DIR/ref.zip" "$OUTPUT_DIR/ref"
fi

echo "Snippy runs completed!"
