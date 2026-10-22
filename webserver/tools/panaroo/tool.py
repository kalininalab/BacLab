import os

from django.shortcuts import render

from baclab.toolkit import Tool, cores, matching_file_in_dir


def panaroo_results(request, job_id, download_dir):
    summary_file = matching_file_in_dir(download_dir, 'summary_statistics.txt', '*/summary_statistics.txt')
    summary_content = "Summary not found."
    if summary_file and os.path.exists(summary_file):
        with open(summary_file, 'r') as f:
            summary_content = f.read()
    
    context = {
        'job_id': job_id,
        'summary_content': summary_content,
    }
    return render(request, 'results_panaroo.html', context)


tool = Tool(
    name='panaroo',
    title='Panaroo',
    category='compgen',
    file_only=True,
    exclude=['combined_DNA_CDS.fasta', 'combined_protein_CDS.fasta', 'combined_protein_cdhit_out.txt', 'combined_protein_cdhit_out.txt.clstr', 'pre_filt_graph.gml', 'final_graph.gml', 'gene_data.csv'],   # internal working data, not results
    args=lambda request: [cores(), request.POST.get('clean_mode', 'strict')],
    results=panaroo_results,
    citation=[
        {
            'text': 'Tonkin-Hill G, MacAlasdair N, Ruis C, et al. 2020. Producing polished prokaryotic pangenomes with the Panaroo pipeline. Genome Biology 21:180.',
        },
    ],
    example=[('chlamydia_trachomatis_D_UW3.gff', 'D_UW3.gff'), ('chlamydia_trachomatis_L2_434.gff', 'L2_434.gff'),
             ('chlamydia_trachomatis_L2b_UCH1.gff', 'L2b_UCH1.gff'), ('chlamydia_trachomatis_A_HAR13.gff', 'A_HAR13.gff')],   # Prokka annotations of four C. trachomatis genomes
    faq=['Upload your genome annotations (.gff) produced by Prokka or Bakta.',
         'Select your desired clean mode (Strict, Moderate, Light).',
         'Click Submit to run the pangenome analysis.',
         'You can download the core genome alignment, gene presence/absence matrices, and view summary statistics on the results page.'],
)
