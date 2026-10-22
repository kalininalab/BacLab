import os

from django.conf import settings
from django.shortcuts import render

import pandas as pd

from baclab.toolkit import Tool, cores, matching_file_in_dir
from baclab.toolkit.files import prune_paths


def rename_fasta(request, input_dir):
    """GTDB-Tk looks for .fna files: whole-genome jobs get their .fasta/.fa uploads renamed."""
    if request.POST.get('taxonomy_type', 'wholegenome') == 'wholegenome' and os.path.exists(input_dir):
        for file in os.listdir(input_dir):
            if file.endswith('.fasta') or file.endswith('.fa'):
                os.rename(os.path.join(input_dir, file), os.path.join(input_dir, os.path.splitext(file)[0] + '.fna'))


def arguments(request):
    return [request.POST.get('taxonomy_type', 'wholegenome'),
            getattr(settings, 'BLAST_DATABASE_PATH', '/databases/BlastDB'),
            getattr(settings, 'GTDBTK_DB_PATH', '/databases/GTDBTkDB'),
            getattr(settings, 'NCBI_TAXA_DB_PATH', '/databases/NcbiTaxaDB'),
            cores()]


def post_process(ctx):
    """Keep the parsed taxonomy table (or the 16S one); if there is none, the logs."""
    import shutil
    output_dir, downloads_dir = ctx['output_dir'], ctx['downloads_dir']
    prune_paths(output_dir, ['identify', 'align'])   # GTDB-Tk's working data
    os.makedirs(downloads_dir, exist_ok=True)
    try:
        if 'parsed_taxonomy.tsv' in os.listdir(output_dir):
            shutil.copy(os.path.join(output_dir, 'parsed_taxonomy.tsv'), os.path.join(downloads_dir, 'parsed_taxonomy.tsv'))
        elif '16s_taxonomy_results.tsv' in os.listdir(output_dir):
            shutil.copy(os.path.join(output_dir, '16s_taxonomy_results.tsv'), os.path.join(downloads_dir, '16s_taxonomy_results.tsv'))
    except Exception:
        for file in os.listdir(output_dir):
            if file.endswith('.log'):
                shutil.copy(os.path.join(output_dir, file), os.path.join(downloads_dir, file))


def taxonomyfinder_results(request, job_id, download_dir):
    results_file = matching_file_in_dir(download_dir, '*_taxonomy_results.tsv', '*parsed_taxonomy.tsv')

    if not results_file:
        return None

    columns = ["Strain", "Domain", "Phylum", "Class", "Order", "Family", "Genus", "Species"]
    try:
        df = pd.read_csv(results_file, sep="\t", engine='python', header=0, usecols=columns)
    except:
        df = pd.DataFrame(columns=columns)
    df_taxonomy_results_html = df.to_html(classes='display', escape=False, table_id='taxonomyResultsTable', index=False)

    context =  {
        'job_id': job_id,
        'taxonomyResultsTable': df_taxonomy_results_html,
    }
    return render(request, 'results_taxonomy.html', context)



tool = Tool(
    name='taxonomyfinder',
    title='Taxonomy Finder (GTDB-Tk / 16S)',
    category='strain',
    settings_key='taxonomy',   # the key the tool switches and enabled_tools.csv use
    file_only=False,
    requires_databases=False,   # 16S mode and whole-genome mode need different databases
    prepare_inputs=rename_fasta,
    args=arguments,
    post_process=post_process,
    results=taxonomyfinder_results,
    citation=[
        {
            'text': 'Chaumeil PA, Mussig AJ, Hugenholtz P, Parks DH. 2022. GTDB-Tk v2: memory friendly classification with the genome taxonomy database. Bioinformatics 38(23):5315-5316.',
            'url': 'https://github.com/Ecogenomics/GTDBTk',
        },
    ],
    example=[('phylogeny_example.fasta', 'taxonomyfinder_example.fasta')],   # 16S rRNA genes of 12 type strains
    example_post={'taxonomy_type': '16s'},   # the example is 16S, not a genome (the whole-genome mode needs the GTDB-Tk data and hours)

)
