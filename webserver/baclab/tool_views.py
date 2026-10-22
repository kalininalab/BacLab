"""Pages shared by the tools that describe themselves with a toolkit Tool (tools/<name>/tool.py folders and the
tools added in the admin): submission, example data, report files. Results are shown by views.results."""
import io
import os
import shutil
import zipfile
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from . import db_status, email_policy, limits, tool_catalog, tool_versions
from .queues import queue_for
from . import ncbi
from .accounts import job_access_denied, owner_fields
from .jobs import create_job
from .models import JobRecord
from .toolkit import registry
from .views import run_job, website_link


def _unsafe_path(path):
    return path.startswith(('/', '\\')) or '..' in path.replace('\\', '/').split('/')


def missing_databases(tool):
    """Titles of the required databases that are not installed - empty for tools that also work without (they have modes that need none)."""
    return db_status.missing_for_tool(tool) if tool.requires_databases else []


def tool_is_on(tool):
    """Is the tool switched on (hand-written pages stay reachable by URL when switched off; these do not)."""
    if tool.source == 'custom':
        return getattr(tool, 'admin_enabled', False)
    return tool_catalog.is_enabled(tool.settings_key)


@require_http_methods(["GET", "POST"])
def custom_tool(request, tool_name):
    """Entry point of the tools added in the admin: /custom/<name>/."""
    tool = registry.get(tool_name)
    if tool is None or tool.source != 'custom':
        raise Http404("No such tool.")
    return handle_job(request, tool_name)


@require_http_methods(["GET", "POST"])
def handle_job(request, job_type):
    """Shows a tool's submission page and, on POST, creates the job (files, database record, Celery task)."""
    tool = registry.get(job_type)
    if tool is None or not tool_is_on(tool):
        raise Http404("This tool is not available.")

    if request.method == 'GET':
        context = {'job_type': job_type, 'tool': tool, 'citation': tool.citation, 'missing_databases': missing_databases(tool), 'tool_version': tool_versions.version_of(job_type),
                   **tool.page_context()}
        context['max_files'] = getattr(tool.form, 'MAX_GENOMES', None)
        context['accepts_accessions'] = context['max_files'] is not None
        return render(request, tool.template, context)

    owner = owner_fields(request)
    job_id, error = submit(request, tool, owner)
    if error:
        return HttpResponseBadRequest(error)
    return render(request, 'after_upload.html', {'run_key': job_id, 'website_link': website_link})


def submit(request, tool, owner):
    """Validate a submission (web form or API call) and create the job. Returns (job_id, None) or (None, error message).
    owner: {'owner': user or None, 'group': group or None, 'private': bool}."""
    missing = missing_databases(tool)
    if missing:   # fail before queueing, with a message that says what to do
        return None, (f"This tool cannot run yet: the database is not installed on this server ({'; '.join(missing)}). "
                      "Please ask the administrator to install it (baclab db install).")

    if tool.file_only and request.POST.get('type') == 'fasta' and request.POST.get('fasta'):
        return None, 'This tool only accepts file uploads - its input is too large to submit as pasted text.'

    for check in (email_policy.check(request.POST.get('email')), limits.check(request)):
        if check:
            return None, check

    accessions, invalid = ncbi.parse_accessions(request.POST.get('accessions'))
    if invalid:
        return None, f"These are not NCBI assembly accessions (expected GCF_/GCA_ followed by 9 digits and a version): {', '.join(invalid[:5])}"
    if accessions and not hasattr(tool.form, 'MAX_GENOMES'):
        return None, "This tool does not take NCBI accessions; please upload files."
    if len(accessions) > ncbi.MAX_ACCESSIONS:
        return None, f"At most {ncbi.MAX_ACCESSIONS} accessions at once."

    use_example = str(request.POST.get('use_example_data', '')).lower() in ('true', '1') and bool(tool.example)
    if accessions:
        uploaded = request.FILES.getlist('genomes')
        total = len(uploaded) + len(accessions)
        if total < tool.form.MIN_GENOMES:
            return None, f"You must provide at least {tool.form.MIN_GENOMES} genomes (files and accessions together)."
        if total > tool.form.MAX_GENOMES:
            return None, f"You can provide at most {tool.form.MAX_GENOMES} genomes (files and accessions together)."
        if any(not f.name.lower().endswith(tool.form.ALLOWED_EXTENSIONS) for f in uploaded):
            return None, f"Allowed file extensions: {', '.join(tool.form.ALLOWED_EXTENSIONS)}."
    else:
        form = tool.form(request.POST, request.FILES, **tool.form_kwargs)
        if not use_example and not form.is_valid():
            return None, '; '.join(error for errors in form.errors.values() for error in errors) or 'Missing or invalid input data'

    inputs = []
    if use_example:
        inputs = [('example', name, path) for path, name in tool.example_files()]
    else:
        if request.POST.get('type') == 'fasta' and request.POST.get('fasta'):
            inputs.append(('fasta', 'user_input.fasta', request.POST['fasta']))
        # getlist() so a `multiple` file input has every selected file saved, not just the first
        for file_key in request.FILES:
            inputs += [(file_key, f.name, f) for f in request.FILES.getlist(file_key)]

    job_id = create_job(tool, inputs, request.POST, owner=owner['owner'], group=owner['group'], private=owner['private'],
                        email=request.POST.get('email', '').strip(), accessions=accessions)
    return job_id, None


def download_example_data(request, job_type):
    """Serves the bundled example data for a tool's "Download Example Data" button."""
    tool = registry.get(job_type)
    if tool is None or not tool.example:
        raise Http404("No example data available for this tool.")

    existing = tool.example_files()
    if not existing:
        raise Http404("Example data file not found.")

    if len(existing) == 1:
        source_path, dest_name = existing[0]
        return FileResponse(open(source_path, 'rb'), as_attachment=True, filename=dest_name)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for source_path, dest_name in existing:
            zip_file.write(source_path, dest_name)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f"{job_type}_example_data.zip")


def example_job_id(tool):
    return f"{tool.name}-EXAMPLE"


def example_exists(tool):
    """Has the example of this tool been started (or finished) before?"""
    job_id = example_job_id(tool)
    return (os.path.exists(os.path.join(settings.RESULTS_DIR, f"{job_id}.zip")) or os.path.isdir(os.path.join(settings.DOWNLOAD_DIR, job_id))
            or os.path.isdir(os.path.join(settings.UPLOAD_DIR, job_id, 'input')))


def start_example(tool):
    """Queue the example job of a tool under its fixed id (<name>-EXAMPLE) unless it exists already. Returns (job id, started)."""
    job_id = example_job_id(tool)
    if example_exists(tool):
        return job_id, False
    results_url = f"{reverse('baclab:results')}?job_id={job_id}"
    input_path = os.path.join(settings.UPLOAD_DIR, job_id, 'input')
    output_path = os.path.join(settings.UPLOAD_DIR, job_id, 'output')
    os.makedirs(input_path, exist_ok=True)
    os.makedirs(output_path, exist_ok=True)
    for source_path, dest_name in tool.example_files():
        shutil.copyfile(source_path, os.path.join(input_path, dest_name))
    shutil.copytree(input_path, os.path.join(output_path, 'input'))

    fake_request = SimpleNamespace(FILES={}, POST=dict(tool.example_post), saved_files={})
    job_details = tool.build_job(fake_request, job_id)
    job_details['email'] = None
    job_details['results_url'] = f"{website_link}{results_url}"

    JobRecord.objects.update_or_create(job_id=job_id, defaults={'job_type': tool.name, 'status': 'queued', 'email': None})
    transaction.on_commit(lambda: run_job.apply_async(args=[job_details], task_id=job_id, queue=queue_for(tool.name)))
    return job_id, True


def example_results(request, job_type):
    """"View Example Results" button target: runs a tool once against its bundled example data under a fixed job id
    (<job_type>-EXAMPLE) and redirects to the normal results page. Once that first run has produced results, every
    later click just redirects straight there - no re-run, no waiting.
    `manage.py prerun_examples` prepares all of them at once."""
    tool = registry.get(job_type)
    if tool is None or not tool.example or not tool_is_on(tool):
        raise Http404("No example available for this tool.")
    problem = tool.example_check() if tool.example_check and not example_exists(tool) else None
    if problem:
        return HttpResponseBadRequest(problem)
    missing = missing_databases(tool) if not example_exists(tool) else []
    if missing:
        return HttpResponseBadRequest(f"The example of this tool needs a database that is not installed on this server yet ({'; '.join(missing)}). "
                                      "Please ask the administrator to install it (baclab db install).")
    job_id, _ = start_example(tool)
    return HttpResponseRedirect(f"{reverse('baclab:results')}?job_id={job_id}")


def serve_tool_report_file(request, job_id, filepath):
    """Serves a file from a job's downloads dir for the HTML-report iframe viewer and the plots of the results pages."""
    if _unsafe_path(job_id) or _unsafe_path(filepath):
        return HttpResponseBadRequest("Invalid path")
    denied = job_access_denied(request, job_id)
    if denied:
        return HttpResponse(denied[1], status=denied[0])

    downloads_path = os.path.abspath(os.path.join(settings.DOWNLOAD_DIR, job_id))
    abs_path = os.path.normpath(os.path.join(downloads_path, filepath))

    if not abs_path.startswith(downloads_path + os.sep):
        return HttpResponseBadRequest("Out of scope")

    if not os.path.isfile(abs_path):
        raise Http404("File not found")

    allowed_extensions = ['.html', '.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.json', '.txt', '.tsv', '.csv', '.pdf', '.gbff', '.db']
    if not any(abs_path.lower().endswith(ext) for ext in allowed_extensions):
        return HttpResponseBadRequest("File type not allowed")

    response = FileResponse(open(abs_path, 'rb'))
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
