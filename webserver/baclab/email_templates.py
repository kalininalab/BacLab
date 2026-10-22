"""The messages BacLab e-mails to users, editable in the admin (E-mail messages). Texts that are left empty fall back to the defaults below.

A text may contain {placeholders}; the ones each message knows are in PLACEHOLDERS. Anything else in curly brackets is left as it is."""
import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

SIGNATURE = "Best regards,\nBacLab Team"

PLACEHOLDERS = {
    'finished': {'job_id': 'ID of the job', 'job_name': 'name of the job (its ID when it has no name)', 'tool': 'tool of the job', 'results_url': 'link to the results'},
    'failed': {'job_id': 'ID of the job', 'job_name': 'name of the job (its ID when it has no name)', 'tool': 'tool of the job', 'results_url': 'link to the job',
               'error': 'what went wrong'},
    'expiry': {'job_id': 'ID of the job', 'job_name': 'name of the job (its ID when it has no name)', 'tool': 'tool of the job', 'results_url': 'link to the results',
               'expires': 'date the results are deleted (YYYY-MM-DD)'},
}

DEFAULTS = {
    'finished': ("Job {job_id} Finished",
                 "Your BacLab job {job_id} has finished.\n\nView results: {results_url}\n\n" + SIGNATURE),
    'failed': ("Job {job_id} Failed",
               "Your BacLab job {job_id} failed.\n\nError: {error}\n\nYou can view details at: {results_url}\n\n" + SIGNATURE),
    'expiry': ("Results of {job_name} will be deleted soon",
               "The results of your job {job_name} ({tool}) will be deleted on {expires}.\n\nDownload them here: {results_url}\n"
               "Or keep them longer (my jobs -> details -> Keep N days).\n"),
}

KINDS = {'finished': 'Job finished', 'failed': 'Job failed', 'expiry': 'Results will be deleted soon'}

SAMPLE = {'job_id': 'mlst-sample-1a2b3c', 'job_name': 'Outbreak isolates batch 1', 'tool': 'MLST', 'results_url': '{site}/results/?job_id=mlst-sample-1a2b3c',
          'error': 'An unexpected error occurred during job execution.', 'expires': '2030-01-31'}

_TOKEN = re.compile(r'\{(\w+)\}')


def unknown_placeholders(kind, text):
    return sorted({name for name in _TOKEN.findall(text or '') if name not in PLACEHOLDERS[kind]})


def _fill(kind, text, context):
    return _TOKEN.sub(lambda m: str(context[m.group(1)]) if m.group(1) in PLACEHOLDERS[kind] and m.group(1) in context else m.group(0), text)


def default_texts():
    """The shipped texts as the fields of the EmailMessages model: {'finished_subject': ..., 'finished_body': ..., ...}."""
    return {f'{kind}_{part}': text for kind, pair in DEFAULTS.items() for part, text in zip(('subject', 'body'), pair)}


def stored():
    from .models import EmailMessages
    return EmailMessages.objects.first()


def render(kind, **context):
    """(subject without the site prefix, body) of a message, from the admin's text or the default."""
    row = stored()
    subject, body = DEFAULTS[kind]
    if row is not None:
        subject = getattr(row, f'{kind}_subject').strip() or subject
        body = getattr(row, f'{kind}_body').strip() or body
    return _fill(kind, subject, context).strip(), _fill(kind, body, context).rstrip() + '\n'


def send(kind, to, fail_silently=True, **context):
    """Renders and sends one message. fail_silently: a broken mail server must never break job handling."""
    subject, body = render(kind, **context)
    mail = EmailMultiAlternatives(f"{settings.EMAIL_SUBJECT_PREFIX}{subject}", body, settings.SERVER_EMAIL, [to])
    mail.send(fail_silently=fail_silently)


def send_samples(to, kinds=None):
    """Sends a sample of each message (or of `kinds`) to one address, with the texts as they are now. Raises on mail errors."""
    context = dict(SAMPLE, results_url=SAMPLE['results_url'].replace('{site}', settings.WEBSITE_LINK.rstrip('/')))
    for kind in kinds or KINDS:
        send(kind, to, fail_silently=False, **context)
    return len(kinds or KINDS)
