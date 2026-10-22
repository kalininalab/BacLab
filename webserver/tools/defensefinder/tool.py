from django.conf import settings
from baclab.toolkit import Tool, cores, database, genome_form, tabbed_results

tool = Tool(
    name='defensefinder',
    title='DefenseFinder',
    category='annot',
    form=genome_form(('.fasta', '.fa', '.fna'), min_files=1, max_files=settings.MAX_GENOMES_PER_JOB),
    args=lambda request: [cores(), database('DefenseFinderDB')],
    outputs=['defensefinder_results.tsv', 'defensefinder_genes.tsv'],
    results=tabbed_results('DefenseFinder Defense Systems', [
        ('defensefinder_results.tsv', 'Systems', 'The complete defense systems found: their type and subtype, the genes they span and how many genes they contain.'),
        ('defensefinder_genes.tsv', 'Genes', 'Every gene that is part of a detected system, with its match quality (e-value, score, coverage) and the system it belongs to.'),
    ]),
    citation=[{
        'text': 'Tesson F, Herve A, Mordret E, et al. Systematic and quantitative view of the antiviral arsenal of prokaryotes. Nat Commun. 2022;13:2561.',
        'url': 'https://doi.org/10.1038/s41467-022-30269-9',
    }],
    example=[('quast_example.fasta', 'defensefinder_example.fasta')],
    faq=['Upload one or more genome assemblies in FASTA format (.fasta, .fa, .fna).',
         'Click Submit to detect anti-phage defence systems with DefenseFinder.',
         'Download the systems and per-gene tables from the results page.'],
)
