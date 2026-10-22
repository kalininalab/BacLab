import json
import os
import shutil
import subprocess

import pandas as pd
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import render

from baclab.toolkit import Tool, cores, matching_file_in_dir

GENOMEMINING_DATABASES = '/databases/GenomeMiningDB'


class GenomeMiningForm(forms.Form):
    """One sequence (file or pasted FASTA); the homolog search only takes a single one."""
    file = forms.FileField(required=False)
    fasta = forms.CharField(label='fasta', max_length=100000, required=False)
    run_homolog = forms.ChoiceField(choices=[('yes', 'Yes'), ('no', 'No')], required=False)
    use_example_data = forms.CharField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get('file')
        fasta = cleaned_data.get('fasta')
        run_homolog = cleaned_data.get('run_homolog')
        is_example = str(cleaned_data.get('use_example_data')).lower() in ['true', '1']

        provided_fields = sum([bool(file), bool(fasta)])
        if not is_example:
            if provided_fields > 1:
                raise ValidationError("You can only provide one of file or fastasequence")
            elif provided_fields == 0:
                raise ValidationError("You must provide one of file or fastasequence")

        content = ""
        if fasta:
            content = fasta
        elif file:
            content = file.read().decode('utf-8')
            file.seek(0)

        if content:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            if len(lines) < 2 or not lines[0].startswith('>'):
                raise ValidationError("Invalid FASTA format. It must contain at least one header line (starting with '>') and one sequence line.")
            if lines[1].startswith('>'):
                raise ValidationError("Invalid FASTA format. A sequence must follow the header.")

        if run_homolog == 'yes' and content.count('>') > 1:
            raise ValidationError("Only one sequence is allowed if you run homolog search.")
        return cleaned_data


def database_options():
    """The mining databases built in the admin (database_options.json in the GenomeMiningDB folder)."""
    try:
        with open(os.path.join(GENOMEMINING_DATABASES, 'database_options.json'), 'r') as f:
            options = json.load(f).get('database_options', [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        print(f"Error loading database options from {GENOMEMINING_DATABASES}: {error}")
        return []
    return [{'value': o['value'], 'label': o['label']} for o in options if isinstance(o, dict) and 'value' in o and 'label' in o]


def arguments(request):
    db_val = request.POST.get('database', 'default')
    if db_val == 'default':
        paths = [getattr(settings, 'CDS_POSITIONS_FASTA', f'{GENOMEMINING_DATABASES}/cds_positions.fasta'),
                 getattr(settings, 'BGC_INFO_CORE_PATH', f'{GENOMEMINING_DATABASES}/bgc_info_core'),
                 getattr(settings, 'BGC_INFO_PATH', f'{GENOMEMINING_DATABASES}/bgc_info'),
                 getattr(settings, 'PROKKA_INFO_PATH', f'{GENOMEMINING_DATABASES}/prokka_info')]
    else:
        folder = os.path.join(GENOMEMINING_DATABASES, db_val)
        paths = [os.path.join(folder, name) for name in ('cds_positions.fasta', 'bgc_info_core', 'bgc_info', 'prokka_info')]
    return paths + [request.POST.get('run_homolog', 'no'), cores()]


def post_process(ctx):
    output_dir, downloads_dir = ctx['output_dir'], ctx['downloads_dir']
    os.makedirs(downloads_dir, exist_ok=True)
    try:
        for file in os.listdir(output_dir):
            for ending in ('_closest_bgc_results_core_prot.tsv', '_PFAM.txt'):
                if file.endswith(ending):
                    shutil.copy2(os.path.join(output_dir, file), os.path.join(downloads_dir, file))
            for ending in ('_proteins.fasta', '_mining.log'):
                if file.endswith(ending):
                    os.remove(os.path.join(output_dir, file))
    except Exception:
        pass


def genomemining_results(request, job_id, download_dir):
    results_file = matching_file_in_dir(download_dir, '*_closest_bgc_results_core_prot.tsv')
    summary_file = matching_file_in_dir(download_dir, '*_PFAM.txt')

    if not results_file:
        return None

    try:
        df = pd.read_csv(results_file, sep="\t", engine='python', header=0)
        
        # Clean up column names for better readability
        cleaned_columns = []
        for col in df.columns:
            # Replace underscores with spaces and capitalize words
            new_col = col.replace('_', ' ').title()
            # Fix specific acronyms
            new_col = new_col.replace('Bgc', 'BGC').replace('Hmm', 'HMM')
            cleaned_columns.append(new_col)
            
        df.columns = cleaned_columns
        
        # Fill missing values (NaN) with "NA" string to preserve original formatting
        df = df.fillna('NA')
    except:
        df = pd.DataFrame()
    df_genomemining_results_html = df.to_html(classes='display', escape=False, table_id='genomeMiningResultsTable', index=False)

    summary_text = ""
    if summary_file and os.path.exists(summary_file):
        with open(summary_file, 'r') as f:
            summary_text = f.read()

    context = {
        'job_id': job_id,
        'genomeMiningResultsTable': df_genomemining_results_html,
        'genomeMiningSummary': summary_text,
    }
    return render(request, 'results_genomemining.html', context)



def build_custom_database(tmpdirname, db_name):
    """Build a mining database (Prokka + antiSMASH on every genome) from the FASTA files an administrator uploaded."""
    db_dir = os.path.join(GENOMEMINING_DATABASES, db_name)
    os.makedirs(db_dir, exist_ok=True)
    fasta_dir = os.path.join(db_dir, "fasta")
    os.makedirs(fasta_dir, exist_ok=True)
    for root, _, files in os.walk(tmpdirname):
        for f in files:
            if f.endswith((".fasta", ".fa", ".fna", ".faa")) and not f.startswith("._"):
                shutil.copy2(os.path.join(root, f), os.path.join(fasta_dir, f))

    cmd = (f"source /opt/conda/etc/profile.d/conda.sh && conda activate server_antismash && "
           f"python3 /app/tools/genomeMining/build_genomemining_db.py '{fasta_dir}' '{db_dir}'")
    proc = subprocess.run(cmd, shell=True, executable="/bin/bash", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    if proc.returncode != 0:
        # the admin sees this message on the database's page: say what went wrong, not only that something did
        tail = "\n".join(proc.stdout.strip().splitlines()[-12:])
        raise RuntimeError(f"Building the genome mining database failed (exit status {proc.returncode}). Last output:\n{tail}")

    json_path = os.path.join(GENOMEMINING_DATABASES, "database_options.json")
    os.makedirs(GENOMEMINING_DATABASES, exist_ok=True)
    options = {"database_options": []}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as jf:
                options = json.load(jf)
        except Exception:
            pass
    for opt in options.setdefault("database_options", []):
        if opt.get("value") == db_name:
            opt["label"] = f"{db_name} (Custom)"
            break
    else:
        options["database_options"].append({"value": db_name, "label": f"{db_name} (Custom)"})
    with open(json_path, "w") as jf:
        json.dump(options, jf, indent=4)


EXAMPLE_DATABASE = 'bacillus_example'


def example_settings():
    return {'database': EXAMPLE_DATABASE}


def example_check():
    """The example protein (Sfp, a surfactin-cluster enzyme) is searched in a database of two Bacillus genomes, which the administrator builds once."""
    if any(option['value'] == EXAMPLE_DATABASE for option in database_options()):
        return None
    return ("The example of Genome Mining searches a protein in a database built from two Bacillus genomes, which has not been built on this server. "
            "In the admin choose Custom databases, tool Genome Mining, database name 'bacillus_example', and upload tools/genomeMining/example_data/example_genomes.zip "
            "(the build runs Prokka and antiSMASH on both genomes and takes about half an hour).")


tool = Tool(
    name='genomemining',
    title='Genome Mining (InterProScan, HMMER, MAFFT)',
    category='annot',
    form=GenomeMiningForm,
    script='genome_mining_script.sh',
    args=arguments,
    post_process=post_process,
    results=genomemining_results,
    page_context=lambda: {'database_options': database_options()},
    custom_database=build_custom_database,
    citation=[
        {
            'text': 'Blin K, Shaw S, Augustijn HE, et al. 2023. antiSMASH 7.0: new and improved predictions for detection, regulation, chemical structures and visualisation. Nucleic Acids Research 51(W1):W46-W50.',
        },
        {
            'text': 'Seemann T. 2014. Prokka: rapid prokaryotic genome annotation. Bioinformatics 30(14):2068-2069.',
        },
    ],
    example=[('genomemining_example.fasta', 'genomemining_example.fasta')],
    example_post=example_settings,
    example_check=example_check,

)
