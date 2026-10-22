import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import path

from baclab.accounts import job_access_denied
from baclab.toolkit import Tool, cores


def quast_results(request, job_id, download_dir):
    html_files = []
    for root, dirs, files in os.walk(download_dir):
        for file in files:
            if file.endswith('.html'):
                rel_dir = os.path.relpath(root, download_dir)
                rel_file = file if rel_dir == '.' else os.path.join(rel_dir, file).replace('\\', '/')
                html_files.append(rel_file)
    
    html_files.sort(key=lambda x: (x != 'report.html', x))
    current_quast_file = html_files[0] if html_files else ''
    
    context = {
        'job_id': job_id,
        'download_dir': download_dir,
        'quast_html_files': html_files,
        'current_quast_file': current_quast_file,
    }
    return render(request, 'results_quast.html', context)


def serve_quast_file(request, job_id, filepath):
    if any(x in filepath for x in ['..', '\\']) or any(x in job_id for x in ['..','/','\\']):
        return HttpResponseBadRequest("Invalid path")
    denied = job_access_denied(request, job_id)
    if denied:
        return HttpResponse(denied[1], status=denied[0])
    downloads_path = os.path.join(settings.DOWNLOAD_DIR, job_id)
    abs_path = os.path.join(downloads_path, filepath)
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
    name='quast',
    title='QUAST',
    category='qc',
    file_only=True,
    args=lambda request: [cores()],
    results=quast_results,
    urls=[path('quast/file/<str:job_id>/<path:filepath>', serve_quast_file, name='quast_file')],
    citation=[
        {
            'text': 'Gurevich A, Saveliev V, Vyahhi N, Tesler G. 2013. QUAST: quality assessment tool for genome assemblies. Bioinformatics 29(8):1072-1075.',
        },
    ],
    example=[('quast_example.fasta', 'quast_example.fasta')],
    faq=['Upload your assembled contigs (FASTA files).',
         'Click Submit to evaluate the assembly quality.',
         'Metrics like N50, L50, and GC content will be calculated and provided in a report.'],
)
