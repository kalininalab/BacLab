#!/bin/bash

# See bigscape_script.sh: without this a failure would be masked by the trailing steps.
set -e

eval "$(conda shell.bash hook)"

conda activate --no-stack server_bigslice

echo "Running BiG-SLiCE"

INPUT_DIR=$1
OUTPUT_DIR=$2
CORES_PER_JOB=$3
BIGSLICE_DB_PATH=$4
THRESHOLD=$5

# BiG-SLiCE wants <input>/datasets.tsv plus one folder per dataset holding one sub-folder per
# genome, each with that genome's antiSMASH region .gbk files. Genome = file name before ".region".
BS_INPUT="$OUTPUT_DIR/bigslice_input"
mkdir -p "$BS_INPUT/dataset_1"
for GBK in "$INPUT_DIR"/*; do
    NAME=$(basename "$GBK")
    GENOME="${NAME%%.region*}"
    GENOME="${GENOME%.*}"
    mkdir -p "$BS_INPUT/dataset_1/$GENOME"
    cp "$GBK" "$BS_INPUT/dataset_1/$GENOME/$NAME"
done
printf '# Dataset name\tPath to folder\tPath to taxonomy\tDescription\ndataset_1\tdataset_1/\t\tUser dataset\n' > "$BS_INPUT/datasets.tsv"

bigslice -i "$BS_INPUT" "$OUTPUT_DIR/bigslice_run" \
    --program_db_folder "$BIGSLICE_DB_PATH/bigslice-models" \
    --threshold "$THRESHOLD" \
    --num_threads "$CORES_PER_JOB"

bigslice --export-tsv "$OUTPUT_DIR/bigslice_tsv" "$OUTPUT_DIR/bigslice_run" \
    --program_db_folder "$BIGSLICE_DB_PATH/bigslice-models"

# BiG-SLiCE exports the BGC->GCF assignment and the BGC metadata as two tables keyed by an
# internal id; join them into one readable table.
python - "$OUTPUT_DIR" <<'PY'
import sys
import pandas as pd
out = sys.argv[1]
meta = pd.read_csv(f"{out}/bigslice_tsv/bgc_metadata.tsv", sep="\t", index_col=0)
members = pd.read_csv(f"{out}/bigslice_tsv/gcf_membership.tsv", sep="\t", index_col=0)
members.columns = ["GCF"]
class_cols = [c for c in meta.columns if c.startswith("class-")]
table = meta[["genome", "bgc", "contig_edge", "len_nt"]].copy()
table["product_classes"] = meta[class_cols].apply(lambda r: ",".join(c[len("class-"):] for c in class_cols if r[c]), axis=1)
table = table.join(members, how="left")
# Distance of each BGC to its family (GCF) model, from BiG-SLiCE's database: 0 = at the family centre,
# larger = a looser fit; the BGC joins the family when it is within the clustering threshold.
import sqlite3
with sqlite3.connect(f"{out}/bigslice_run/result/data.db") as db:
    distances = dict(db.execute("SELECT bgc_id, membership_value FROM gcf_membership WHERE rank = 0"))
table["distance_to_GCF"] = [round(distances[i], 4) if i in distances else None for i in table.index]
table.index.name = "bgc_id"
table.to_csv(f"{out}/bigslice_results.tsv", sep="\t")
PY
