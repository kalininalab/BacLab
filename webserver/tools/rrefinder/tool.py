from django.conf import settings
from django import forms

from baclab.toolkit import Tool, choice, cores, genome_form, tabbed_results

MODES = ('precision', 'exploratory', 'both')


class Form(genome_form(('.faa', '.fasta', '.fa', '.gbk', '.gb', '.gbff'), min_files=1, max_files=settings.MAX_GENOMES_PER_JOB)):
    mode = forms.ChoiceField(choices=[(m, m) for m in MODES], required=False)


tool = Tool(
    name='rrefinder',
    title='RRE-Finder',
    category='annot',
    form=Form,
    args=lambda request: [cores(), choice(request.POST.get('mode'), MODES, 'both')],
    outputs=['rrefinder_precision.tsv', 'rrefinder_exploratory.tsv', 'rrefinder_exploratory_resubmit.tsv'],
    results=tabbed_results('RRE-Finder RiPP Recognition Elements', [
        ('rrefinder_precision.tsv', 'Precision', 'Hits of the curated RREfam HMMs: high confidence, fast.'),
        ('rrefinder_exploratory.tsv', 'Exploratory', 'Initial HMM scan with the broader RRE profiles: also finds more distant RREs, with more false positives.'),
        ('rrefinder_exploratory_resubmit.tsv', 'Exploratory (resubmitted)', 'The exploratory hits searched again against the RRE reference database, with probability and alignment details.'),
    ]),
    citation=[{
        'text': 'Kloosterman AM, Shelton KE, van Wezel GP, Medema MH, Mitchell DA. RRE-Finder: a genome-mining tool for class-independent RiPP discovery. mSystems. 2020;5(5):e00267-20.',
        'url': 'https://doi.org/10.1128/mSystems.00267-20',
    }],
    example=['rrefinder_example'],
    faq=['Upload protein FASTA files or GenBank files and choose precision, exploratory or both modes.',
         'Click Submit to detect RiPP Recognition Elements.',
         'See the detected RREs on the results page.'],
)
