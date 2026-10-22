"""Which tools are switched on, and the URL names a tool must not take.

Every tool is a tools/<name>/tool.py folder (or a tool added in the admin): they describe themselves (see baclab/toolkit/tool.py) and appear in the
menus automatically. This module only knows the switches (enabled_tools.csv, the admin's Tool switches, ENABLE_TOOL_<key> variables).
"""
import csv
import os

from django.conf import settings

# First URL segments that belong to the platform; a custom tool must not use them.
RESERVED_URL_NAMES = {
    'admin', 'about', 'terms', 'results', 'qrcode', 'sample', 'strains', 'accounts', 'download', 'custom', 'static',
    'media', 'job_progress', 'faa_viewer', 'taxonomy', 'taxonomy_database', 'phylogenetic_tree', 'annotation',
    'example-data', 'example-results', 'report-file', 'api', 'health', 'ckeditor', 'databases', 'data', 'tools',
}


def csv_defaults():
    """{tool key: enabled} from enabled_tools.csv - the defaults shipped with the code."""
    tools = {}
    try:
        with open(os.path.join(str(settings.ROOT_DIR), 'enabled_tools.csv'), newline='') as handle:
            for row in csv.DictReader(handle):
                name = (row.get('tool') or '').strip()
                if name:
                    tools[name] = (row.get('enabled') or '').strip() == '1'
    except OSError:
        pass
    return tools


def enabled_map():
    """{tool key: enabled}. Precedence: ENABLE_TOOL_<key> environment variable, then the switch in the admin
    (models.ToolSetting), then enabled_tools.csv. Tools nobody mentioned count as enabled."""
    tools = csv_defaults()
    try:
        from .models import ToolSetting
        for setting in ToolSetting.objects.all():
            tools[setting.tool] = setting.enabled
    except Exception:   # before the first migrate
        pass
    for key, value in os.environ.items():
        if key.startswith('ENABLE_TOOL_'):
            tools[key[len('ENABLE_TOOL_'):]] = value.strip().lower() in ('1', 'true', 'yes', 'on')
    return tools


def is_enabled(key, tools=None):
    tools = enabled_map() if tools is None else tools
    if key in tools:
        return tools[key]
    lowered = {name.lower(): value for name, value in tools.items()}
    return lowered.get(key.lower(), True)
