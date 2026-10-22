import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import path

from baclab.accounts import job_access_denied
from baclab.toolkit import Tool, cores


def multiqc_results(request, job_id, download_dir):
    report_path = os.path.join(download_dir, 'multiqc_report.html')
    context = {
        'job_id': job_id,
        'report_available': os.path.exists(report_path),
    }
    return render(request, 'results_multiqc.html', context)


def serve_multiqc_file(request, job_id, filename):
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
    name='multiqc',
    title='MultiQC',
    category='qc',
    file_only=True,
    exclude=['**/multiqc_report_data'],   # internal working data, not results
    args=lambda request: [cores()],
    results=multiqc_results,
    urls=[path('multiqc/file/<str:job_id>/<str:filename>', serve_multiqc_file, name='multiqc_file')],
    citation=[
        {
            'text': 'Ewels P, Magnusson M, Lundin S, Kaller M. 2016. MultiQC: summarize analysis results for multiple tools and samples in a single report. Bioinformatics 32(19):3047-3048.',
            'url': 'https://multiqc.info',
        },
    ],
    example=[('multiqc_example.zip', 'multiqc_example.zip')],
    faq=['Upload a .zip archive of report/log files from previous fastp, QUAST, CheckM, etc. jobs.',
         'Click Submit to get a single combined HTML QC summary across all of them.',
         'Results can be viewed and downloaded on the results page.'],
)
