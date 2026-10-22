"""Start a new job from an earlier one: run it again, or feed its result files to another tool."""
import os

from django.conf import settings
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from . import db_status, email_policy, limits
from .account_views import accounts_required
from .accounts import can_view_job
from .jobs import create_job
from .models import JobRecord, get_user_group
from .toolkit import registry
from .tool_views import tool_is_on

_NOT_RESULTS = ('CITATION.txt', 'run_parameters.txt', 'METHODS.txt')


def _download_dir(job):
    return os.path.join(settings.DOWNLOAD_DIR, job.job_id)


def _job_for(request, job_id):
    job = get_object_or_404(JobRecord, job_id=job_id)
    if not can_view_job(request.user, job):
        raise Http404("No such job")
    return job


def _check_can_submit(request, tool):
    """An error message, or None."""
    if tool is None or not tool_is_on(tool):
        return "This tool is not available."
    missing = db_status.missing_for_tool(tool)
    if missing:
        return f"This tool cannot run yet: its database is not installed ({'; '.join(missing)})."
    return limits.check(request)


def _owner(request):
    return dict(owner=request.user, group=get_user_group(request.user))


@accounts_required
@require_http_methods(["POST"])
def rerun(request, job_id):
    """Run a job again with the same inputs and settings (while its input files are still kept)."""
    job = _job_for(request, job_id)
    tool = registry.get(job.job_type)
    if tool is None:
        return HttpResponseBadRequest("Re-running is not available for this tool.")
    error = _check_can_submit(request, tool)
    if error:
        return HttpResponseBadRequest(error)

    input_dir = os.path.join(_download_dir(job), 'input')
    fields = (job.parameters or {}).get('fields') or {}
    inputs = []
    if fields:
        for field, names in fields.items():
            inputs += [(field, name, os.path.join(input_dir, name)) for name in names if os.path.isfile(os.path.join(input_dir, name))]
    elif os.path.isdir(input_dir):
        inputs = [('genomes', name, os.path.join(input_dir, name)) for name in sorted(os.listdir(input_dir))]
    accessions = (job.parameters or {}).get('accessions') or []
    if not inputs and not accessions:
        return HttpResponseBadRequest("The input files of this run are no longer kept on the server, so it cannot be re-run. Please submit it again from the tool page.")
    new_id = create_job(tool, inputs, (job.parameters or {}).get('settings', {}), email=request.user.email if not email_policy.check(request.user.email) else '',
                        accessions=accessions, **_owner(request))
    return render(request, 'after_upload.html', {'run_key': new_id, 'website_link': ''})


def result_files(job):
    """Relative paths of the result files of a job (its own input copy excluded)."""
    base = _download_dir(job)
    found = []
    for root, _, names in os.walk(base):
        for name in names:
            relative = os.path.relpath(os.path.join(root, name), base)
            if relative.startswith('input' + os.sep) or name in _NOT_RESULTS:
                continue
            found.append(relative)
    return sorted(found)


def target_tools():
    """Tools that take a set of genome files: they can be fed result files."""
    return [tool for tool in registry.all_tools() if hasattr(tool.form, 'MAX_GENOMES') and tool_is_on(tool)]


@accounts_required
@require_http_methods(["GET", "POST"])
def send_to(request, job_id):
    """Pick result files of a job and start another tool on them."""
    job = _job_for(request, job_id)
    files = result_files(job)
    if request.method == 'POST':
        tool = registry.get(request.POST.get('tool', ''))
        chosen = request.POST.getlist('files')
        error = _check_can_submit(request, tool) if tool else "Unknown tool."
        base = os.path.abspath(_download_dir(job))
        valid = [f for f in chosen if f in files]   # only files that really are results of this job
        if not error and tool and not hasattr(tool.form, 'MAX_GENOMES'):
            error = "This tool cannot take result files as input."
        if not error and not tool.form.MIN_GENOMES <= len(valid) <= tool.form.MAX_GENOMES:
            error = f"{tool.title} needs between {tool.form.MIN_GENOMES} and {tool.form.MAX_GENOMES} files; you chose {len(valid)}."
        if not error and any(not f.lower().endswith(tool.form.ALLOWED_EXTENSIONS) for f in valid):
            error = f"{tool.title} accepts only {', '.join(tool.form.ALLOWED_EXTENSIONS)} files."
        if error:
            return HttpResponseBadRequest(error)
        inputs = [('genomes', os.path.basename(f), os.path.join(base, f)) for f in valid]
        new_id = create_job(tool, inputs, {}, email=request.user.email if not email_policy.check(request.user.email) else '', **_owner(request))
        return render(request, 'after_upload.html', {'run_key': new_id, 'website_link': ''})

    options = []
    for tool in target_tools():
        matching = [f for f in files if f.lower().endswith(tool.form.ALLOWED_EXTENSIONS)]
        if len(matching) >= tool.form.MIN_GENOMES:
            options.append({'tool': tool, 'files': matching[:200], 'min': tool.form.MIN_GENOMES, 'max': tool.form.MAX_GENOMES})
    return render(request, 'send_to.html', {'job': job, 'options': options, 'has_files': bool(files)})
