from django.shortcuts import render

from baclab.toolkit import Tool, cores


def spades_results(request, job_id, download_dir):
    context = {
        'job_id': job_id,
        'download_dir': download_dir
    }
    return render(request, 'results_spades.html', context)


tool = Tool(
    name='spades',
    title='Assembly & QC Pipeline (SPAdes)',
    category='qc',
    file_only=True,
    exclude=['K*', 'tmp', 'misc', 'corrected', 'before_rr.fasta', 'pipeline_state', 'run_spades.yaml', 'run_spades.sh', 'input_dataset.yaml', 'dataset.info', 'checkm/bins', 'checkm/storage', 'checkm/lineage.ms', '**/multiqc_report_data'],   # internal working data, not results
    args=lambda request: [cores(), request.POST.get('read_type', 'single')],
    results=spades_results,
    citation=[
        {
            'text': 'Bankevich A, Nurk S, Antipov D, et al. 2012. SPAdes: a new genome assembly algorithm and its applications to single-cell sequencing. Journal of Computational Biology 19(5):455-477.',
        },
    ],
    example=[('ecoli_1K_1.fq.gz', 'ecoli_1K_1.fq.gz'),
             ('ecoli_1K_2.fq.gz', 'ecoli_1K_2.fq.gz')],
    faq_title='How to use SPAdes?',
    faq=['Upload your raw sequencing reads (FASTQ files).',
         'Select whether they are single-end or paired-end reads.',
         'Click Submit to assemble the reads into contigs. SPAdes will generate high-quality genomes de novo.',
         'Assembly metrics (N50, L50) and final FASTA files can be viewed and downloaded on the results page.'],
)
