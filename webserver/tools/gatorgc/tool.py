import glob
import os

import pandas as pd
from django import forms
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.urls import reverse

from baclab.toolkit import Tool, citation_for, cores, genome_form, matching_file_in_dir, rename_uploaded_input, saved_name


class Form(genome_form(('.gbk', '.gb', '.gbff'), min_files=1)):
    """Genomes (GenBank) to search, plus the required (and optional) query proteins of the gene cluster to look for."""
    PROTEIN_EXTENSIONS = ('.faa', '.fasta', '.fa')

    required_proteins = forms.FileField(required=False)
    optional_proteins = forms.FileField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        required = cleaned_data.get('required_proteins')
        optional = cleaned_data.get('optional_proteins')
        if not required:
            raise ValidationError("You must upload a protein FASTA file with the required query proteins.")
        for f in (required, optional):
            if f and not f.name.lower().endswith(self.PROTEIN_EXTENSIONS):
                raise ValidationError(f"\"{f.name}\" has an unsupported extension. Allowed extensions: {', '.join(self.PROTEIN_EXTENSIONS)}.")
        return cleaned_data


def prepare_inputs(request, input_dir):
    # The script tells the query proteins from the genomes by these fixed names.
    rename_uploaded_input(input_dir, saved_name(request, 'required_proteins'), 'required_proteins')
    rename_uploaded_input(input_dir, saved_name(request, 'optional_proteins'), 'optional_proteins')


def results(request, job_id, download_dir):
    """Hits table plus, for every genomic window GATOR-GC found, its neighbourhood and conservation
    plots and links to that window's score/conservation tables and extracted GenBank file."""
    hits_file = matching_file_in_dir(download_dir, 'gatorgc_results.tsv')
    if not hits_file:
        return None
    try:
        hits_df = pd.read_csv(hits_file, sep='\t', engine='python')
    except Exception:
        hits_df = pd.DataFrame()

    def file_url(relative_path):
        if not os.path.isfile(os.path.join(download_dir, relative_path)):
            return None
        return reverse('baclab:tool_report_file', args=[job_id, relative_path])

    plot_dir = 'gator_results/gator_neighborhoods_plots'
    windows = []
    for plot in sorted(glob.glob(os.path.join(download_dir, plot_dir, '*_neighborhoods.svg'))):
        # e.g. window_1--genome_1_neighborhoods.svg -> window key "window_1--genome_1"
        key = os.path.basename(plot)[:-len('_neighborhoods.svg')]
        windows.append({
            'title': key.replace('--', ' in '),
            'neighborhood_plot': file_url(f'{plot_dir}/{key}_neighborhoods.svg'),
            'conservation_plot': file_url(f'gator_results/gator_conservation_plots/{key}.svg'),
            'conservation_table': file_url(f'gator_results/gator_conservation_tables/{key}_percentages.csv'),
            'scores_table': file_url(f'gator_results/gator_scores/{key}_GFS.csv'),
            'genbank': file_url(f'gator_results/windows_genbanks/{key}.gbff'),
        })

    context = {
        'job_id': job_id,
        'hitsTable': hits_df.to_html(classes='display', escape=False, table_id='gatorgcResultsTable', index=False),
        'windows': windows,
        'citation': citation_for(job_id),
    }
    return render(request, 'results_gatorgc.html', context)


tool = Tool(
    name='gatorgc',
    title='GATOR-GC',
    category='annot',
    form=Form,
    prepare_inputs=prepare_inputs,
    args=lambda request: [cores()],
    outputs=['gatorgc_results.tsv',
             'gator_results/gator_neighborhoods_plots', 'gator_results/gator_conservation_plots',
             'gator_results/gator_conservation_tables', 'gator_results/gator_scores', 'gator_results/windows_genbanks'],
    results=results,
    citation=[{
        'text': 'Cediel-Becerra JDD, Raab A, Chevrette MG, et al. GATOR-GC: a tool for targeted, evolution-aware detection of biosynthetic gene clusters. Nucleic Acids Res. 2025.',
        'url': 'https://doi.org/10.1093/nar/gkaf606',
    }],
    example=['gatorgc_example'],
    faq=['Upload one or more annotated genomes (.gbk, .gb, .gbff) and a protein FASTA with the required query proteins (and optionally one with optional proteins).',
         'Click Submit to find genomic windows containing the gene cluster.',
         'See the hits on the results page; plots and conservation tables are in the download.'],
)
