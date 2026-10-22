#!/bin/bash

# See padloc_script.sh: without this a tool failure would be masked by the trailing steps.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_genovi

echo "Running GenoVi"

INPUT_DIR=$1
OUTPUT_DIR=$2
GENOME_STATUS=$3

# GenoVi treats -o as a bare directory name relative to the cwd (it builds "<o>/<o>.png" itself)
# and puts its scratch files next to it, so run it from inside the job's output dir.
cd "$OUTPUT_DIR"

PLOTS=0
INDEX="$OUTPUT_DIR/genovi_plots.html"
echo "<!doctype html><html><head><meta charset=\"utf-8\"><title>GenoVi plots</title></head><body style=\"font-family:sans-serif\">" > "$INDEX"

for GENOME in "$INPUT_DIR"/*; do
    NAME=$(basename "$GENOME")
    NAME="${NAME%.*}"

    # Circos refuses to draw more than 200 ideograms (contigs). Skip such a file with a readable
    # message instead of GenoVi's own opaque "no element found" XML error on the empty SVG it
    # leaves behind.
    CONTIG_COUNT=$(grep -c '^LOCUS' "$GENOME" || true)
    if [ "$CONTIG_COUNT" -gt 200 ]; then
        echo "WARNING: $NAME has $CONTIG_COUNT contigs; Circos can draw at most 200 - skipped." >&2
        echo "<h3>$NAME</h3><p>Skipped: $CONTIG_COUNT contigs found, at most 200 can be drawn. Please provide a less fragmented assembly.</p>" >> "$INDEX"
        continue
    fi

    # -cu skips the DeepNOG COG classification (needs a large separate model download).
    genovi -i "$GENOME" -s "$GENOME_STATUS" -cu -o "genovi_$NAME"

    cp "genovi_$NAME/genovi_$NAME.svg" "genovi_$NAME.svg"
    cp "genovi_$NAME/genovi_$NAME.png" "genovi_$NAME.png"
    echo "<h3>$NAME</h3><p><a href=\"genovi_$NAME.svg\">SVG</a> | <a href=\"genovi_$NAME.png\">PNG</a></p><img src=\"genovi_$NAME.svg\" style=\"max-width:100%;height:auto\">" >> "$INDEX"
    PLOTS=$((PLOTS + 1))
done

echo "</body></html>" >> "$INDEX"

if [ "$PLOTS" -eq 0 ]; then
    echo "ERROR: no genome could be plotted." >&2
    exit 1
fi
