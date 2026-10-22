from baclab.toolkit import Tool, cores, database, table_results


tool = Tool(
    name='checkm2',
    title='CheckM2',
    category='qc',
    file_only=True,
    exclude=['protein_files', 'diamond_output'],   # internal working data, not results
    args=lambda request: [cores(), database('Checkm2DB')],
    results=table_results('checkm2_results.tsv', 'CheckM2 Results', table_id='checkm2ResultsTable'),
    citation=[
        {
            'text': 'Chklovski A, Parks DH, Woodcroft BJ, Tyson GW. 2023. CheckM2: a rapid, scalable and accurate tool for assessing microbial genome quality using machine learning. Nature Methods 20:1203-1212.',
        },
    ],
    example=[('checkm2_example.fasta', 'checkm2_example.fasta')],
    faq=['Upload your genome assemblies (FASTA files).',
         'Click Submit to get an ML-based completeness/contamination estimate - a fast second opinion alongside CheckM.',
         'Results can be viewed and downloaded on the results page.'],
)
