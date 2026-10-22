"""Finds the tools.

* Built-in tools: every tools/<folder>/tool.py defines `tool = Tool(...)`.
* Custom tools: rows of models.CustomTool, added by an administrator without touching the code
  (see toolkit/custom.py). They are re-read when a row changes, so a new tool needs no restart.
"""
import importlib.util
import logging
import os
import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError

logger = logging.getLogger(__name__)

_builtin = {}
_discovered = False
_custom = {}
_custom_stamp = None


def reserved_names():
    """Names a tool may not take: the top-level pages of the platform."""
    from ..tool_catalog import RESERVED_URL_NAMES
    return set(RESERVED_URL_NAMES)


def discover():
    """Import every tools/*/tool.py once."""
    global _discovered
    if _discovered:
        return
    _discovered = True
    tools_dir = settings.TOOLS_DIR
    if not os.path.isdir(tools_dir):
        return
    taken = reserved_names()
    for folder in sorted(os.listdir(tools_dir)):
        path = os.path.join(tools_dir, folder, 'tool.py')
        if not os.path.isfile(path):
            continue
        spec = importlib.util.spec_from_file_location(f'baclab_tool_{folder}', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module   # so what the module defines (its exceptions) can be pickled and imported by name
        spec.loader.exec_module(module)
        tool = module.tool
        if tool.name in taken or tool.name in _builtin:
            raise ImproperlyConfigured(f'tools/{folder}/tool.py: the tool name "{tool.name}" is already in use')
        tool.directory = os.path.join(tools_dir, folder)
        _builtin[tool.name] = tool


def refresh_custom(force=False):
    """(Re)build the tools of the admin-defined rows when they changed since the last call."""
    global _custom, _custom_stamp
    try:
        from django.db.models import Count, Max
        from ..models import CustomTool
        from . import custom
        summary = CustomTool.objects.aggregate(count=Count('pk'), stamp=Max('updated_at'))
        stamp = (summary['count'], summary['stamp'])
        if force or stamp != _custom_stamp:
            _custom = {row.name: custom.build_tool(row) for row in CustomTool.objects.all()}
            _custom_stamp = stamp
    except DatabaseError as error:   # no table yet (before the first migrate): there are no custom tools
        logger.warning('Custom tools not loaded: %s', error)
    except Exception:   # a broken row: keep what we have
        logger.exception('Could not load the custom tools')


def builtin_tools():
    discover()
    return sorted(_builtin.values(), key=lambda tool: tool.title.lower())


def get(name):
    """The tool with this job type, or None."""
    discover()
    if name in _builtin:
        return _builtin[name]
    refresh_custom()
    return _custom.get(name)


def all_tools(include_custom=True):
    discover()
    tools = list(_builtin.values())
    if include_custom:
        refresh_custom()
        tools += list(_custom.values())
    return sorted(tools, key=lambda tool: tool.title.lower())
