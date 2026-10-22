import pandas as pd
from django import forms
from django.shortcuts import render

from baclab.toolkit import Tool, choice, citation_for, cores, database, genome_form, matching_file_in_dir

# Pre-packaged single-copy-gene sets shipped with GToTree (see `gtt-hmms`).
HMM_SETS = (
    'Bacteria', 'Archaea', 'Bacteria_and_Archaea', 'Universal-Hug-et-al', 'Actinobacteria',
    'Alphaproteobacteria', 'Bacteroidetes', 'Betaproteobacteria', 'Chlamydiae', 'Cyanobacteria',
    'Epsilonproteobacteria', 'Firmicutes', 'Gammaproteobacteria', 'Proteobacteria', 'Tenericutes',
)


class Form(genome_form(('.fasta', '.fa', '.fna'), min_files=3)):
    """GToTree builds a tree, which is only meaningful for 3+ genomes."""
    hmm_set = forms.ChoiceField(choices=[(s, s) for s in HMM_SETS], required=False)


def results(request, job_id, download_dir):
    """Tree, per-genome quality table and a genome x marker-gene hit heatmap."""
    tree_file = matching_file_in_dir(download_dir, 'gtotree_tree.nwk')
    if not tree_file:
        return None
    with open(tree_file) as handle:
        tree_string = handle.read().replace('\n', '')

    summary_html, summary_df = '', None
    summary_file = matching_file_in_dir(download_dir, 'gtotree_genomes_summary.tsv')
    if summary_file:
        try:
            summary_df = pd.read_csv(summary_file, sep='\t', engine='python')
            shown = summary_df.rename(columns={
                'assembly_id': 'Genome', 'num_SCG_hits': 'Marker gene hits', 'uniq_SCG_hits': 'Unique marker genes',
                'perc_comp': 'Completeness (%)', 'perc_redund': 'Redundancy (%)',
                'num_SCG_hits_after_len_filt': 'Hits after length filter', 'in_final_tree': 'In tree',
            }).drop(columns=['taxid'], errors='ignore')
            summary_html = shown.to_html(classes='display', escape=False, table_id='gtotreeSummaryTable', index=False)
        except Exception:
            summary_df = None

    # Genome x marker-gene heatmap: 0 = missing, 1 = single copy, 2+ = duplicated.
    genes, heatmap_rows = [], []
    hits_file = matching_file_in_dir(download_dir, 'gtotree_scg_hit_counts.tsv')
    if hits_file:
        try:
            hits_df = pd.read_csv(hits_file, sep='\t', engine='python', index_col=0)
            genes = [str(gene) for gene in hits_df.columns]
            for genome, row in hits_df.iterrows():
                counts = [int(value) if pd.notna(value) else 0 for value in row.tolist()]
                heatmap_rows.append({
                    'genome': str(genome),
                    'cells': [{'gene': gene, 'count': count, 'cls': 'missing' if count == 0 else ('single' if count == 1 else 'multi')} for gene, count in zip(genes, counts)],
                    'missing': sum(1 for count in counts if count == 0),
                    'multi': sum(1 for count in counts if count > 1),
                })
        except Exception:
            genes, heatmap_rows = [], []

    stats = {'genomes': len(summary_df) if summary_df is not None else len(heatmap_rows), 'markers': len(genes)}
    if summary_df is not None:
        if 'in_final_tree' in summary_df:
            stats['in_tree'] = int((summary_df['in_final_tree'].astype(str).str.lower() == 'yes').sum())
        if 'perc_comp' in summary_df:
            stats['median_completeness'] = f"{pd.to_numeric(summary_df['perc_comp'], errors='coerce').median():.1f}"

    context = {
        'job_id': job_id,
        'phylogeneticTreeData': tree_string,
        'summaryTable': summary_html,
        'genes': genes,
        'heatmapRows': heatmap_rows,
        'stats': stats,
        'citation': citation_for(job_id),
    }
    return render(request, 'results_gtotree.html', context)


tool = Tool(
    name='gtotree',
    title='GToTree',
    category='compgen',
    form=Form,
    args=lambda request: [cores(), choice(request.POST.get('hmm_set'), HMM_SETS, 'Bacteria'), database('GtotreeDB')],
    outputs=['gtotree_tree.nwk', 'gtotree_genomes_summary.tsv', 'gtotree_scg_hit_counts.tsv', 'gtotree_aligned_scgs.faa'],
    results=results,
    citation=[{
        'text': 'Lee MD. GToTree: a user-friendly workflow for phylogenomics. Bioinformatics. 2019;35(20):4162-4164.',
        'url': 'https://doi.org/10.1093/bioinformatics/btz188',
    }],
    example=[('ani_example/strain_A.fasta', 'genome_1.fasta'), ('ani_example/strain_B_ecoli_K12.fasta', 'genome_2.fasta'),
             ('klebsiella_pneumoniae_HS11286.fna', 'genome_3.fasta')],
    faq=['Upload three or more genome assemblies in FASTA format and choose a single-copy gene set.',
         'Click Submit to build a phylogenomic tree from the shared marker genes.',
         'View the tree on the results page; the alignment and marker-gene tables are in the download.'],
)
