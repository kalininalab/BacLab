"""Sphinx configuration of the BacLab documentation (built by Read the Docs, see ../.readthedocs.yaml).

Local build:  pip install -r docs/requirements.txt && sphinx-build -b html docs docs/_build/html
"""
import os

project = 'BacLab'
author = 'BacLab authors'
copyright = '2026, BacLab authors'
release = '1.0.0'

extensions = ['myst_parser']
source_suffix = {'.md': 'markdown'}
root_doc = 'index'
exclude_patterns = ['_build', '_demos', 'Thumbs.db', '.DS_Store', 'README.md']

myst_enable_extensions = ['colon_fence', 'deflist', 'attrs_inline']
myst_heading_anchors = 3
suppress_warnings = ['myst.header', 'myst.xref_missing']

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_css_files = ['custom.css']
html_theme_options = {'navigation_depth': 3, 'collapse_navigation': False}

# The static demonstrations (docs/_demos/demos/*.html) are published as they are, under /demos/
_demos = os.path.join(os.path.dirname(__file__), '_demos')
html_extra_path = [_demos] if os.path.isdir(_demos) else []
