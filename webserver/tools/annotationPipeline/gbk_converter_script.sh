#!/bin/bash
set -euo pipefail

eval "$(conda shell.bash hook)"

INPUT_FILE=$1            # file path (or pattern)
OUTPUT_FILE=$2           # output file path
LOG_FILE="${3:-$(dirname "$OUTPUT_FILE")/gbk_converter.log}"

if [[ -z "${INPUT_FILE}" || -z "${OUTPUT_FILE}" ]]; then
  echo "Usage: $0 <input_file> <output_file> [log_file]" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"
mkdir -p "$(dirname "$LOG_FILE")"

# Log everything to LOG_FILE and also to console
exec > >(tee -a "$LOG_FILE") 2>&1

conda activate --no-stack server_antismash

found=0
for f in "$INPUT_FILE"; do
  [[ -e "$f" ]] || continue
  found=1
  out="$OUTPUT_FILE"
  echo "Converting: $f -> $out"
  python - "$f" "$out" <<'PY'
import sys, gzip
from Bio import SeqIO
inp, outp = sys.argv[1], sys.argv[2]
ih = gzip.open(inp, 'rt') if inp.endswith('.gz') else open(inp, 'r')
with ih as i, open(outp, 'w') as o:
    n = SeqIO.write(SeqIO.parse(i, 'genbank'), o, 'fasta')
    if n == 0:
        sys.stderr.write(f'No records written from {inp}\n')
PY
done

if [[ $found -eq 0 ]]; then
  echo "No GenBank files found in ${INPUT_FILE}" >&2
fi

echo "Done."