#!/bin/bash

eval "$(conda shell.bash hook)"
conda activate server_blast

echo "Running BLAST"

INPUT_DIR=$1
OUTPUT_DIR=$2
E_VALUE=$3
DATABASE=$4
TYPE=$5
COOCCURENCE=$6
MIN_PIDENT_COOCCURENCE=$7
MIN_QCOVS_COOCCURENCE=$8
CORES_PER_JOB=$9
RUN_CLINKER=${10}
ANTISMASH_RESULTS_PATH=${11}
SCRIPT_DIR="$(dirname "$0")"

for FILE in "$INPUT_DIR"/*; do
    FILENAME=$(basename -- "$FILE")

    if [ "$TYPE" == "blastp" ]; then
        blastp -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_pairwise.txt" -evalue "$E_VALUE" -outfmt "0" -num_threads "$CORES_PER_JOB"
        blastp -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_tabular.txt" -evalue "$E_VALUE" -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qcovs" -num_threads "$CORES_PER_JOB"
    fi

    if [ "$TYPE" == "blastn" ]; then
        blastn -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_pairwise.txt" -evalue "$E_VALUE" -outfmt "0" -num_threads "$CORES_PER_JOB"
        blastn -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_tabular.txt" -evalue "$E_VALUE" -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qcovs" -num_threads "$CORES_PER_JOB"
    fi

    if [ "$TYPE" == "tblastn" ]; then
        tblastn -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_pairwise.txt" -evalue "$E_VALUE" -outfmt "0" -num_threads "$CORES_PER_JOB"
        tblastn -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_tabular.txt" -evalue "$E_VALUE" -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qcovs" -num_threads "$CORES_PER_JOB"
    fi

    if [ "$TYPE" == "blastx" ]; then
        blastx -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_pairwise.txt" -evalue "$E_VALUE" -outfmt "0" -num_threads "$CORES_PER_JOB"
        blastx -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_tabular.txt" -evalue "$E_VALUE" -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qcovs" -num_threads "$CORES_PER_JOB"
    fi

    if [ "$TYPE" == "tblastx" ]; then
        tblastx -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_pairwise.txt" -evalue "$E_VALUE" -outfmt "0" -num_threads "$CORES_PER_JOB"
        tblastx -db "$DATABASE" -query "$FILE" -out "$OUTPUT_DIR/${FILENAME}_tabular.txt" -evalue "$E_VALUE" -outfmt "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qcovs" -num_threads "$CORES_PER_JOB"
    fi

    if [ "$COOCCURENCE" == "on" ]; then
        python3 "$SCRIPT_DIR/cooccuring_finder.py" "$FILE" "$OUTPUT_DIR/${FILENAME}_tabular.txt" "$OUTPUT_DIR/${FILENAME}_cooccurrence.txt" "$MIN_PIDENT_COOCCURENCE" "$MIN_QCOVS_COOCCURENCE"
    fi


    if [ "$RUN_CLINKER" == "True" ]; then
        conda deactivate
        conda activate server_cblaster

        python3 "$SCRIPT_DIR/clinker_generator.py" "$OUTPUT_DIR/${FILENAME}_tabular.txt" "$OUTPUT_DIR/${FILENAME}_clinker" "$ANTISMASH_RESULTS_PATH"

        clinker "$OUTPUT_DIR/${FILENAME}_clinker" -p "$OUTPUT_DIR/plot.html"

        rm -fr "$OUTPUT_DIR/${FILENAME}_clinker"

        python3 "$SCRIPT_DIR/itol_annotation_writer.py" "$OUTPUT_DIR/${FILENAME}_tabular.txt" "$OUTPUT_DIR/"

        conda deactivate
        conda activate server_blast
    fi

done
