"""JSON API (v1) for scripts and pipelines. Authenticate with `Authorization: Bearer <key>`; keys are created on the "my jobs" page.

    GET  /api/v1/tools/                 tools that take files (name, title, limits, accepted extensions)
    POST /api/v1/jobs/<tool>/submit/    multipart: file field "genomes" (repeat), "accessions", "email", "private" and the tool's settings
    GET  /api/v1/jobs/                  your latest jobs
    GET  /api/v1/jobs/<id>/             status, key findings
    GET  /api/v1/jobs/<id>/download/    the results zip
"""
import functools
import os

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import summaries
from .accounts import can_view_job
from .models import ApiToken, JobRecord, get_user_group
from .toolkit import registry
from .tool_views import submit, tool_is_on


def _json_error(message, status):
    return JsonResponse({'error': message}, status=status)


def token_required(view):
    @csrf_exempt
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (settings.ACCOUNTS_ENABLED and settings.API_ENABLED):
            return _json_error('The API is not enabled on this server.', 404)
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if not header.startswith('Bearer '):
            return _json_error('Send your API key as "Authorization: Bearer <key>".', 401)
        token = ApiToken.objects.filter(key_hash=ApiToken.hash_key(header[7:].strip())).select_related('user').first()
        if token is None or not token.user.is_active:
            return _json_error('Invalid API key.', 401)
        token.last_used = timezone.now()
        token.save(update_fields=['last_used'])
        request.user = token.user
        return view(request, *args, **kwargs)
    return wrapper


def _job_json(request, job):
    data = {'job_id': job.job_id, 'tool': job.job_type, 'status': job.status, 'label': job.label, 'private': job.private,
            'queued_at': job.queued_at.isoformat(), 'finished_at': job.finished_at.isoformat() if job.finished_at else None,
            'error': job.error_message or None, 'results_url': request.build_absolute_uri(f"{reverse('baclab:results')}?job_id={job.job_id}"),
            'download_url': request.build_absolute_uri(reverse('baclab:api_download', args=[job.job_id])) if job.status == 'finished' else None}
    if job.status == 'finished':
        data['summary'] = summaries.ensure_summary(job) or None
    return data


@token_required
@require_http_methods(["GET"])
def tools(request):
    rows = []
    for tool in registry.all_tools():
        if hasattr(tool.form, 'MAX_GENOMES') and tool_is_on(tool):
            rows.append({'name': tool.name, 'title': tool.title, 'category': tool.category, 'description': tool.description,
                         'min_files': tool.form.MIN_GENOMES, 'max_files': tool.form.MAX_GENOMES, 'extensions': list(tool.form.ALLOWED_EXTENSIONS)})
    return JsonResponse({'tools': rows})


@token_required
@require_http_methods(["POST"])
def create_job_view(request, tool_name):
    tool = registry.get(tool_name)
    if tool is None or not tool_is_on(tool) or not hasattr(tool.form, 'MAX_GENOMES'):
        return _json_error('Unknown tool, or a tool that cannot be used through the API.', 404)
    # the API takes the genome files under any field name
    request.FILES.setlist('genomes', [f for key in list(request.FILES) for f in request.FILES.getlist(key)])
    owner = {'owner': request.user, 'group': get_user_group(request.user), 'private': request.POST.get('private') in ('on', 'true', '1')}
    job_id, error = submit(request, tool, owner)
    if error:
        return _json_error(error, 400)
    job = JobRecord.objects.get(job_id=job_id)
    return JsonResponse(_job_json(request, job), status=201)


@token_required
@require_http_methods(["GET"])
def job_list(request):
    jobs = JobRecord.objects.filter(owner=request.user)[:100]
    return JsonResponse({'jobs': [_job_json(request, job) for job in jobs]})


def _visible_job(request, job_id):
    job = JobRecord.objects.filter(job_id=job_id).first()
    if job is None or not can_view_job(request.user, job):
        raise Http404
    return job


@token_required
@require_http_methods(["GET"])
def job_status(request, job_id):
    try:
        return JsonResponse(_job_json(request, _visible_job(request, job_id)))
    except Http404:
        return _json_error('No such job.', 404)


@token_required
@require_http_methods(["GET"])
def job_download(request, job_id):
    try:
        job = _visible_job(request, job_id)
    except Http404:
        return _json_error('No such job.', 404)
    path = os.path.join(settings.RESULTS_DIR, f'{job.job_id}.zip')
    if job.status != 'finished' or not os.path.exists(path):
        return _json_error('The results are not available (job not finished, or deleted).', 404)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=f'{job.job_id}.zip')
