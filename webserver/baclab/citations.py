"""
The "please cite" boxes shown on every tool's submission and results page.

The citations of a tool are part of the tool: `citation=[{"text": ..., "url": ...}]` in webserver/tools/<name>/tool.py (or the field of a tool
added in the admin). The box is rendered generically from them by the `tool_citation` template tag (see templatetags/citation_tags.py), and the
same entries are written to CITATION.txt in every result archive. The only citation kept here is the one of the platform itself.

Each citation is a dict: {"text": "Author A, et al. Year. Title. Journal.", "url": "https://..."}; "url" is optional.
"""

# The tools' own citations credit the underlying third-party software (e.g. SPAdes or CheckM). This one credits the BacLab *platform itself* - the
# thing to cite for having run the analysis through this server at all, on
# top of whichever individual tools were used.
#
# >>> PLACEHOLDER - THE BACLAB PAPER <<<
# Replace "text" with the real reference once the paper is published/preprinted
# (authors, title, journal, year) and set "url" to its DOI or bioRxiv link.
# While "url" is None the cite boxes, CITATION.txt in every result archive and
# the README say "manuscript in preparation" instead of showing a broken link.
# The same reference belongs in /CITATION.cff and the README ("Citing BacLab").
PLATFORM_CITATION = {
    "text": "Yurtseven A, et al. BacLab: a self-hosted, containerized web platform for integrated bacterial genomics and genome mining. [Journal, year - PLACEHOLDER, to be published]",
    "url": None,
}


def citations_for(tool_key):
    """The citations of a tool: the `citation` of its Tool (tools/<name>/tool.py, or a tool added in the admin)."""
    from .toolkit import registry
    tool = registry.get(tool_key)
    entries = tool.citation if tool is not None else []
    if isinstance(entries, dict):
        entries = [entries]
    return entries
