"""Optional user space: log in, see your own jobs and those of your group, name runs, keep results longer."""
import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import Http404, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from . import email_policy
from . import methods, summaries
from .accounts import can_view_job
from .models import ApiToken, JobRecord, Project, get_user_group

JOBS_PAGE_LIMIT = 500
STATUS_ORDER = ["running", "queued", "failed", "finished"]   # active / attention-needing first
GROUP_BY_CHOICES = [("date", "Date"), ("tool", "Tool"), ("status", "Status"), ("none", "No grouping")]
GROUP_TAB_GROUP_BY_CHOICES = [("user", "User")] + GROUP_BY_CHOICES   # only meaningful for other members' jobs


def accounts_required(view):
    """404 when accounts are switched off; otherwise the user has to be logged in."""
    @login_required
    def wrapper(request, *args, **kwargs):
        return view(request, *args, **kwargs)

    def checked(request, *args, **kwargs):
        if not settings.ACCOUNTS_ENABLED:
            raise Http404("User accounts are not enabled on this server.")
        return wrapper(request, *args, **kwargs)
    checked.__name__ = view.__name__
    checked.__doc__ = view.__doc__
    return checked


def _date_bucket(job, now):
    age = now - job.queued_at
    if age < timedelta(days=1):
        return "Today"
    if age < timedelta(days=7):
        return "Last 7 days"
    if age < timedelta(days=30):
        return "Last 30 days"
    return "Older"


def _group_jobs(jobs, group_by):
    """[(section title, jobs)] for the my-jobs page. `jobs` is newest first."""
    if group_by == "none":
        return [("", jobs)]
    now = timezone.now()
    buckets = {}
    for job in jobs:
        key = {"date": lambda: _date_bucket(job, now), "tool": lambda: job.tool_label, "status": lambda: job.get_status_display(),
               "user": lambda: job.owner.username if job.owner else "unknown"}[group_by]()
        buckets.setdefault(key, []).append(job)
    if group_by == "date":
        return [(key, buckets[key]) for key in ["Today", "Last 7 days", "Last 30 days", "Older"] if key in buckets]
    if group_by == "status":
        labels = dict(JobRecord.STATUS_CHOICES)
        return [(labels[status], buckets[labels[status]]) for status in STATUS_ORDER if labels[status] in buckets]
    return sorted(buckets.items(), key=lambda item: item[0].lower())


@accounts_required
def my_jobs(request):
    """The logged-in user's jobs (or, on the group tab, the other members' jobs), filterable and groupable."""
    group = get_user_group(request.user)
    scope = request.GET.get('scope', 'mine')
    if scope != 'group' or not group:
        scope = 'mine'
    group_by_choices = GROUP_TAB_GROUP_BY_CHOICES if scope == 'group' else GROUP_BY_CHOICES
    group_by = request.GET.get('group_by', 'date')
    if group_by not in dict(group_by_choices):
        group_by = 'date'
    status = request.GET.get('status', '')
    if status not in dict(JobRecord.STATUS_CHOICES):
        status = ''
    query = request.GET.get('q', '').strip()

    project_id = request.GET.get('project', '')
    if scope == 'group':
        all_jobs = JobRecord.objects.filter(group=group).exclude(owner=request.user).select_related('owner')
    else:
        all_jobs = JobRecord.objects.filter(owner=request.user)
        if project_id.isdigit():
            all_jobs = all_jobs.filter(project_id=int(project_id))
    all_jobs = list(all_jobs[:JOBS_PAGE_LIMIT])
    summaries.ensure_summaries(all_jobs)
    status_counts = {code: sum(1 for job in all_jobs if job.status == code) for code, _ in JobRecord.STATUS_CHOICES}

    jobs = all_jobs
    if status:
        jobs = [job for job in jobs if job.status == status]
    if query:
        needle = query.lower()
        jobs = [job for job in jobs if needle in " ".join([job.job_id, job.label, job.tool_label, job.owner.username if job.owner else ""]).lower()]

    return render(request, 'my_jobs.html', {
        'group': group, 'scope': scope, 'group_by': group_by, 'group_by_choices': group_by_choices,
        'status': status, 'status_choices': JobRecord.STATUS_CHOICES, 'status_counts': status_counts,
        'total_jobs': len(all_jobs), 'query': query, 'sections': _group_jobs(jobs, group_by), 'shown_jobs': len(jobs),
        'has_active_jobs': any(job.is_active for job in jobs), 'default_retention': settings.MAX_RESULTS_AGE,
        'show_owner': scope == 'group', 'limit_reached': len(all_jobs) >= JOBS_PAGE_LIMIT,
        'projects': Project.objects.filter(owner=request.user), 'project_id': project_id,
    })


def _input_files_on_disk(job):
    """Input file names of a job submitted before inputs were recorded on the JobRecord."""
    for base in (settings.DOWNLOAD_DIR, settings.UPLOAD_DIR):
        input_dir = os.path.join(base, job.job_id, 'input')
        if os.path.isdir(input_dir):
            return sorted(os.listdir(input_dir))
    return []


@accounts_required
def job_detail(request, job_id):
    """Overview of one run: what was analysed, how it went, links to the results."""
    job = get_object_or_404(JobRecord, job_id=job_id)
    if not can_view_job(request.user, job):
        raise Http404("No such job")
    summaries.ensure_summary(job)
    return render(request, 'job_detail.html', {
        'job': job, 'summary': job.summary or None, 'input_files': job.parameters.get('inputs') or _input_files_on_disk(job),
        'projects': Project.objects.filter(owner=request.user), 'methods': methods.methods_text(job) if job.status == 'finished' else '', 'is_owner': job.owner_id == request.user.id, 'retention_choices': settings.RETENTION_CHOICES, 'active': job.is_active,
    })


@accounts_required
@require_http_methods(["POST"])
def set_label(request, job_id):
    """Lets a job's owner name a run."""
    job = get_object_or_404(JobRecord, job_id=job_id, owner=request.user)
    job.label = request.POST.get('label', '').strip()[:JobRecord._meta.get_field('label').max_length]
    job.save(update_fields=['label'])
    return HttpResponseRedirect(reverse('baclab:job_detail', args=[job.job_id]))


@accounts_required
@require_http_methods(["POST"])
def set_retention(request, job_id):
    """Lets a job's owner choose how many days its results are kept (one of RETENTION_CHOICES)."""
    job = get_object_or_404(JobRecord, job_id=job_id, owner=request.user)
    try:
        days = int(request.POST.get('days', ''))
    except ValueError:
        return HttpResponseBadRequest('Invalid retention period')
    if days not in settings.RETENTION_CHOICES:
        return HttpResponseBadRequest('Invalid retention period')
    job.retention_days = None if days == settings.MAX_RESULTS_AGE else days   # the default keeps following MAX_RESULTS_AGE
    job.save(update_fields=['retention_days'])
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('baclab:my_jobs')
    return HttpResponseRedirect(next_url)


@require_http_methods(["GET", "POST"])
def signup(request):
    """Self-service account creation, only when ALLOW_SIGNUP is on. An administrator puts the new user into a group."""
    if not (settings.ACCOUNTS_ENABLED and settings.ALLOW_SIGNUP):
        raise Http404("Sign-up is not enabled on this server.")
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return HttpResponseRedirect(reverse('baclab:my_jobs'))
    return render(request, 'registration/signup.html', {'form': form})


@accounts_required
@require_http_methods(["POST"])
def set_email(request):
    """The notification address of the account: pre-filled on the tool pages."""
    from django.contrib import messages
    address = request.POST.get('email', '').strip()
    error = email_policy.check(address)
    if error:
        messages.error(request, error)
    else:
        request.user.email = address
        request.user.save(update_fields=['email'])
        messages.success(request, 'Notification e-mail saved.' if address else 'Notification e-mail removed.')
    return HttpResponseRedirect(reverse('baclab:my_jobs'))


@accounts_required
@require_http_methods(["POST"])
def set_private(request, job_id):
    """Lets a job's owner make a run private (results only open for the owner and the group) or public again."""
    job = get_object_or_404(JobRecord, job_id=job_id, owner=request.user)
    job.private = request.POST.get('private') == '1'
    job.save(update_fields=['private'])
    return HttpResponseRedirect(reverse('baclab:job_detail', args=[job.job_id]))


@accounts_required
def job_methods(request, job_id):
    """The methods paragraph of a run as a text file."""
    from django.http import HttpResponse
    job = get_object_or_404(JobRecord, job_id=job_id)
    if not can_view_job(request.user, job):
        raise Http404("No such job")
    response = HttpResponse(methods.methods_text(job), content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{job.job_id}-methods.txt"'
    return response


@accounts_required
@require_http_methods(["POST"])
def set_project(request, job_id):
    """Put a run into one of the owner's projects (or a new one, named in the form); empty = no project."""
    job = get_object_or_404(JobRecord, job_id=job_id, owner=request.user)
    new_name = request.POST.get('new_project', '').strip()[:100]
    if new_name:
        project, _ = Project.objects.get_or_create(owner=request.user, name=new_name)
    elif request.POST.get('project', '').isdigit():
        project = get_object_or_404(Project, pk=int(request.POST['project']), owner=request.user)
    else:
        project = None
    job.project = project
    job.save(update_fields=['project'])
    return HttpResponseRedirect(reverse('baclab:job_detail', args=[job.job_id]))


def _project_or_404(request, project_id):
    return get_object_or_404(Project, pk=project_id, owner=request.user)


@accounts_required
def project_detail(request, project_id):
    """All runs of a project side by side: their key findings in one table (CSV with ?format=csv)."""
    import csv
    from django.http import HttpResponse
    project = _project_or_404(request, project_id)
    jobs = list(project.jobs.order_by('queued_at'))
    summaries.ensure_summaries(jobs)
    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{project.name}-overview.csv"'
        writer = csv.writer(response)
        writer.writerow(['job_id', 'name', 'tool', 'status', 'submitted', 'headline'])
        for job in jobs:
            writer.writerow([job.job_id, job.label, job.tool_label, job.status, job.queued_at.strftime('%Y-%m-%d %H:%M'), (job.summary or {}).get('headline', '')])
        return response
    return render(request, 'project_detail.html', {'project': project, 'jobs': jobs})


@accounts_required
def project_download(request, project_id):
    """One zip with the results archives of all finished runs of the project."""
    import tempfile
    import zipfile
    from django.http import FileResponse
    project = _project_or_404(request, project_id)
    handle = tempfile.TemporaryFile()
    with zipfile.ZipFile(handle, 'w', zipfile.ZIP_STORED) as archive:
        for job in project.jobs.filter(status='finished'):
            path = os.path.join(settings.RESULTS_DIR, f'{job.job_id}.zip')
            if os.path.exists(path):
                archive.write(path, f'{job.label or job.job_id}-{job.job_id}.zip' if job.label else f'{job.job_id}.zip')
    handle.seek(0)
    return FileResponse(handle, as_attachment=True, filename=f'{project.name}-results.zip')


@accounts_required
@require_http_methods(["POST"])
def project_delete(request, project_id):
    """Delete the project folder only; its runs stay (without a project)."""
    _project_or_404(request, project_id).delete()
    return HttpResponseRedirect(reverse('baclab:my_jobs'))


@accounts_required
@require_http_methods(["GET", "POST"])
def api_keys(request):
    """Create and revoke the user's API keys; a new key is shown once."""
    if not settings.API_ENABLED:
        raise Http404("The API is not enabled on this server.")
    new_key = None
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()[:64] or 'my key'
        _, new_key = ApiToken.create_for(request.user, name)
    return render(request, 'api_keys.html', {'tokens': ApiToken.objects.filter(user=request.user), 'new_key': new_key,
                                             'site': request.build_absolute_uri('/').rstrip('/')})


@accounts_required
@require_http_methods(["POST"])
def api_key_delete(request, token_id):
    get_object_or_404(ApiToken, pk=token_id, user=request.user).delete()
    return HttpResponseRedirect(reverse('baclab:api_keys'))
