"""Django-side view on db_catalog: what is installed under /databases, and what a given tool is missing."""
import os

from django.conf import settings

from . import db_catalog


def databases_dir():
    return settings.DATABASES_DIR


def overview(with_size=False):
    """One dict per catalog entry: the entry, whether it is installed, the tools using it (titles) and optionally its size."""
    from .toolkit import registry
    titles = {tool.name: tool.title for tool in registry.all_tools()}
    rows = []
    for entry, installed in db_catalog.status(databases_dir()):
        folder = entry.get('install', {}).get('target') or ''
        size = None
        if with_size and installed:
            first = (entry.get('markers_all') or entry.get('markers_any'))[0].split('/')[0]
            size = db_catalog.human_size(db_catalog.folder_size(os.path.join(databases_dir(), first)))
        rows.append({'entry': entry, 'installed': installed, 'size': size, 'folder': folder,
                     'tools': [titles.get(name, name) for name in entry['tools']]})
    return rows


def missing_for_tool(tool):
    """Titles of the required databases of this tool (a toolkit Tool or a legacy key) that are not installed."""
    key = tool if isinstance(tool, str) else tool.name
    missing = [entry['title'] for entry in db_catalog.missing_for_tool(key, databases_dir())]
    if not isinstance(tool, str):   # folders named by a custom tool
        for folder in getattr(tool, 'databases', []):
            path = os.path.join(databases_dir(), folder)
            if tool.source == 'custom' and not (os.path.isdir(path) and os.listdir(path)):
                missing.append(f'databases/{folder}')
    return missing
