"""A ready-to-adapt "Methods" paragraph for a finished run: tool, version, settings, databases, references."""
import glob
import os
from datetime import datetime

from django.conf import settings

from . import db_catalog, tool_versions
from .citations import citations_for


def database_lines(job_type, databases_dir=None):
    """['PADLOC-DB (downloaded 2026-10-14)', ...] for the databases of the tool that are installed."""
    key = job_type
    root = databases_dir or settings.DATABASES_DIR
    lines = []
    for entry in db_catalog.entries_for_tool(key):
        if not db_catalog.is_installed(entry, root):
            continue
        pattern = (entry.get('markers_all') or entry.get('markers_any'))[0]
        hits = glob.glob(os.path.join(root, pattern), recursive=True)
        stamp = f" (installed {datetime.fromtimestamp(os.path.getmtime(hits[0])):%Y-%m-%d})" if hits else ''
        lines.append(f"{entry['title']}{stamp}")
    return lines


def methods_text(job):
    """Plain text; the caller shows or downloads it."""
    version = tool_versions.version_of(job.job_type)
    settings_used = (job.parameters or {}).get('settings', {})
    inputs = (job.parameters or {}).get('inputs', [])
    parts = [f"{job.tool_label}{f' (version {version})' if version else ''} was run on the BacLab web platform "
             f"(version {settings.BACLAB_VERSION}) on {job.queued_at:%d %B %Y}"
             + (f" with {len(inputs)} input file{'s' if len(inputs) != 1 else ''}" if inputs else '') + '.']
    if settings_used:
        parts.append("Settings: " + ", ".join(f"{k} = {v}" for k, v in settings_used.items()) + ".")
    databases = database_lines(job.job_type)
    if databases:
        parts.append("Reference data: " + "; ".join(databases) + ".")
    references = [f"- {c['text']}" + (f" {c['url']}" if c.get('url') else '') for c in citations_for(job.job_type)]
    text = ' '.join(parts)
    if references:
        text += "\n\nPlease cite:\n" + "\n".join(references)
    return text
