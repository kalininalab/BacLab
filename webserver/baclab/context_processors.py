from . import tool_catalog
from .models import ThemeSettings, InhouseStrainCollection
from .toolkit import registry
from django.urls import reverse
from .toolkit.menu import CATEGORIES, CATEGORY_KEYS

def _enabled_map(request):
    """tool_catalog.enabled_map(), computed once per request (two context processors need it)."""
    cached = getattr(request, '_enabled_map', None)
    if cached is None:
        cached = request._enabled_map = tool_catalog.enabled_map()
    return cached


def dynamic_tools(request):
    """
    The enabled tools (tools/<name>/tool.py folders and tools added in the admin), for the menus and the home page:
    `dyn_tools` maps a category key to its tools; `dyn_tool_list` is the flat list; `tool_menu` the columns of the tools menu.
    """
    enabled = _enabled_map(request)
    grouped = {key: [] for key in CATEGORY_KEYS}
    flat = []
    for tool in registry.all_tools():
        if tool.source == 'custom':
            on = getattr(tool, 'admin_enabled', False)
        else:
            on = tool_catalog.is_enabled(tool.settings_key, enabled)
        if on and tool.category in grouped:
            grouped[tool.category].append(tool)
            flat.append(tool)

    # The "tools" dropdown: one column per category, every enabled tool sorted by name
    columns = []
    for number, (key, title) in enumerate(CATEGORIES, 1):
        entries = [{'title': tool.title, 'url': tool.url} for tool in grouped[key]]
        if entries:
            columns.append({'number': f'{number:02d}', 'title': title, 'tools': sorted(entries, key=lambda e: e['title'].lower())})
    return {'dyn_tools': grouped, 'dyn_tool_list': flat, 'tool_menu': columns}

def theme_settings(request):
    try:
        theme = ThemeSettings.objects.get(pk=1)
        return {'theme': theme}
    except ThemeSettings.DoesNotExist:
        return {'theme': None}

def strain_collections(request):
    try:
        collections = list(InhouseStrainCollection.objects.all())
    except Exception:
        collections = []
    return {'nav_collections': collections}



def accounts(request):
    """Whether the optional user accounts are switched on (login links, "my jobs")."""
    from django.conf import settings
    from . import email_policy
    return {'accounts_enabled': settings.ACCOUNTS_ENABLED, 'allow_signup': settings.ACCOUNTS_ENABLED and settings.ALLOW_SIGNUP,
            'email_policy_hint': email_policy.describe(), 'api_enabled': settings.ACCOUNTS_ENABLED and settings.API_ENABLED}
