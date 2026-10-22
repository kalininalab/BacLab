#!/bin/bash
# Creates the skeleton of a new tool: tools/new_tool.sh <name> "<Title>" <category>
# (category: qc, amr, strain, compgen, annot, search - see baclab/toolkit/menu.py)
set -e
NAME=$1; TITLE=$2; CATEGORY=${3:-annot}
if [ -z "$NAME" ] || [ -z "$TITLE" ]; then echo "usage: $0 <name> \"<Title>\" [category]"; exit 1; fi
if ! [[ "$NAME" =~ ^[a-z][a-z0-9]{1,23}$ ]]; then echo "the name must be 2-24 lowercase letters/digits, starting with a letter"; exit 1; fi
DIR="$(dirname "$0")/$NAME"
[ -e "$DIR" ] && { echo "$DIR already exists"; exit 1; }
mkdir -p "$DIR/install"

cat > "$DIR/tool.py" <<PY
from baclab.toolkit import Tool, cores, genome_form, table_results

tool = Tool(
    name='$NAME',
    title='$TITLE',
    category='$CATEGORY',
    description='One sentence about what $TITLE does.',
    form=genome_form(('.fasta', '.fa', '.fna'), min_files=1, max_files=20),
    args=lambda request: [cores()],               # script call: <script> <input dir> <output dir> *args
    outputs=['${NAME}_results.tsv'],              # what is kept (and zipped) from the output folder
    results=table_results('${NAME}_results.tsv', '$TITLE results', table_id='${NAME}ResultsTable'),
    # databases=['${NAME}'],                      # keys of baclab/db_catalog.py this tool needs
    citation=[
        {'text': 'Authors. Title. Journal. Year.', 'url': 'https://doi.org/...'},
    ],
    faq=['Upload one or more genome assemblies in FASTA format.',
         'Click Submit to run $TITLE.',
         'Download the results from the results page.'],
)
PY

cat > "$DIR/${NAME}_script.sh" <<SH
#!/bin/bash
set -e
eval "\$(conda shell.bash hook)"
conda activate --no-stack server_$NAME

INPUT_DIR=\$1
OUTPUT_DIR=\$2
CORES_PER_JOB=\$3

# TODO: run the tool on \$INPUT_DIR/* and write \$OUTPUT_DIR/${NAME}_results.tsv
SH
chmod +x "$DIR/${NAME}_script.sh"

cat > "$DIR/install/server_$NAME.yml" <<YML
name: server_$NAME
channels:
  - conda-forge
  - bioconda
dependencies:
  - $NAME
YML

cat > "$DIR/$NAME.html" <<'HTML'
{% extends "tool_base.html" %}
{% load static %}

{% block toolname %} __TITLE__ {% endblock %}

{% block accepted_files %} .fasta, .fa, .fna {% endblock %}

{% block hiddenStatusInputButtonsDiv %} hide {% endblock %}

{% block toolEntries %}
<div class="col s12 m8 offset-m2" style="width: 75%; margin-top: 20px; margin-left: 50px; margin-right: 50px;">
    <div class="compact-file-field">
        <div class="btn btn-small multi-file-btn">
            <span>Add genomes</span>
            <input id="genomes" type="file" name="genomes" accept=".fasta,.fa,.fna" multiple>
        </div>
    </div>
    <div id="genomes-list"></div>
</div>
<script src="{% static 'js/multi_file_upload.js' %}"></script>
<script>
    initMultiFileUpload({inputId: 'genomes', listId: 'genomes-list', extensions: ['.fasta', '.fa', '.fna'], minFiles: 1, maxFiles: {{ max_files }}});
</script>
{% endblock %}

{% block toolSpecificChecks %}
<script>
    function checkFields(){
        if (document.getElementById('genomes').files.length < 1) {
            alert('Please upload at least 1 file.');
            return false;
        }
        return true;
    }
</script>
{% endblock %}

{% block windowonloadjstoolspecific %}
    document.getElementById('fasta-input-container').hidden = true;
    document.getElementById('upload-input-container').hidden = true;
{% endblock %}
HTML
sed -i "s|__TITLE__|$TITLE|" "$DIR/$NAME.html"
echo "Created $DIR - edit tool.py, the script, the environment file and the page, add '$NAME,1' to enabled_tools.csv, see tools/README.md"
