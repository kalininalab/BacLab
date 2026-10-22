import glob
import os

import pandas as pd
from django import forms
from django.shortcuts import render
from django.urls import reverse

from baclab.toolkit import Tool, choice, citation_for, cores, database, genome_form, matching_file_in_dir, unpack_archive

GCF_CUTOFFS = ('0.2', '0.3', '0.4', '0.5', '0.6', '0.7')
DEFAULT_GCF_CUTOFF = '0.5'   # the page's preselected value


class Form(genome_form(('.gbk',), min_files=2, max_files=1000, allow_zip=True)):
    """antiSMASH region GenBank files (or a zip of them) to group into gene cluster families."""
    gcf_cutoff = forms.ChoiceField(choices=[(c, c) for c in GCF_CUTOFFS], required=False)


def patch_viewer(run_dir):
    """Make the BiG-SCAPE viewer in run_dir load its database from its own folder.

    The viewer only does that by itself on localhost, from a fixed /data_sqlite.db path (anywhere
    else it asks for the file by hand, and on localhost it fails with "file is not a database" when
    the server has no such file). The job script patches new jobs the same way; doing it here too
    covers results from before that change and cached example results. Safe to repeat."""
    index_path = os.path.join(run_dir, 'index.html')
    db_files = sorted(glob.glob(os.path.join(run_dir, '*.db')))
    if not os.path.isfile(index_path) or not db_files:
        return
    db_name = os.path.basename(db_files[0])
    try:
        with open(index_path, encoding='utf-8') as handle:
            html = handle.read()
        patched = html
        patched = patched.replace('if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {', 'if (true) {')
        patched = patched.replace("xhr.open('GET', '/data_sqlite.db', true);", f"xhr.open('GET', './{db_name}', true);")
        patched = patched.replace('$("#status").html("Loaded: data_sqlite.db")', f'$("#status").html("Loaded: {db_name}")')
        if patched != html:
            with open(index_path, 'w', encoding='utf-8') as handle:
                handle.write(patched)
    except OSError:
        pass


def results(request, job_id, download_dir):
    """The interactive BiG-SCAPE viewer (embedded) and the merged families table, as selectable tabs."""
    table_file = matching_file_in_dir(download_dir, 'bigscape_results.tsv')
    if not table_file:
        return None
    try:
        df = pd.read_csv(table_file, sep='\t', engine='python')
    except Exception:
        df = pd.DataFrame()
    viewer_url = None
    patch_viewer(os.path.join(download_dir, 'bigscape_run'))
    if os.path.isfile(os.path.join(download_dir, 'bigscape_run', 'index.html')):
        viewer_url = reverse('baclab:tool_report_file', args=[job_id, 'bigscape_run/index.html'])
    return render(request, 'results_bigscape.html', {
        'job_id': job_id,
        'viewerUrl': viewer_url,
        'familyCount': df['Family'].nunique() if 'Family' in df else 0,
        'recordCount': len(df),
        'resultsTable': df.to_html(classes='display', escape=False, table_id='bigscapeResultsTable', index=False) if len(df.columns) else '',
        'citation': citation_for(job_id),
    })


tool = Tool(
    name='bigscape',
    title='BiG-SCAPE',
    category='annot',
    form=Form,
    prepare_inputs=unpack_archive(Form),
    args=lambda request: [cores(), database('PfamDB'), choice(request.POST.get('gcf_cutoff'), GCF_CUTOFFS, DEFAULT_GCF_CUTOFF), 'yes' if 'mibig' in request.POST else 'no', database('BigscapeDB')],
    outputs=['bigscape_results.tsv', 'bigscape_run'],
    results=results,
    citation=[{
        'text': 'Navarro-Munoz JC, Selem-Mojica N, Mullowney MW, et al. A computational framework to explore large-scale biosynthetic diversity. Nat Chem Biol. 2020;16:60-68.',
        'url': 'https://doi.org/10.1038/s41589-019-0400-9',
    }],
    example=[('bacillus_antismash_regions', 'bacillus_antismash_regions')],   # 27 antiSMASH regions of B. subtilis 168 and B. velezensis FZB42
    faq=['Upload two or more antiSMASH region GenBank files (.gbk), up to 1000, or one zip archive of them, and pick a GCF distance cutoff. Optionally tick the box to include the MIBiG 4.0 reference clusters.',
         'Click Submit to group the clusters into gene cluster families.',
         'Explore the families in the interactive BiG-SCAPE viewer on the results page, or in the families table (the download also contains the viewer to open offline).'],
)
