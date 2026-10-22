from baclab.toolkit import Tool, cores, table_results


tool = Tool(
    name='checkm',
    title='CheckM',
    category='qc',
    file_only=True,
    exclude=['bins', 'storage', 'lineage.ms'],   # internal working data, not results
    args=lambda request: [cores()],
    results=table_results('checkm_results.tsv', 'CheckM Results', table_id='checkmResultsTable'),
    citation=[
        {
            'text': 'Parks DH, Imelfort M, Skennerton CT, Hugenholtz P, Tyson GW. 2015. CheckM: assessing the quality of microbial genomes recovered from isolates, single cells, and metagenomes. Genome Research 25(7):1043-1055.',
        },
    ],
    example=[('checkm_example.fasta', 'checkm_example.fasta')],
    faq=['Upload your genome assemblies (FASTA files).',
         'Click Submit to assess the completeness and contamination of the genomes.',
         'Results can be viewed and downloaded on the results page.'],
)
