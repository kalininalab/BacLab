from django.shortcuts import render

from baclab.toolkit import Tool, cores, matching_file_in_dir


def gubbins_results(request, job_id, download_dir):
    tree_file = matching_file_in_dir(download_dir, '*.final_tree.tre', '*.node_labelled.final_tree.tre')

    phylogenetic_tree_string = None
    if tree_file:
        with open(tree_file, 'r') as f:
            phylogenetic_tree_string = f.read().replace('\n', '')

    context = {
        'job_id': job_id,
        'phylogeneticTreeData': phylogenetic_tree_string,
    }
    return render(request, 'results_gubbins.html', context)


tool = Tool(
    name='gubbins',
    title='Gubbins',
    category='compgen',
    file_only=True,
    args=lambda request: [cores()],
    results=gubbins_results,
    citation=[
        {
            'text': 'Croucher NJ, Page AJ, Connor TR, Delaney AJ, Keane JA, Bentley SD, Parkhill J, Harris SR. 2015. Rapid phylogenetic analysis of large samples of recombinant bacterial whole genome sequences using Gubbins. Nucleic Acids Research 43(3):e15.',
        },
    ],
    example=[('chlamydia_trachomatis_core.aln', 'chlamydia_trachomatis_core.aln')],   # snippy-core alignment of four C. trachomatis genomes
    faq=['Upload a whole-genome multi-FASTA alignment (e.g. from snippy-core).',
         'Click Submit to mask recombinant regions and build a recombination-filtered tree.',
         'Results can be viewed and downloaded on the results page.'],
)
