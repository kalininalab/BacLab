"""Creating a job for a toolkit tool, whoever asks: the web form, a re-run, "use as input for another tool", the API."""
import os
import shutil
import uuid
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from .models import JobRecord
from .queues import queue_for
from .toolkit.files import sanitize_filename

_SKIP_SETTINGS = {'csrfmiddlewaretoken', 'type', 'fasta', 'file', 'use_example_data', 'email', 'private', 'accessions'}


def _flat(post):
    """A plain {name: value} dict (a Django QueryDict would give lists)."""
    return post.dict() if hasattr(post, 'dict') else dict(post)


def settings_record(post):
    return {k: str(v)[:200] for k, v in _flat(post).items() if k not in _SKIP_SETTINGS and not k.startswith('csrf') and v not in (None, '')}


def create_job(tool, inputs, post, owner=None, group=None, email='', private=False, project=None, accessions=()):
    """Create the job folders, the JobRecord and queue the Celery task. Returns the job id.

    inputs: [(form field, file name, source)] - source is a path, bytes, or an uploaded file (anything with .chunks()).
    post:   dict of the settings (what tool.args reads from request.POST).
    """
    from .views import run_job, website_link, write_parameters   # views imports this module's siblings: import late

    job_id = f"{tool.name}-{uuid.uuid4()}"
    job_path = os.path.join(settings.UPLOAD_DIR, job_id)
    input_path, output_path = os.path.join(job_path, 'input'), os.path.join(job_path, 'output')
    os.makedirs(input_path, exist_ok=True)
    os.makedirs(output_path, exist_ok=True)
    write_parameters(post, output_path)

    saved_files = {}
    for field, name, source in inputs:
        saved = sanitize_filename(name)
        target = os.path.join(input_path, saved)
        if hasattr(source, 'chunks'):
            with open(target, 'wb') as handle:
                for chunk in source.chunks():
                    handle.write(chunk)
        elif isinstance(source, (bytes, str)) and not (isinstance(source, str) and os.path.exists(source)):
            with open(target, 'wb') as handle:
                handle.write(source if isinstance(source, bytes) else source.encode())
        else:
            shutil.copyfile(source, target)
        saved_files.setdefault(field, []).append(saved)

    shutil.copytree(input_path, os.path.join(output_path, 'input'))
    request = SimpleNamespace(POST=_flat(post), FILES={}, saved_files=saved_files)
    job_details = tool.build_job(request, job_id)
    job_details['email'] = email or None
    job_details['results_url'] = f"{website_link}{reverse('baclab:results')}?job_id={job_id}"
    if accessions:
        job_details['accessions'] = list(accessions)

    names = [saved for names in saved_files.values() for saved in names] + list(accessions)
    JobRecord.objects.create(job_id=job_id, job_type=tool.name, status='queued', email=email or None, owner=owner, group=group, private=private,
                             project=project, parameters={'inputs': names, 'settings': settings_record(post), 'fields': saved_files,
                                                          'accessions': list(accessions)})
    # Only after the JobRecord row is committed, or the worker can update a row that does not exist yet
    transaction.on_commit(lambda: run_job.apply_async(args=[job_details], task_id=job_id, queue=queue_for(tool.name)))
    return job_id
