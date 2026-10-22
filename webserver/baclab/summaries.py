"""Key findings of a finished job in one headline plus a few numbers, shown on "my jobs" and the job page.

Built from the files in the job's download folder when the job is first looked at after it finished, then stored on the JobRecord.
A summarizer returns {"headline": str, "status": good|warn|bad|none, "tiles": [{"value", "label", "note"}]} or None
(then the generic fallback counts the result files). Tools without a summarizer just get the fallback - add one to SUMMARIZERS.
"""
import glob
import logging
import os

import pandas as pd
from django.conf import settings

logger = logging.getLogger(__name__)


def _table(download_dir, pattern, sep='\t', **kwargs):
    """The first file matching pattern as a DataFrame, or None."""
    hits = sorted(glob.glob(os.path.join(download_dir, pattern)))
    if not hits:
        return None
    try:
        return pd.read_csv(hits[0], sep=sep, engine='python', **kwargs)
    except Exception:
        return None


def _column(df, *names):
    """The first of the (case-insensitive) column names present in df."""
    lowered = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _tile(value, label, note=''):
    return {'value': str(value), 'label': label, 'note': note}


def _plural(n, word):
    if n == 1:
        return f"{n} {word}"
    return f"{n} {word[:-1] + 'ies' if word.endswith('y') else word + 's'}"


def _top(series, limit=4):
    counts = series.dropna().astype(str).value_counts()
    return ', '.join(f"{name} ({n})" for name, n in counts.head(limit).items())


# ---- per tool ----
def padloc(d):
    df = _table(d, 'padloc_results.csv', sep=',')
    if df is None:
        return None
    column = _column(df, 'system')
    systems = df.drop_duplicates(subset=[c for c in (_column(df, 'genome'), _column(df, 'system.number')) if c] or None)
    n = len(systems)
    return {'headline': f"{_plural(n, 'defence system')} found" if n else 'No defence systems found', 'status': 'good' if n else 'none',
            'tiles': [_tile(n, 'defence systems'), _tile(systems[column].nunique() if column else '-', 'distinct types', _top(systems[column]) if column else '')]}


def defensefinder(d):
    df = _table(d, 'defensefinder_results.tsv')
    if df is None:
        return None
    n = len(df)
    kind = _column(df, 'type')
    return {'headline': f"{_plural(n, 'defence system')} found" if n else 'No defence systems found', 'status': 'good' if n else 'none',
            'tiles': [_tile(n, 'defence systems'), _tile(df[kind].nunique() if kind else '-', 'distinct types', _top(df[kind]) if kind else '')]}


def amrfinderplus(d):
    df = _table(d, 'amrfinderplus_results.tsv')
    if df is None:
        return None
    gene = _column(df, 'Element symbol', 'Gene symbol')
    n = len(df)
    return {'headline': f"{_plural(n, 'resistance/stress gene')} found" if n else 'No resistance genes found', 'status': 'warn' if n else 'good',
            'tiles': [_tile(n, 'genes / mutations'), _tile(df[gene].nunique() if gene else '-', 'distinct', _top(df[gene]) if gene else '')]}


def abricate(d):
    df = _table(d, '*_results.tsv')
    if df is None:
        return None
    gene = _column(df, 'GENE')
    n = len(df)
    return {'headline': f"{_plural(n, 'hit')} in the screened database" if n else 'No hits', 'status': 'warn' if n else 'good',
            'tiles': [_tile(n, 'hits'), _tile(df[gene].nunique() if gene else '-', 'distinct genes', _top(df[gene]) if gene else '')]}


def mlst(d):
    path = os.path.join(d, 'mlst_results.tsv')
    if not os.path.exists(path):
        return None
    rows = [line.rstrip('\n').split('\t') for line in open(path) if line.strip()]
    sts = [(r[0].rsplit('/', 1)[-1], r[1] if len(r) > 1 else '-', r[2] if len(r) > 2 else '-') for r in rows]
    if not sts:
        return None
    first = sts[0]
    headline = f"{first[1]} ST{first[2]}" if len(sts) == 1 else f"{_plural(len(sts), 'genome')} typed"
    return {'headline': headline, 'status': 'good' if all(st[2] not in ('-', '') for st in sts) else 'warn',
            'tiles': [_tile(len(sts), 'genomes'), _tile(len({st[2] for st in sts}), 'distinct sequence types', ', '.join(f"{n}: {s}/ST{t}" for n, s, t in sts[:4]))]}


def checkm2(d):
    df = _table(d, 'checkm2_results.tsv')
    if df is None:
        return None
    comp, cont = _column(df, 'Completeness'), _column(df, 'Contamination')
    if not comp or not cont:
        return None
    best_comp, worst_cont = df[comp].astype(float).min(), df[cont].astype(float).max()
    ok = best_comp >= 90 and worst_cont <= 5
    return {'headline': f"Completeness {best_comp:.1f}%, contamination {worst_cont:.1f}%" + (' (worst of the genomes)' if len(df) > 1 else ''),
            'status': 'good' if ok else 'warn',
            'tiles': [_tile(f"{best_comp:.1f}%", 'completeness' + (' (lowest)' if len(df) > 1 else ''), 'high-quality: >= 90%'),
                      _tile(f"{worst_cont:.1f}%", 'contamination' + (' (highest)' if len(df) > 1 else ''), 'high-quality: <= 5%')]}


def kraken2(d):
    df = _table(d, 'kraken2_results.tsv', header=None, names=['Percent', 'Reads', 'Direct', 'Rank', 'TaxID', 'Name'])
    if df is None or df.empty:
        return None
    species = df[df['Rank'] == 'S'].sort_values('Percent', ascending=False)
    if species.empty:
        return None
    top = species.iloc[0]
    return {'headline': f"{str(top['Name']).strip()} ({top['Percent']:.1f}% of the sequence)", 'status': 'good' if top['Percent'] >= 80 else 'warn',
            'tiles': [_tile(f"{top['Percent']:.1f}%", str(top['Name']).strip(), 'top species'), _tile(len(species), 'species detected')]}


def _pairwise(d, filename, column, label):
    df = _table(d, filename)
    if df is None:
        return None
    col = _column(df, column)
    q, r = _column(df, 'Query', 'query'), _column(df, 'Reference', 'target')
    if not col:
        return None
    if q and r:
        df = df[df[q].astype(str) != df[r].astype(str)]
    if df.empty:
        return None
    values = df[col].astype(float)
    return {'headline': f"{label} {values.min():.1f}-{values.max():.1f}% between the genomes", 'status': 'none',
            'tiles': [_tile(f"{values.min():.1f}%", f'lowest {label}'), _tile(f"{values.max():.1f}%", f'highest {label}'),
                      _tile(len(df), 'comparisons')]}


def ani(d):
    return _pairwise(d, 'ani_results.tsv', 'ANI', 'ANI')


def fastaai(d):
    return _pairwise(d, 'fastaai_results.tsv', 'AAI_estimate', 'AAI')


def gecco(d):
    df = _table(d, 'gecco_results.tsv')
    if df is None:
        return None
    kind = _column(df, 'type')
    n = len(df)
    return {'headline': f"{_plural(n, 'biosynthetic gene cluster')} predicted" if n else 'No gene clusters predicted', 'status': 'good' if n else 'none',
            'tiles': [_tile(n, 'clusters'), _tile(df[kind].nunique() if kind else '-', 'cluster types', _top(df[kind]) if kind else '')]}


def mobsuite(d):
    df = _table(d, 'mobsuite_results.tsv')
    if df is None:
        return None
    n = len(df)
    return {'headline': f"{_plural(n, 'plasmid')} reconstructed" if n else 'No plasmids found', 'status': 'none', 'tiles': [_tile(n, 'plasmids')]}


def bigscape(d):
    df = _table(d, 'bigscape_results.tsv')
    if df is None:
        return None
    fam = _column(df, 'Family')
    return {'headline': f"{_plural(df[fam].nunique() if fam else 0, 'gene cluster family')} from {_plural(len(df), 'cluster')}", 'status': 'none',
            'tiles': [_tile(len(df), 'clusters'), _tile(df[fam].nunique() if fam else '-', 'families')]}


def bigslice(d):
    df = _table(d, 'bigslice_results.tsv')
    if df is None:
        return None
    gcf = _column(df, 'GCF')
    families = df[gcf].nunique() if gcf else 0
    return {'headline': f"{_plural(families, 'gene cluster family')} from {_plural(len(df), 'cluster')}", 'status': 'none',
            'tiles': [_tile(len(df), 'clusters'), _tile(families, 'families')]}


def gtotree(d):
    df = _table(d, 'gtotree_genomes_summary.tsv')
    if df is None:
        return None
    comp = _column(df, 'perc_comp')
    tile = [_tile(len(df), 'genomes')]
    if comp:
        tile.append(_tile(f"{pd.to_numeric(df[comp], errors='coerce').median():.1f}%", 'median marker completeness'))
    return {'headline': f"Phylogenomic tree of {_plural(len(df), 'genome')}", 'status': 'good', 'tiles': tile}


def basalt(d):
    df = _table(d, 'basalt_quality_report.tsv')
    if df is None:
        return None
    return {'headline': f"{_plural(len(df), 'bin')} (MAG) recovered", 'status': 'good' if len(df) else 'none', 'tiles': [_tile(len(df), 'bins')]}


def screen(d):
    df = _table(d, 'genome_profile.tsv')
    if df is None:
        return None
    return {'headline': f"{_plural(len(df), 'genome')} profiled", 'status': 'none',
            'tiles': [_tile(len(df), 'genomes'), _tile(len([c for c in df.columns if c != 'genome']), 'properties per genome')]}


SUMMARIZERS = {
    'padloc': padloc, 'defensefinder': defensefinder, 'amrfinderplus': amrfinderplus, 'abricate': abricate, 'mlst': mlst, 'checkm2': checkm2,
    'kraken2': kraken2, 'ani': ani, 'fastaai': fastaai, 'gecco': gecco, 'mobsuite': mobsuite, 'bigscape': bigscape, 'bigslice': bigslice,
    'gtotree': gtotree, 'basalt': basalt, 'screen': screen,
}


def _fallback(download_dir):
    files = [f for _, _, names in os.walk(download_dir) for f in names if f not in ('CITATION.txt', 'run_parameters.txt')]
    outputs = [f for f in files if not f.startswith('input')]
    return {'headline': f"{_plural(len(outputs), 'result file')} ready to download" if outputs else 'No result files', 'status': 'none' if outputs else 'bad',
            'tiles': [_tile(len(outputs), 'result files')]}


def summarize(job_type, download_dir):
    """The summary dict of a finished job ({} when there is nothing to show)."""
    if not os.path.isdir(download_dir):
        return {}
    function = SUMMARIZERS.get(job_type)
    try:
        result = function(download_dir) if function else None
    except Exception:
        logger.exception('Summary of %s failed', job_type)
        result = None
    return result or _fallback(download_dir)


def ensure_summary(job):
    """Compute and store the summary of a finished job the first time it is needed."""
    if job.summary is not None or job.status != 'finished':
        return job.summary
    job.summary = summarize(job.job_type, os.path.join(settings.DOWNLOAD_DIR, job.job_id))
    job.save(update_fields=['summary'])
    return job.summary


def ensure_summaries(jobs):
    for job in jobs:
        ensure_summary(job)
