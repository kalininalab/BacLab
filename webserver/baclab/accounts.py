"""Optional user accounts: who owns a job, who may look at it."""
from django.conf import settings

from .models import get_user_group

# Form fields that are not settings of the analysis
_NOT_SETTINGS = {'csrfmiddlewaretoken', 'type', 'fasta', 'file', 'use_example_data', 'email'}


def owner_fields(request):
    """JobRecord fields that tie a new job to the logged-in user and their group (empty for anonymous users or when accounts are off)."""
    user = getattr(request, 'user', None)
    if not settings.ACCOUNTS_ENABLED or user is None or not user.is_authenticated:
        return {'owner': None, 'group': None, 'private': False}
    return {'owner': user, 'group': get_user_group(user), 'private': request.POST.get('private') in ('on', 'true', '1')}


def submitted_parameters(post, files=None):
    """What was submitted, for the job overview: {"inputs": [file names], "settings": {name: value}}."""
    names = []
    for key in (files or {}):
        names += [f.name for f in (files.getlist(key) if hasattr(files, 'getlist') else [files[key]])]
    values = {key: post.get(key) for key in post.keys() if key not in _NOT_SETTINGS and not key.startswith('csrf')}
    return {'inputs': names, 'settings': {k: str(v)[:200] for k, v in values.items() if v not in (None, '')}}


def can_view_job(user, job):
    """The owner and the members of the owner's group (never anonymous jobs)."""
    if job.owner_id is None:
        return False
    if job.owner_id == user.id:
        return True
    group = get_user_group(user)
    return group is not None and job.group_id == group.id


def job_access_denied(request, job_id):
    """None when the visitor may open this job's results; else an (HTTP status, message). Only private jobs are protected: everything
    else stays reachable by link, as before."""
    from .models import JobRecord
    job = JobRecord.objects.filter(job_id=job_id).select_related('owner').first()
    if job is None or not job.private:
        return None
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return 401, 'This run is private. Please log in to open it.'
    if can_view_job(user, job):
        return None
    return 403, 'This run is private to its owner and their group.'
