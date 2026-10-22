import glob
import os

import pandas as pd
from django.shortcuts import render

from baclab.toolkit import Tool, cores, matching_file_in_dir


def plasmidfinder_results(request, job_id, download_dir):
    results_file = matching_file_in_dir(download_dir, '*_results.tsv', 'results_tab.tsv', 'results_tab.txt', '*results*.tsv', '*results*.txt')
    if not results_file:
        sub_results = glob.glob(os.path.join(download_dir, '*', 'results_tab.tsv')) + glob.glob(os.path.join(download_dir, '*', 'results_tab.txt')) + glob.glob(os.path.join(download_dir, '*', '*.tsv'))
        if sub_results:
            results_file = sorted(sub_results)[0]

    if not results_file:
        return None

    try:
        df = pd.read_csv(results_file, sep="\t", engine='python', header=0)
        df_html = df.to_html(classes='display', escape=False, table_id='plasmidfinderResultsTable', index=False)
    except Exception:
        try:
            df = pd.read_csv(results_file, sep=r"\s+", engine='python', header=0)
            df_html = df.to_html(classes='display', escape=False, table_id='plasmidfinderResultsTable', index=False)
        except Exception:
            df_html = "<p>No plasmid hits found or error parsing results table.</p>"

    context = {
        'job_id': job_id,
        'plasmidfinderResultsTable': df_html,
    }
    return render(request, 'results_plasmidfinder.html', context)


tool = Tool(
    name='plasmidfinder',
    title='PlasmidFinder',
    category='amr',
    file_only=True,
    args=lambda request: [request.POST.get('minimum_identity', '60'), request.POST.get('minimum_coverage', '60'), cores(), request.POST.get('database', 'all')],
    results=plasmidfinder_results,
    citation=[
        {
            'text': 'Carattoli A, Zankari E, Garcia-Fernandez A, Voldby Larsen M, Lund O, Villa L, Aarestrup FM, Hasman H. 2014. In silico detection and typing of plasmids using PlasmidFinder and plasmid multilocus sequence typing. Antimicrobial Agents and Chemotherapy 58(7):3895-3903.',
        },
    ],
    example=[('klebsiella_pneumoniae_HS11286.fna', 'klebsiella_pneumoniae_HS11286.fna')],   # a clinical isolate with several plasmids
    faq=["Upload your bacterial genome assemblies in FASTA format ('.fasta', '.fna', '.fa').",
         'Optionally adjust the minimum identity and minimum coverage thresholds.',
         'Click Submit to start the PlasmidFinder job. You will receive a job ID and can view or download the results later.',
         'PlasmidFinder results can be viewed and downloaded on the results page.'],
)
