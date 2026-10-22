"""The tool menus (navigation bar, home page picker, FAQ) are built from the registered tools."""

# (key, title): the order here is the order of the menus. A tool's `category` is one of these keys.
CATEGORIES = [
    ('qc', 'Quality Control & Assembly'),
    ('amr', 'AMR, Virulence & Mobile Elements'),
    ('strain', 'Strain Typing & Taxonomy'),
    ('compgen', 'Comparative Genomics'),
    ('annot', 'Annotation & Biosynthetic Gene Clusters'),
    ('search', 'Sequence Search'),
]
CATEGORY_KEYS = [key for key, _ in CATEGORIES]
