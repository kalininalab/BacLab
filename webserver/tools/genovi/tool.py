from django.conf import settings
from baclab.toolkit import Tool, choice, genome_form, html_results

tool = Tool(
    name='genovi',
    title='GenoVi (circular plot)',
    category='annot',
    form=genome_form(('.gbk', '.gb', '.gbff'), min_files=1, max_files=settings.MAX_GENOMES_PER_JOB),
    args=lambda request: [choice(request.POST.get('genome_status'), ('complete', 'draft'), 'complete')],
    outputs=['genovi_plots.html', 'genovi_*.svg', 'genovi_*.png'],
    results=html_results('genovi_plots.html', 'GenoVi Circular Genome Plots'),
    citation=[{
        'text': 'Cumsille A, Duran RE, Rodriguez-Delherbe A, et al. GenoVi, an open-source automated circular genome visualizer for bacteria and archaea. PLoS Comput Biol. 2023;19(4):e1010998.',
        'url': 'https://doi.org/10.1371/journal.pcbi.1010998',
    }],
    example=[('klebsiella_pneumoniae_pKPHS2.gb', 'klebsiella_pneumoniae_pKPHS2.gb')],   # the 111 kb plasmid pKPHS2 of K. pneumoniae HS11286
    faq_title='How to use GenoVi?',
    faq=['Upload one or more annotated genomes in GenBank format (.gbk, .gb, .gbff) and choose complete or draft.',
         'Click Submit to draw a circular genome plot (at most 200 contigs).',
         'Download the plots as SVG or PNG from the results page.'],
)
