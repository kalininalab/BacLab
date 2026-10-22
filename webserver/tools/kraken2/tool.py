from baclab.toolkit import Tool, cores, database, table_results


tool = Tool(
    name='kraken2',
    title='Kraken2',
    category='strain',
    file_only=True,
    args=lambda request: [cores(), database('Kraken2DB')],
    results=table_results('kraken2_results.tsv', 'Kraken2 Report', header=None, table_id='kraken2ResultsTable',
                          columns=['Percent', 'Reads Covered', 'Reads Assigned Direct', 'Rank', 'TaxID', 'Name']),
    citation=[
        {
            'text': 'Wood DE, Lu J, Langmead B. 2019. Improved metagenomic analysis with Kraken 2. Genome Biology 20:257.',
        },
    ],
    example=[('kraken2_example.fasta', 'kraken2_example.fasta')],
    faq=['Upload your genome assemblies (FASTA files).',
         'Click Submit to get a fast k-mer based taxonomic classification, useful as a contamination/species-ID check.',
         'Results can be viewed and downloaded on the results page.'],
)
