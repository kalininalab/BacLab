import os

import pandas as pd
from django.conf import settings
from django.shortcuts import render

from baclab.toolkit import Tool, cores, matching_file_in_dir


def abricate_results(request, job_id, download_dir):
    results_file = matching_file_in_dir(download_dir, '*_results.tsv')
    summary_file = matching_file_in_dir(download_dir, '*_summary.tsv')

    if not results_file:
        return None

    columns = ["#FILE", "SEQUENCE", "START", "END", "GENE", "COVERAGE", "GAPS", "%COVERAGE", "%IDENTITY", "DATABASE", "ACCESSION", "PRODUCT", "RESISTANCE"]
    try:
        df = pd.read_csv(os.path.join(settings.DOWNLOAD_DIR, job_id, results_file), sep="\t", engine='python', header=0, usecols=columns)
    except:
        df = pd.DataFrame(columns=columns)
    df_abricate_results_html = df.to_html(classes='display', escape=False, table_id='abricateResultsTable', index=False)

    df_summary_html = None
    if summary_file:
        columns = ["#FILE", "NUM_FOUND"]
        try:
            df_summary = pd.read_csv(os.path.join(settings.DOWNLOAD_DIR, job_id, summary_file), sep="\t", engine='python', header=0)
        except:
            df_summary = pd.DataFrame(columns=columns)
        df_summary_html = df_summary.to_html(classes='display', escape=False, table_id='abricateSummaryTable', index=False)
    
    context = {
        'job_id': job_id,
        'abricateResultsTable': df_abricate_results_html,
        'abricateSummaryTable': df_summary_html,
    }
    return render(request, 'results_abricate.html', context)


tool = Tool(
    name='abricate',
    title='Abricate',
    category='amr',
    file_only=True,
    args=lambda request: [request.POST.get('database', 'ncbi'), request.POST.get('minimum_identity', '80'), request.POST.get('minimum_coverage', '80'), cores()],
    results=abricate_results,
    citation=[
        {
            'text': 'Seemann T. Abricate: mass screening of contigs for antimicrobial and virulence genes.',
            'url': 'https://github.com/tseemann/abricate',
        },
    ],
    example=[('abricate_example.fasta', 'abricate_example.fasta')],
    faq_title='How to use abricate (AMR)?',
    faq=['Upload your whole genome in GenBank or fasta format (.gbk, .fasta).',
         'Select the AMR database (default database is:CARD)',
         'Click Submit to start the abricate job. You will receive a job ID and can revisit later.',
         'Abricate results can be downloaded on results page.'],
)
