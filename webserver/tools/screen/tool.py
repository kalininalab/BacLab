"""Genome screen: one upload, several quick analyses, one table with a row per genome.

Runs the scripts of other tools one after the other on the same genomes (each in its own conda environment) and merges their key
results into genome_profile.tsv. A step that fails or whose database is missing is reported in step_status.tsv; the others still run.
"""
import csv
import os

import pandas as pd
from django.conf import settings

from baclab import db_catalog
from baclab.toolkit import Tool, cores, database, genome_form, tabbed_results
from baclab.toolkit.files import run_command

# step -> (script relative to the tools folder, arguments after <input> <output> <cores>, catalog database keys it needs, label)
STEPS = {
    'mlst': ('mlst/mlst_script.sh', lambda: [], [], 'MLST typing'),
    'amr': ('amrfinderplus/amrfinderplus_script.sh', lambda: ['none'], ['amrfinderplus'], 'AMRFinderPlus resistance genes'),
    'checkm2': ('checkm2/checkm2_script.sh', lambda: [database('Checkm2DB')], ['checkm2'], 'CheckM2 completeness / contamination'),
    'defence': ('defensefinder/defensefinder_script.sh', lambda: [database('DefenseFinderDB')], ['defensefinder'], 'DefenseFinder defence systems'),
}
STEP_ORDER = ['mlst', 'amr', 'checkm2', 'defence']
FASTA = ('.fasta', '.fa', '.fna')


def genome_names(input_dir):
    return sorted(f for f in os.listdir(input_dir) if f.lower().endswith(FASTA))


def stem(name):
    return os.path.splitext(os.path.basename(name))[0]


def fasta_stats(path):
    """(size bp, contigs, N50, GC %) of a FASTA file."""
    lengths, gc, current = [], 0, 0
    with open(path) as handle:
        for line in handle:
            if line.startswith('>'):
                if current:
                    lengths.append(current)
                current = 0
            else:
                line = line.strip().upper()
                current += len(line)
                gc += line.count('G') + line.count('C')
    if current:
        lengths.append(current)
    total = sum(lengths)
    running, n50 = 0, 0
    for length in sorted(lengths, reverse=True):
        running += length
        if running >= total / 2:
            n50 = length
            break
    return total, len(lengths), n50, round(100.0 * gc / total, 2) if total else 0.0


def read(path, **kwargs):
    try:
        return pd.read_csv(path, sep='\t', engine='python', **kwargs) if os.path.isfile(path) else None
    except Exception:
        return None


def chosen_steps(output_dir):
    """The analyses the user ticked, from run_parameters.txt (the web layer writes the form values there); nothing ticked = the quick ones."""
    ticked = set()
    try:
        with open(os.path.join(output_dir, 'run_parameters.txt')) as handle:
            ticked = {line.split(':', 1)[0] for line in handle if line.strip()}
    except OSError:
        pass
    chosen = [s for s in STEP_ORDER if f'step_{s}' in ticked]
    return chosen or ['mlst', 'amr']


def run(ctx):
    output_dir = ctx['output_dir']
    input_dir = os.path.join(output_dir, 'input')
    steps = chosen_steps(output_dir)
    names = genome_names(input_dir)
    if not names:
        raise RuntimeError('No genome FASTA files found in the input.')

    stats = {stem(n): fasta_stats(os.path.join(input_dir, n)) for n in names}
    with open(os.path.join(output_dir, 'genome_stats.tsv'), 'w', newline='') as handle:
        writer = csv.writer(handle, delimiter='\t')
        writer.writerow(['genome', 'size_bp', 'contigs', 'N50', 'GC_percent'])
        for genome, values in stats.items():
            writer.writerow([genome, *values])

    status = []
    for step in steps:
        script, extra_args, database_keys, label = STEPS[step]
        missing = [e['title'] for key in database_keys for e in [db_catalog.BY_KEY[key]] if not db_catalog.is_installed(e, settings.DATABASES_DIR)]
        if missing:
            status.append((step, label, 'skipped', f"database not installed: {'; '.join(missing)}"))
            continue
        step_dir = os.path.join(output_dir, step)
        os.makedirs(step_dir, exist_ok=True)
        try:
            run_command(['bash', os.path.join(settings.TOOLS_DIR, script), input_dir, step_dir, str(settings.CORES_PER_JOB), *extra_args()], step_dir)
            status.append((step, label, 'done', ''))
        except Exception as error:
            lines = str(error).strip().splitlines()
            status.append((step, label, 'failed', (lines[-1] if lines else type(error).__name__)[:300]))
    with open(os.path.join(output_dir, 'step_status.tsv'), 'w', newline='') as handle:
        writer = csv.writer(handle, delimiter='\t')
        writer.writerow(['step', 'analysis', 'status', 'note'])
        writer.writerows(status)
    if not any(row[2] == 'done' for row in status):
        raise RuntimeError('None of the analyses could run: ' + '; '.join(f'{r[0]} {r[2]} ({r[3]})' for r in status))

    profile = pd.DataFrame([{'genome': g, 'size_bp': v[0], 'contigs': v[1], 'N50': v[2], 'GC_percent': v[3]} for g, v in stats.items()])
    done = {row[0] for row in status if row[2] == 'done'}
    if 'mlst' in done:
        mlst = read(os.path.join(output_dir, 'mlst', 'mlst_results.tsv'), header=None)
        if mlst is not None and mlst.shape[1] >= 3:
            found = {stem(str(r[0])): (r[1], r[2]) for r in mlst.itertuples(index=False)}
            profile['MLST_scheme'] = [found.get(g, ('', ''))[0] for g in profile['genome']]
            profile['MLST_ST'] = [found.get(g, ('', ''))[1] for g in profile['genome']]
    if 'amr' in done:
        counts = {}
        for g in profile['genome']:
            table = read(os.path.join(output_dir, 'amr', f'{g}_amrfinder.tsv'))
            counts[g] = 0 if table is None else len(table)
        profile['AMR_genes'] = [counts[g] for g in profile['genome']]
    if 'checkm2' in done:
        table = read(os.path.join(output_dir, 'checkm2', 'checkm2_results.tsv'))
        if table is not None and 'Name' in table:
            by_name = table.set_index(table['Name'].astype(str).map(stem))
            for column, label in (('Completeness', 'completeness_percent'), ('Contamination', 'contamination_percent')):
                if column in by_name:
                    profile[label] = [by_name[column].get(g, '') for g in profile['genome']]
    if 'defence' in done:
        table = read(os.path.join(output_dir, 'defence', 'defensefinder_results.tsv'))
        counts = table['genome'].astype(str).value_counts().to_dict() if table is not None and 'genome' in table else {}
        profile['defence_systems'] = [counts.get(g, 0) for g in profile['genome']]
    profile.to_csv(os.path.join(output_dir, 'genome_profile.tsv'), sep='\t', index=False)


def args(request):
    return [cores()]


tool = Tool(
    name='screen',
    title='Genome screen (pipeline)',
    category='qc',
    description='One upload, several quick analyses (typing, resistance genes, genome quality, defence systems) and one table with a row per genome.',
    form=genome_form(FASTA, min_files=1, max_files=settings.MAX_GENOMES_PER_JOB),
    args=args,
    run=run,
    outputs=['genome_profile.tsv', 'genome_stats.tsv', 'step_status.tsv', 'mlst', 'amr', 'checkm2', 'defence'],
    results=tabbed_results('Genome screen', [
        ('genome_profile.tsv', 'Genome profile', 'One row per genome: assembly statistics and the key result of every analysis that ran.'),
        ('step_status.tsv', 'Analyses', 'Which analyses ran, were skipped (database missing) or failed.'),
        ('mlst/mlst_results.tsv', 'MLST', 'Sequence types.'),
        ('amr/amrfinderplus_results.tsv', 'Resistance genes', 'AMRFinderPlus hits of all genomes.'),
        ('checkm2/checkm2_results.tsv', 'CheckM2', 'Completeness and contamination.'),
        ('defence/defensefinder_results.tsv', 'Defence systems', 'DefenseFinder systems of all genomes.'),
    ]),
    citation=[
        {'text': 'Seemann T. mlst: scan contig files against PubMLST typing schemes.', 'url': 'https://github.com/tseemann/mlst'},
        {'text': 'Feldgarden M, et al. AMRFinderPlus and the Reference Gene Catalog. Sci Rep. 2021;11:12728.', 'url': 'https://doi.org/10.1038/s41598-021-91456-0'},
        {'text': 'Chklovski A, et al. CheckM2: a rapid, scalable and accurate tool for assessing microbial genome quality using machine learning. Nat Methods. 2023;20:1203-1212.',
         'url': 'https://doi.org/10.1038/s41592-023-01940-w'},
        {'text': 'Tesson F, et al. Systematic and quantitative view of the antiviral arsenal of prokaryotes. Nat Commun. 2022;13:2561.', 'url': 'https://doi.org/10.1038/s41467-022-30269-9'},
    ],
    example=[('ani_example/strain_A.fasta', 'E_coli_draft_MDR.fasta'), ('ani_example/strain_B_ecoli_K12.fasta', 'E_coli_K12.fasta'),
             ('klebsiella_pneumoniae_NTUH_K2044.fna', 'K_pneumoniae_NTUH-K2044.fasta')],
    example_post={'step_mlst': 'on', 'step_amr': 'on'},
    faq_title='How to use the Genome screen?',
    faq=['Upload one or more genome assemblies (FASTA) and tick the analyses you want: typing (MLST), resistance genes, genome quality (CheckM2), defence systems.',
         'Click Submit. The analyses run one after the other on the same genomes; an analysis whose database is missing is skipped.',
         'The results page shows one table with a row per genome, plus the full table of each analysis; everything is in the download.'],
)
