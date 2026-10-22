import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import path

from baclab.accounts import job_access_denied
from baclab.toolkit import Tool, cores


def fastp_results(request, job_id, download_dir):
    context = {
        'job_id': job_id,
        'download_dir': download_dir
    }
    return render(request, 'results_fastp.html', context)


def serve_fastp_file(request, job_id, filename):
    if any(x in filename for x in ['..', '\\']) or any(x in job_id for x in ['..','/','\\']):
        return HttpResponseBadRequest("Invalid path")
    denied = job_access_denied(request, job_id)
    if denied:
        return HttpResponse(denied[1], status=denied[0])
    downloads_path = os.path.join(settings.DOWNLOAD_DIR, job_id)
    abs_path = os.path.join(downloads_path, filename)
    if not abs_path.endswith(".html"):
        return HttpResponseBadRequest("Only HTML files allowed")
    if not abs_path.startswith(os.path.abspath(downloads_path)):
        return HttpResponseBadRequest("Out of scope")
    if not os.path.exists(abs_path):
        raise Http404("Report not found")
    resp = FileResponse(open(abs_path, "rb"))
    resp["X-Frame-Options"] = "SAMEORIGIN"
    return resp


tool = Tool(
    name='fastp',
    title='fastp',
    category='qc',
    file_only=True,
    args=lambda request: [cores()],
    results=fastp_results,
    urls=[path('fastp/file/<str:job_id>/<str:filename>', serve_fastp_file, name='fastp_file')],
    citation=[
        {
            'text': 'Chen S, Zhou Y, Chen Y, Gu J. 2018. fastp: an ultra-fast all-in-one FASTQ preprocessor. Bioinformatics 34(17):i884-i890.',
        },
    ],
    example=[('ecoli_1K_1.fq.gz', 'ecoli_1K_1.fq.gz'),
             ('ecoli_1K_2.fq.gz', 'ecoli_1K_2.fq.gz')],
    faq=['Upload your raw sequencing reads (FASTQ files).',
         'Click Submit to perform read quality control and filtering.',
         'Filtered reads and HTML/JSON reports can be downloaded on the results page.'],
)
