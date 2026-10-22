from baclab.toolkit import Tool, cores, first_of, table_results


tool = Tool(
    name='snippy',
    title='Snippy',
    category='compgen',
    file_only=True,
    args=lambda request: [cores(), request.POST.get('reference_source', 'upload'), request.POST.get('reference_taxid', ''), request.POST.get('ref_filename', '')],
    results=first_of(table_results('*snps.tab', 'Snippy SNPs/Variants', table_id='snippyResultsTable'),
                      table_results('*/snps.tab', 'Snippy SNPs/Variants', table_id='snippyResultsTable'),
                      table_results('*snps.csv', 'Snippy SNPs/Variants', sep=',', table_id='snippyResultsTable')),
    citation=[
        {
            'text': 'Seemann T. Snippy: rapid haploid variant calling and core genome alignment.',
            'url': 'https://github.com/tseemann/snippy',
        },
    ],
    example=[('klebsiella_pneumoniae_NTUH_K2044.fna', 'klebsiella_pneumoniae_NTUH_K2044.fna')],   # a hypervirulent K1 isolate, compared with the species reference
    example_post={'reference_source': 'taxid', 'reference_taxid': '573'},   # no reference file to upload: fetch the K. pneumoniae reference
    faq=['Upload your NGS sequence reads or assembled contigs.',
         'Provide a reference genome by either uploading a FASTA file or specifying a Taxonomy ID to fetch from RefSeq.',
         'Click Submit to run Snippy. Snippy will find SNPs between the reference and your input sequences.',
         'Results can be downloaded on the results page.'],
)
