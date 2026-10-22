import os

from django.shortcuts import render

from baclab.toolkit import Tool, cores


def mlst_results(request, job_id, download_dir):
    tsv_path = os.path.join(download_dir, 'mlst_results.tsv')
    headers = []
    rows = []
    if os.path.exists(tsv_path):
        with open(tsv_path, 'r', encoding='utf-8') as f:
            parsed_rows = [line.rstrip('\n').split('\t') for line in f if line.strip()]
        if parsed_rows:
            max_cols = max(len(r) for r in parsed_rows)
            headers = ['File', 'Scheme', 'Sequence Type'] + [f'Allele {i}' for i in range(1, max_cols - 2)]
            headers = headers[:max_cols]
            rows = [r + [''] * (max_cols - len(r)) for r in parsed_rows]
            for row in rows:
                row[0] = os.path.basename(row[0])   # the scheme output names the input by its path on the server

    context = {
        'job_id': job_id,
        'headers': headers,
        'rows': rows,
    }
    return render(request, 'results_mlst.html', context)


tool = Tool(
    name='mlst',
    title='MLST',
    category='strain',
    file_only=True,
    args=lambda request: [cores()],
    results=mlst_results,
    citation=[
        {
            'text': 'Seemann T. mlst: scan contig files against PubMLST typing schemes.',
            'url': 'https://github.com/tseemann/mlst',
        },
        {
            'text': 'Jolley KA, Bray JE, Maiden MCJ. 2018. Open-access bacterial population genomics: BIGSdb software, the PubMLST.org website and their applications. Wellcome Open Research 3:124.',
        },
    ],
    example=[('mlst_example.fasta', 'mlst_example.fasta')],
    faq=['Upload your genome assemblies (FASTA files).',
         'Click Submit to determine the sequence type (ST) and allele calls against PubMLST schemes.',
         'Results can be viewed and downloaded on the results page.'],
)
