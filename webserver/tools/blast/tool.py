import json
import os
import re
import subprocess

import pandas as pd
from django.conf import settings
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.urls import path

from baclab.toolkit import Tool, cores, matching_file_in_dir
from baclab.toolkit.files import copy_output_to_downloads

BLAST_DATABASES = '/databases/BlastDB'


def database_options():
    """The BLAST databases offered on the page: database_options.json in the BlastDB folder (the admin's custom databases add to it)."""
    try:
        with open(os.path.join(settings.BLAST_DATABASE_PATH, 'database_options.json')) as handle:
            options = json.load(handle).get('database_options', [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        print(f"Error loading blast database options: {error}")
        return []
    validated = []
    for option in options:
        if not isinstance(option, dict) or not all(key in option for key in ('value', 'label', 'db_type')):
            print(f"Warning: Skipping blast option with missing required fields: {option}")
            continue
        db_type = option['db_type'].lower()
        if db_type not in ('nucl', 'prot'):
            print(f"Warning: Skipping blast option with invalid db_type '{db_type}': {option}")
            continue
        validated.append({'value': option['value'], 'label': option['label'], 'db_type': db_type, 'show_warning': option.get('show_warning', False)})
    return validated


def arguments(request):
    post = request.POST
    blastdb = post.get('blastdb', 'all_inhouse_bgcs_blastpDB')
    return [
        str(post.get('evalue', '1e-5')),
        blastdb if os.path.isabs(blastdb) else os.path.join(BLAST_DATABASES, blastdb),
        post.get('blast_type', 'blastp'),
        post.get('co-occurence', 'off'),
        str(post.get('min_pident_cooccurence', '40')),
        str(post.get('min_qcovs_cooccurence', '30')),
        cores(),
        'True' if blastdb == 'all_inhouse_bgcs_blastpDB' else 'False',
        '/databases/AntismashResults',
    ]


def post_process(ctx):
    copy_output_to_downloads(ctx['output_dir'], ctx['downloads_dir'])
    for file in os.listdir(ctx['downloads_dir']):
        if file.endswith('_pairwise.txt'):
            os.remove(os.path.join(ctx['downloads_dir'], file))


# ---- links from the hits to the in-house collection ----
def _subject_link_display(v: str):
    # Keep original if split not long enough
    parts = v.split("_")
    if len(parts) > 2:
        return parts[2]
    elif len(parts) == 2:
        return parts[1]
    return v


def make_sample_link(sample_name):
    """
    Expected sample_name pattern: contig<number>_<genome>.region<number>
    Produces: /sample?path_info=<genome>---r<contig>c<region>
    """
    m = re.match(r'contig_?([0-9]+)_(.+)\.region([0-9]+)', sample_name)
    if not m:
        return ''
    contig = m.group(1)
    genome = m.group(2)
    region = m.group(3).lstrip('0') or '0'
    return f'/sample?path_info={genome}---r{contig}c{region}'


def make_annotation_link(sample_name):
    """
    Expected sample_name pattern: StrainName_ProteinID
    Produces: /annotation/StrainName_ProteinID
    """
    m = re.match(r'(.+?)_(.+):', sample_name)
    if not m:
        return ''
    strain_name = m.group(1)
    protein_id = m.group(2)
    return f'/annotation/{strain_name}_{protein_id}'


def header_matches(header: str, subject_id: str) -> bool:
    h = header.strip().lstrip(">")
    if not h:
        return False
    first = h.split(" ")[0]
    return first == subject_id


def find_fasta_record_by_id(handle, subject_id: str):
    cur_header = None
    seq_parts = []
    for line in handle:
        if isinstance(line, bytes):
            line = line.decode("utf-8", "ignore")
        if line.startswith(">"):
            if cur_header is not None and header_matches(cur_header, subject_id):
                return f"#{cur_header}\n{''.join(seq_parts)}"
            cur_header = line[1:].strip()
            seq_parts = []
        else:
            if cur_header is not None:
                seq_parts.append(line.strip())
    if cur_header is not None and header_matches(cur_header, subject_id):
        return f">{cur_header}\n{''.join(seq_parts)}"
    return None



def annotation_strains():
    """File names of the in-house annotation database (looked up when a results page is built, so new strains show up at once)."""
    try:
        return os.listdir(settings.ANNOTATION_DB_PATH)
    except OSError:
        return []


def parse_subject_id(df):
    #Parsing of the subject ID column
    first_val = df["subject id"].iloc[0] if not df.empty else ""
    
    # Case 1: Myxo BGC specific (split by ;)
    if str(first_val).count(";") == 3:
        split_cols = df["subject id"].str.split(";", expand=True)
        df["subject id"] = split_cols[0].str.strip()
        df["locus tag"] = split_cols[1].str.strip()
        df["locus from"] = split_cols[2].str.strip()
        df["locus to"] = split_cols[3].str.strip()
        
        # Apply HTML links
        df["subject id"] = df["subject id"].apply(
            lambda v: f'<a title="{v}" href="{make_sample_link(v)}">{_subject_link_display(v)}</a>' 
            if make_sample_link(v) else v
        )
        return df[["query id", "subject id", "% 'identity'", "alignment length", "q. start", "q. end", "locus tag", "locus from", "locus to", "% query coverage per subject"]]

    # Case 2: AnnotationDB match
    prefix = str(first_val).split(':')[0].split('_')[0]
    if f"{prefix}.faa" in annotation_strains():
        df["subject id"] = df["subject id"].apply(
            lambda v: f'<a title="{v}" href="{make_annotation_link(v)}">{v}</a>' 
            if make_annotation_link(v) else v
        )
    
    return df[["query id", "subject id", "% 'identity'", "alignment length", "q. start", "q. end", "% query coverage per subject"]]


def blast_results(request, job_id, download_dir):
    blast_results = matching_file_in_dir(download_dir, '*_tabular.txt')
    cooccurrence_results = matching_file_in_dir(download_dir, '*_cooccurrence.txt')

    if not blast_results:
        return None

    cols = ["query id", "subject id", "% 'identity'", "alignment length", "q. start", "q. end", "% query coverage per subject"]
    try:
        df = pd.read_csv(blast_results, sep="\t", engine='python', header=None, usecols=[0,1,2,3,6,7,12])
        df.columns = cols
        df = parse_subject_id(df)
    except Exception:
        df = pd.DataFrame(columns=cols)
    df_html = df.to_html(classes='display', escape=False, table_id='blastResultsTable', index=False)

    co_occurence_df_html = None
    if cooccurrence_results:
        try:
            co_df = pd.read_csv(cooccurrence_results, sep="\t", engine='python', header=None, skiprows=1, usecols=[0,1,2])
            co_df.columns = ["Subject_ID", "Found_Genes", "Locations"]
            co_occurence_df_html = co_df.to_html(classes='display', escape=False, table_id='cooccurrenceTable', index=False)
        except Exception:
            pass

    context = {
        'job_id': job_id,
        'blastResultsTable': df_html,
        'cooccurrenceTable': co_occurence_df_html,
    }
    return render(request, 'results_blast.html', context)


def annotation_results_view(request, subject_id):
    if any(x in subject_id for x in ['..', '"', '\'', '//']):
        return HttpResponseBadRequest("Invalid subject ID")
    
    file_name = subject_id.split("_")[0]

    annotation_path = os.path.join(settings.ANNOTATION_DB_PATH, f"{file_name}.faa")

    if not os.path.isfile(annotation_path):
        return HttpResponseBadRequest("No results found for the given subject ID")

    raw_fasta = None
    with open(annotation_path, "rt", encoding="utf-8", errors="ignore") as fh:
        raw_fasta = find_fasta_record_by_id(fh, subject_id)

    if not raw_fasta:
        return HttpResponseBadRequest("Requested sequence not found in FASTA")

    return render(request, 'annotation_results_view.html', {'raw_fasta': raw_fasta})



def build_custom_database(tmpdirname, db_name):
    """Make a BLAST database from the FASTA files an administrator uploaded (admin -> Custom databases)."""
    combined_fasta = os.path.join(tmpdirname, "combined.fasta")
    with open(combined_fasta, "w") as outfile:
        for root, _, files in os.walk(tmpdirname):
            for f in files:
                if f == "combined.fasta":
                    continue
                if f.endswith((".fasta", ".fa", ".fna", ".faa")):
                    with open(os.path.join(root, f), "r") as infile:
                        outfile.write(infile.read())
                        outfile.write("\n")

    db_type = "nucl"
    with open(combined_fasta, "r") as cf:
        for line in cf:
            if not line.startswith(">"):
                if any(c in line.upper() for c in "EFILPQU"):
                    db_type = "prot"
                break

    out_path = os.path.join(BLAST_DATABASES, db_name)
    cmd = f"source /opt/conda/etc/profile.d/conda.sh && conda activate server_blast && makeblastdb -in '{combined_fasta}' -dbtype '{db_type}' -out '{out_path}' -title '{db_name}'"
    subprocess.run(cmd, shell=True, executable="/bin/bash", check=True)

    json_path = os.path.join(BLAST_DATABASES, "database_options.json")
    options = {"database_options": []}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as jf:
                options = json.load(jf)
        except Exception:
            pass

    for opt in options.get("database_options", []):
        if opt.get("value") == db_name:
            opt["label"] = f"{db_name} (Custom)"
            opt["db_type"] = db_type
            break
    else:
        options.setdefault("database_options", []).append({"value": db_name, "label": f"{db_name} (Custom)", "db_type": db_type})
    with open(json_path, "w") as jf:
        json.dump(options, jf, indent=4)


def example_settings():
    """The example is a nucleotide (16S) query: search it with blastn in the first nucleotide database the installation has."""
    nucleotide = [option['value'] for option in database_options() if option['db_type'] == 'nucl']
    return {'blast_type': 'blastn', 'blastdb': nucleotide[0] if nucleotide else 'none'}


tool = Tool(
    name='blast',
    title='BLAST',
    category='search',
    requires_databases=False,   # the page offers whatever databases are installed
    args=lambda request: arguments(request),
    post_process=post_process,
    results=blast_results,
    page_context=lambda: {'database_options': database_options()},
    custom_database=build_custom_database,
    urls=[path('annotation/<str:subject_id>', annotation_results_view, name='annotation_results_view')],
    citation=[
        {
            'text': 'Camacho C, Coulouris G, Avagyan V, Ma N, Papadopoulos J, Bealer K, Madden TL. 2009. BLAST+: architecture and applications. BMC Bioinformatics 10:421.',
        },
    ],
    example=[('blast_example.fasta', 'blast_example.fasta')],
    example_post=example_settings,
)
