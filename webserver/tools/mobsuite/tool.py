from baclab.toolkit import Tool, cores, table_results


tool = Tool(
    name='mobsuite',
    title='MOB-suite',
    category='amr',
    file_only=True,
    args=lambda request: [cores()],
    results=table_results('mobsuite_results.tsv', 'MOB-suite Results', table_id='mobsuiteResultsTable'),
    citation=[
        {
            'text': 'Robertson J, Nash JHE. 2018. MOB-suite: software tools for clustering, reconstruction and typing of plasmids from draft assemblies. Microbial Genomics 4(8).',
        },
    ],
    example=[('mobsuite_example.fasta', 'mobsuite_example.fasta')],
    faq=['Upload your genome assemblies (FASTA files).',
         'Click Submit to reconstruct, cluster, and mobility-type plasmids beyond simple replicon detection.',
         'Results can be viewed and downloaded on the results page.'],
)
