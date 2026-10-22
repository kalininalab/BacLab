from baclab.toolkit import Tool, cores, table_results


tool = Tool(
    name='ani',
    title='ANI (FastANI)',
    category='compgen',
    file_only=True,
    exclude=['genome_list.txt'],   # internal working data, not results
    args=lambda request: [cores()],
    results=table_results('ani_results.tsv', 'FastANI Results', table_id='aniResultsTable'),
    citation=[
        {
            'text': 'Jain C, Rodriguez-R LM, Phillippy AM, Konstantinidis KT, Aluru S. 2018. High throughput ANI analysis of 90K prokaryotic genomes reveals clear species boundaries. Nature Communications 9:5114.',
            'url': 'https://github.com/ParBLiSS/FastANI',
        },
    ],
    example=[('ani_example', 'ani_example')],
    faq_title='How to use FastANI (ANI)?',
    faq=['Upload 2 or more genome assemblies (FASTA files) at once.',
         'Click Submit to get an all-vs-all Average Nucleotide Identity comparison - the standard ~95% threshold for "same species."',
         'Results can be viewed and downloaded on the results page.'],
)
