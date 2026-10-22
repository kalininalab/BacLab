"""Which Celery queue a job goes to (see HEAVY_TOOLS in the settings)."""
from django.conf import settings


def queue_for(job_type):
    return 'heavy' if job_type in settings.HEAVY_TOOLS else 'fast'
