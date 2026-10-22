from django.conf import settings
from baclab.toolkit import Tool, cores, database, genome_form, table_results

tool = Tool(
    name='padloc',
    title='PADLOC (antiviral defence)',
    category='annot',
    form=genome_form(('.fasta', '.fa', '.fna'), min_files=1, max_files=settings.MAX_GENOMES_PER_JOB),
    args=lambda request: [cores(), database('PadlocDB')],
    outputs=['padloc_results.csv', 'padloc_results.gff'],
    results=table_results(
        'padloc_results.csv', 'PADLOC Defence Systems', sep=',', table_id='padlocResultsTable',
        usecols=['genome', 'system.number', 'seqid', 'system', 'target.name', 'protein.name', 'full.seq.E.value',
                 'domain.iE.value', 'target.coverage', 'hmm.coverage', 'start', 'end', 'strand']),
    citation=[{
        'text': 'Payne LJ, Meaden S, Mestre MR, et al. PADLOC: a web server for the identification of antiviral defence systems in microbial genomes. Nucleic Acids Res. 2022;50(W1):W541-W550.',
        'url': 'https://doi.org/10.1093/nar/gkac400',
    }],
    example=[('quast_example.fasta', 'padloc_example.fasta')],
    faq_title='How to use PADLOC?',
    faq=['Upload one or more genome assemblies in FASTA format (.fasta, .fa, .fna).',
         'Click Submit to detect antiviral defence systems with PADLOC.',
         'Browse the detected systems on the results page; the full table and GFF are in the download.'],
)
