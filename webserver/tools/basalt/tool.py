from django import forms
from django.core.exceptions import ValidationError

from baclab.toolkit import Tool, choice, cores, database, rename_uploaded_input, saved_name, table_results

SENSITIVITIES = ('quick', 'sensitive', 'more-sensitive')
# BASALT is memory hungry (its docs suggest 128 GB for routine datasets; 32 GB is the minimum).
RAM_GB = 128


class Form(forms.Form):
    """BASALT: an assembly (FASTA) plus its paired short reads (both mates required)."""
    ASSEMBLY_EXTENSIONS = ('.fasta', '.fa', '.fna')
    READ_EXTENSIONS = ('.fastq', '.fastq.gz', '.fq', '.fq.gz')

    assembly = forms.FileField(required=True)
    read1 = forms.FileField(required=True)
    read2 = forms.FileField(required=True)
    sensitivity = forms.ChoiceField(choices=[(s, s) for s in SENSITIVITIES], required=False)

    def clean(self):
        cleaned_data = super().clean()
        for field, extensions in (('assembly', self.ASSEMBLY_EXTENSIONS), ('read1', self.READ_EXTENSIONS), ('read2', self.READ_EXTENSIONS)):
            uploaded = cleaned_data.get(field)
            if uploaded and not uploaded.name.lower().endswith(extensions):
                raise ValidationError(f"\"{uploaded.name}\" has an unsupported extension. Allowed extensions: {', '.join(extensions)}.")
        return cleaned_data


def prepare_inputs(request, input_dir):
    # The script finds the three inputs by these fixed names.
    for field in ('assembly', 'read1', 'read2'):
        rename_uploaded_input(input_dir, saved_name(request, field), field)


tool = Tool(
    name='basalt',
    title='BASALT (metagenome binning)',
    category='qc',
    form=Form,
    prepare_inputs=prepare_inputs,
    args=lambda request: [cores(), database('BasaltDB'), database('Checkm2DB'), RAM_GB,
                          choice(request.POST.get('sensitivity'), SENSITIVITIES, 'quick')],
    outputs=['basalt_quality_report.tsv', 'basalt_bins'],
    results=table_results('basalt_quality_report.tsv', 'BASALT Bin Quality', table_id='basaltResultsTable',
                          note='The bin FASTA files are in the downloadable results (basalt_bins/).'),
    citation=[{
        'text': 'Qiu Z, Yuan L, Lian CA, et al. BASALT refines binning from metagenomic data and increases resolution of genome-resolved metagenomic analysis. Nat Commun. 2024;15:2179.',
        'url': 'https://doi.org/10.1038/s41467-024-46539-7',
    }],
    faq_title='How to use BASALT?',
    faq=['Upload a metagenome assembly (FASTA) and the paired-end reads (read 1 and read 2) it was assembled from.',
         'Click Submit to bin the contigs into genomes (MAGs). This is a heavy analysis and can take hours.',
         'Download the bins and their quality table from the results page.'],
)
