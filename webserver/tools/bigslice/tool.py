import pandas as pd
from django import forms

from baclab.toolkit import Tool, choice, cores, database, genome_form, matching_file_in_dir, render_result_tabs

THRESHOLDS = ('0.2', '0.3', '0.4', '0.5', '0.6')


class Form(genome_form(('.gbk',), min_files=2, max_files=200)):
    """antiSMASH region GenBank files to cluster into gene cluster families."""
    threshold = forms.ChoiceField(choices=[(c, c) for c in THRESHOLDS], required=False)


def results(request, job_id, download_dir):
    """BGC assignments, a per-family (GCF) summary and the run information, as selectable tabs."""
    table_file = matching_file_in_dir(download_dir, 'bigslice_results.tsv')
    if not table_file:
        return None
    try:
        assignments = pd.read_csv(table_file, sep='\t', engine='python')
    except Exception:
        return None

    # Per-family summary, computed from the assignments table.
    summary = pd.DataFrame()
    if 'GCF' in assignments:
        grouped = assignments.assign(GCF=assignments['GCF'].fillna(-1).astype(int)).groupby('GCF', sort=False)

        def classes(series):
            names = sorted({name for cell in series.dropna() for name in str(cell).split(',') if name})
            return ', '.join(names) if names else '-'

        summary = pd.DataFrame({
            'BGCs': grouped.size(),
            'Genomes': grouped['genome'].nunique() if 'genome' in assignments else None,
            'Product classes': grouped['product_classes'].agg(classes) if 'product_classes' in assignments else None,
            'Mean length (nt)': grouped['len_nt'].mean().round(0).astype(int) if 'len_nt' in assignments else None,
            'Mean distance to family': grouped['distance_to_GCF'].mean().round(3) if 'distance_to_GCF' in assignments else None,
            'Members': grouped['bgc'].agg('; '.join) if 'bgc' in assignments else None,
        }).dropna(axis=1, how='all').reset_index()
        summary = summary.rename(columns={'GCF': 'Family (GCF)'}).sort_values(['BGCs', 'Family (GCF)'], ascending=[False, True])
        summary['Family (GCF)'] = summary['Family (GCF)'].astype(str).replace('-1', 'unassigned')

    # Run information: a readable version of BiG-SLiCE's own run table plus a few counts.
    info_rows = []
    run_file = matching_file_in_dir(download_dir, 'bigslice_tsv/run_metadata.tsv')
    if run_file:
        try:
            run = pd.read_csv(run_file, sep='\t', engine='python').iloc[0]
            info_rows += [('Run date', str(run.get('time_stamp', ''))[:19]), ('Clustering threshold', run.get('threshold', ''))]
        except Exception:
            pass
    family_sizes = summary['BGCs'] if 'BGCs' in summary else pd.Series(dtype=int)
    info_rows += [
        ('BGCs clustered', len(assignments)),
        ('Genomes', assignments['genome'].nunique() if 'genome' in assignments else ''),
        ('Gene cluster families (GCFs)', len(summary)),
        ('Singleton families (1 BGC)', int((family_sizes == 1).sum())),
        ('Largest family (BGCs)', int(family_sizes.max()) if len(family_sizes) else ''),
    ]
    run_info = pd.DataFrame(info_rows, columns=['Setting', 'Value'])

    return render_result_tabs(request, job_id, 'BiG-SLiCE Gene Cluster Families', [
        ('BGC assignments', 'Each BGC with the gene cluster family (GCF) it was assigned to and its distance to that family (0 = at the family centre; larger = a looser fit).', assignments),
        ('Families', 'The gene cluster families found: how many BGCs and genomes each contains, their product classes and members.', summary),
        ('Run information', 'Clustering threshold and totals for this run.', run_info),
    ])


tool = Tool(
    name='bigslice',
    title='BiG-SLiCE',
    category='annot',
    form=Form,
    args=lambda request: [cores(), database('BigsliceDB'), choice(request.POST.get('threshold'), THRESHOLDS, '0.4')],
    outputs=['bigslice_results.tsv', 'bigslice_tsv'],
    results=results,
    citation=[{
        'text': 'Kautsar SA, van der Hooft JJJ, de Ridder D, Medema MH. BiG-SLiCE: A highly scalable tool maps the diversity of 1.2 million biosynthetic gene clusters. GigaScience. 2021;10(1):giaa154.',
        'url': 'https://doi.org/10.1093/gigascience/giaa154',
    }],
    example=[('bacillus_antismash_regions', 'bacillus_antismash_regions')],   # 27 antiSMASH regions of B. subtilis 168 and B. velezensis FZB42
    faq=['Upload two or more antiSMASH region GenBank files (.gbk) and pick a clustering threshold.',
         'Click Submit to cluster the clusters into gene cluster families.',
         'Download the family assignment table from the results page.'],
)
