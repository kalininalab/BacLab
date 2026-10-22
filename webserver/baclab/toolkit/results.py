"""Building blocks for the results pages. A tool's `results=` is a function (request, job_id, download_dir)
returning a response, or None when there is nothing to show; the factories at the bottom cover the usual cases."""
import os

import pandas as pd
from django.shortcuts import render
from django.urls import reverse

from . import registry
from .files import matching_file_in_dir


def citation_for(job_id):
    """The citations of the tool a job id belongs to (job ids are "<tool name>-<uuid>")."""
    tool = registry.get(job_id.split('-')[0])
    return tool.citation if tool else []


def generic_table_results(request, job_id, download_dir, tsv_glob, table_title, sep="\t", header=0, columns=None, table_id="genericResultsTable", usecols=None, note=None):
    """Reusable results renderer for tools whose primary output is a single delimited table file."""
    result_file = matching_file_in_dir(download_dir, tsv_glob)
    if not result_file:
        return None
    try:
        df = pd.read_csv(result_file, sep=sep, engine='python', header=header, usecols=usecols)
        if columns:
            df.columns = list(columns[:len(df.columns)])
    except Exception:
        df = pd.DataFrame()
    table_html = df.to_html(classes='display', escape=False, table_id=table_id, index=False, na_rep='')   # empty cells, not "NaN"
    context = {
        'job_id': job_id,
        'resultsTable': table_html,
        'tableTitle': table_title,
        'tableId': table_id,
        'note': note,
        'citation': citation_for(job_id),
    }
    return render(request, 'results_generic_table.html', context)

def generic_html_results(request, job_id, download_dir, html_glob, report_title):
    """Reusable results renderer for tools whose primary output is a self-contained HTML report
    (e.g. QUAST/fastp/MultiQC's own report.html) - embeds it in an iframe served by
    serve_tool_report_file. Returns None (so callers can fall back to a table view) if no matching
    file is found."""
    result_file = matching_file_in_dir(download_dir, html_glob)
    if not result_file:
        return None
    rel_path = os.path.relpath(result_file, download_dir)
    context = {
        'job_id': job_id,
        'reportTitle': report_title,
        'reportUrl': reverse('baclab:tool_report_file', args=[job_id, rel_path]),
        'citation': citation_for(job_id),
    }
    return render(request, 'results_generic_html.html', context)

def render_result_tabs(request, job_id, page_title, tables):
    """Render the shared tabbed-tables page. tables: (tab title, description, DataFrame) tuples."""
    tabs = []
    for title, description, df in tables:
        table_id = f'resultTable{len(tabs)}'
        tabs.append({
            'id': table_id,
            'title': title,
            'description': description,
            'hit_count': len(df),
            'html': df.to_html(classes='display', escape=False, table_id=table_id, index=False, na_rep='') if len(df.columns) else '',
        })
    if not tabs:
        return None
    return render(request, 'results_tabbed_tables.html', {
        'job_id': job_id,
        'pageTitle': page_title,
        'tables': tabs,
        'citation': citation_for(job_id),
    })

def tabbed_table_results(request, job_id, download_dir, page_title, tables):
    """Results page with one selectable tab per result table file that exists in download_dir.
    tables: (filename, tab title, description) tuples in display order."""
    frames = []
    for filename, title, description in tables:
        path = matching_file_in_dir(download_dir, filename)
        if not path:
            continue
        try:
            df = pd.read_csv(path, sep='\t', engine='python')
        except Exception:
            df = pd.DataFrame()
        frames.append((title, description, df))
    return render_result_tabs(request, job_id, page_title, frames)


# ---- one-line results for the common cases ----
def table_results(filename, title, **options):
    """Show one delimited file as a filterable table (options as for generic_table_results)."""
    return lambda request, job_id, download_dir: generic_table_results(request, job_id, download_dir, filename, title, **options)


def html_results(filename, title):
    """Show a self-contained HTML report produced by the tool."""
    return lambda request, job_id, download_dir: generic_html_results(request, job_id, download_dir, filename, title)


def tabbed_results(page_title, tables):
    """One tab per table file that exists; tables: (filename, tab title, description) tuples."""
    return lambda request, job_id, download_dir: tabbed_table_results(request, job_id, download_dir, page_title, tables)


def first_of(*result_functions):
    """Use the first of several results functions that has something to show."""
    def results(request, job_id, download_dir):
        for function in result_functions:
            response = function(request, job_id, download_dir)
            if response:
                return response
    return results
