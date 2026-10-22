from baclab.toolkit import Tool, cores, table_results


tool = Tool(
    name='fastaai',
    title='FastAAI',
    category='compgen',
    file_only=True,
    exclude=['predicted_proteins', 'hmms', 'database', 'logs', 'fastaai.log'],   # internal working data, not results
    args=lambda request: [cores()],
    results=table_results('fastaai_results.tsv', 'FastAAI Results', table_id='fastaaiResultsTable'),
    citation=[
        {
            'text': 'Gerhardt K, Ruiz-Perez CA, Rodriguez-R LM, Konstantinidis KT. 2023. FastAAI: Efficient estimation of genome average amino acid identity and phylum-level relationships using tetramers of universal proteins.',
            'url': 'https://github.com/cruizperez/FastAAI',
        },
    ],
    example=[('ani_example', 'ani_example')],
    faq=['Upload 2 or more genome assemblies (FASTA files) at once.',
         'Click Submit to get an all-vs-all Average Amino Acid Identity estimate - a genus-level companion to ANI that stays informative further apart than ANI does.',
         'Results can be viewed and downloaded on the results page.'],
)
