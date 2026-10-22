import json
import os

import pandas as pd
from django.shortcuts import render
from django.urls import reverse

from baclab.toolkit import Tool, citation_for, cores, database, genome_form, matching_file_in_dir

REPORT_COLUMNS = {
    'OG is Single Copy?': 'Single copy',
    'OG Median Length (bp)': 'Median length (bp)',
    'OG Consensus Order': 'Order',
    'OG Consensus Direction': 'Strand',
    'Entropy': 'Entropy',
    'PGAP Annotation (E-value)': 'PGAP annotation (E-value)',
    'Pfam Domains': 'Pfam domains',
}


def gene_class(present_in, cluster_count):
    """PanBGC's gene classes: core = in every cluster, singleton = in exactly one, accessory = the rest."""
    if present_in >= cluster_count:
        return 'Core'
    if present_in <= 1:
        return 'Singleton'
    return 'Accessory'


def results(request, job_id, download_dir):
    """Summary (clusters, gene classes, Heaps' law openness), the presence/absence heatmap and the ortholog-group table."""
    report_file = matching_file_in_dir(download_dir, 'panbgc_report.tsv')
    if not report_file:
        return None
    try:
        df = pd.read_csv(report_file, sep='\t', engine='python')
    except Exception:
        return None

    heaps = {}
    heaps_file = matching_file_in_dir(download_dir, 'panbgc_heaps_law.json')
    if heaps_file:
        try:
            with open(heaps_file) as handle:
                heaps = json.load(handle)
        except Exception:
            heaps = {}

    proportion_column = 'Proportion of Total Gene Clusters with OG'
    proportions = pd.to_numeric(df[proportion_column], errors='coerce').fillna(0.0) if proportion_column in df else pd.Series([0.0] * len(df), index=df.index)
    cluster_count = heaps.get('bgcCount')
    if not cluster_count and (proportions > 0).any():
        cluster_count = int(round(1 / proportions[proportions > 0].min()))
    present_in = [int(round(p * cluster_count)) for p in proportions] if cluster_count else []

    table = pd.DataFrame(index=df.index)
    table['Ortholog group'] = df['Ortholog Group (OG) ID'] if 'Ortholog Group (OG) ID' in df else ''
    if cluster_count:
        table['Class'] = [gene_class(n, cluster_count) for n in present_in]
        table['Present in clusters'] = [f"{n} / {cluster_count}" for n in present_in]
    for source, label in REPORT_COLUMNS.items():
        if source in df:
            table[label] = df[source]

    class_counts = table['Class'].value_counts().to_dict() if 'Class' in table else {}
    gamma = heaps.get('gamma')
    heatmap = None
    if os.path.isfile(os.path.join(download_dir, 'panbgc_heatmap.pdf')):
        heatmap = reverse('baclab:tool_report_file', args=[job_id, 'panbgc_heatmap.pdf'])

    context = {
        'job_id': job_id,
        'summary': {
            'clusters': cluster_count or None,
            'groups': len(df),
            'core': class_counts.get('Core', 0),
            'accessory': class_counts.get('Accessory', 0),
            'singleton': class_counts.get('Singleton', 0),
            'gamma': f"{gamma:.2f}" if isinstance(gamma, (int, float)) else None,
        },
        'heatmapUrl': heatmap,
        'resultsTable': table.to_html(classes='display', escape=False, table_id='panbgcResultsTable', index=False),
        'citation': citation_for(job_id),
    }
    return render(request, 'results_panbgc.html', context)


tool = Tool(
    name='panbgc',
    title='PanBGC',
    category='annot',
    form=genome_form(('.gbk',), min_files=3, max_files=100),   # the gene clusters of ONE gene cluster family
    args=lambda request: [cores(), database('ZolDB')],
    outputs=['panbgc_visualisation.json', 'panbgc_report.tsv', 'panbgc_heaps_law.json', 'panbgc_heatmap.pdf'],
    results=results,
    citation=[
        {'text': 'PanBGC-DB: pangenome-inspired analysis of biosynthetic gene cluster families (Ziemert lab, University of Tuebingen) - check the repository for its current citation.',
         'url': 'https://github.com/ZiemertLab/PanBGC-DB'},
        {'text': 'Salamzade R, Kalan LR, et al. zol & fai: large-scale targeted detection and evolutionary investigation of gene clusters. Nucleic Acids Res. 2025.',
         'url': 'https://github.com/Kalan-Lab/zol'},
    ],
    example=['panbgc_example'],
    faq=['Upload three or more GenBank files (.gbk) of gene clusters from the same gene cluster family.',
         'Click Submit to classify their genes into core, accessory and unique ortholog groups.',
         'See the ortholog groups on the results page and upload the visualisation file to PanBGC-DB for the interactive view.'],
)
