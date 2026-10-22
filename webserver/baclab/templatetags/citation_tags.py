from django import template
from baclab.citations import PLATFORM_CITATION, citations_for

register = template.Library()


@register.inclusion_tag('partials/platform_citation_box.html')
def baclab_citation():
    """
    Renders the "please cite BacLab" box - the platform itself, separate from
    whichever individual tool(s) a given page's `tool_citation` credits.

    Edit PLATFORM_CITATION in baclab/citations.py to update it (e.g. once the
    paper has a real DOI); nothing else needs to change.
    """
    return {'citation': PLATFORM_CITATION}


@register.inclusion_tag('partials/citation_box.html')
def tool_citation(identifier):
    """
    Renders the "please cite" box for a tool.

    `identifier` can be either a bare job_type (e.g. "checkm", used on the
    submission page) or a job_id (e.g. "checkm-<uuid>", used on the results
    page) - the tool key is always the part before the first "-", matching
    the convention already used elsewhere in views.py.

    Citations themselves live in baclab/citations.py - edit that file to
    add, change, or remove what is shown here.
    """
    if not identifier:
        return {'citations': []}

    return {'citations': citations_for(identifier.split('-')[0])}
