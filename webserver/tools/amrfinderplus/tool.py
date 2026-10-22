from baclab.toolkit import Tool, cores, table_results


tool = Tool(
    name='amrfinderplus',
    title='AMRFinderPlus',
    category='amr',
    file_only=True,
    args=lambda request: [cores(), request.POST.get('organism', 'none') or 'none'],
    results=table_results('amrfinderplus_results.tsv', 'AMRFinderPlus Results', table_id='amrfinderplusResultsTable'),
    citation=[
        {
            'text': 'Feldgarden M, Brover V, Gonzalez-Escalona N, et al. 2021. AMRFinderPlus and the Reference Gene Catalog facilitate examination of the genomic links among antimicrobial resistance, stress response, and virulence. Scientific Reports 11:12728.',
        },
    ],
    example=[('amrfinderplus_example.fasta', 'amrfinderplus_example.fasta')],
    faq=['Upload your genome assemblies (FASTA files), optionally selecting an organism for point-mutation-aware calling.',
         'Click Submit to detect AMR, stress, and virulence genes.',
         'Results can be viewed and downloaded on the results page.'],
)
