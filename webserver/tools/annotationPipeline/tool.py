import os
import shutil

import zipfile

from django.conf import settings
from django.shortcuts import render

from baclab.tools.antismash import AntismashTool
from baclab.tools.bakta import BaktaTool
from baclab.tools.converter import GbkConverterTool
from baclab.tools.prokka import ProkkaTool
from baclab.toolkit import Tool


def build_job(request, job_id):
    """The pipeline has no script of its own: the job says which of its steps to run."""
    job_path = os.path.join(settings.UPLOAD_DIR, job_id)
    return {
        'jobId': job_id,
        'command': [''],
        'uploadDir': os.path.join(job_path, 'input'),
        'outputDir': os.path.join(job_path, 'output'),
        'resultsDir': os.path.join(settings.DOWNLOAD_DIR, job_id),
        'options': {
            'bakta': 'bakta_checkbox' in request.POST,
            'antismash': 'antismash_checkbox' in request.POST,
            'prokka': 'prokka_checkbox' in request.POST,
        },
    }


def run(ctx):
    """Convert GenBank input if needed, then run the chosen annotation steps one after the other."""
    job_id, output_dir, job_options = ctx['job_id'], ctx['output_dir'], ctx['job_options']
    input_dir = os.path.join(settings.UPLOAD_DIR, job_id, 'input')
    GbkConverterTool(job_id=job_id, input_dir=input_dir, output_dir=output_dir).convert_if_needed()
    for key, step in (('bakta', BaktaTool), ('antismash', AntismashTool), ('prokka', ProkkaTool)):
        if job_options.get(key):
            step(job_id=job_id, input_dir=input_dir, output_dir=output_dir).execute({})


def post_process(ctx):
    """The results are large: move them into the downloads folder instead of copying them."""
    os.makedirs(ctx['downloads_dir'], exist_ok=True)
    for entry in os.listdir(ctx['output_dir']):
        if entry != 'input':
            shutil.move(os.path.join(ctx['output_dir'], entry), os.path.join(ctx['downloads_dir'], entry))


def annotation_results(request, job_id, download_dir):
    """The annotation pipeline's outputs are many large files per genome and tool: list them (the download has them all)."""
    files = []
    archive_path = os.path.join(settings.RESULTS_DIR, f"{job_id}.zip")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            files = [{'name': i.filename, 'size': i.file_size} for i in archive.infolist()
                     if not i.filename.endswith('/') and not i.filename.startswith('input/') and i.filename not in ('CITATION.txt', 'run_parameters.txt')]
    except (OSError, zipfile.BadZipFile):
        pass
    return render(request, 'results_custom_files.html', {'job_id': job_id, 'files': sorted(files, key=lambda f: f['name'])})



tool = Tool(
    name='annotationPipeline',
    title='Annotation Pipeline (Prokka, Bakta, antiSMASH)',
    category='annot',
    file_only=True,
    requires_databases=False,   # each step needs its own database; the page lists them
    build_job=build_job,
    run=run,
    post_process=post_process,
    results=annotation_results,
    citation=[
        {
            'text': 'Schwengers O, Jelonek L, Dieckmann MA, Beyvers S, Blom J, Goesmann A. 2021. Bakta: rapid and standardized annotation of bacterial genomes via alignment-free sequence identification. Microbial Genomics 7(11).',
            'url': 'https://github.com/oschwengers/bakta',
        },
        {
            'text': 'Seemann T. 2014. Prokka: rapid prokaryotic genome annotation. Bioinformatics 30(14):2068-2069.',
            'url': 'https://github.com/tseemann/prokka',
        },
        {
            'text': 'Blin K, Shaw S, Augustijn HE, et al. 2023. antiSMASH 7.0: new and improved predictions for detection, regulation, chemical structures and visualisation. Nucleic Acids Research 51(W1):W46-W50.',
            'url': 'https://antismash.secondarymetabolites.org',
        },
    ],
    example=[('annotationPipeline_example.fasta', 'annotationPipeline_example.fasta')],
    example_post={'prokka_checkbox': 'on'},   # the example run only needs one of the three steps

)
