from baclab.toolkit import Tool, cores, table_results


tool = Tool(
    name='gecco',
    title='GECCO',
    category='annot',
    file_only=True,
    exclude=['**/*.genes.tsv', '**/*.features.tsv'],   # internal working data, not results
    args=lambda request: [cores()],
    results=table_results('gecco_results.tsv', 'GECCO Clusters', table_id='geccoResultsTable'),
    citation=[
        {
            'text': 'Carroll LM, Larralde M, Fleck JS, Ponnudurai R, Milanese A, Cappio Barazzone E, Zeller G. 2021. Accurate de novo identification of biosynthetic gene clusters with GECCO. bioRxiv.',
            'url': 'https://github.com/zellerlab/GECCO',
        },
    ],
    example=[('gecco_example.fasta', 'gecco_example.fasta')],
    faq=['Upload your genome assemblies (FASTA files).',
         "Click Submit to predict biosynthetic gene clusters with GECCO's ML model, complementing antiSMASH.",
         'Results can be viewed and downloaded on the results page.'],
)
