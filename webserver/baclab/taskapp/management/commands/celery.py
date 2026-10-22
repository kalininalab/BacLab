import os
import subprocess

from django.core.management.base import BaseCommand
from django.utils import autoreload


def restart_celery():
    subprocess.run(["pkill", "celery"])
    # Started directly (not through a script baked into the image), so the queues always match the code that is mounted into the container.
    # CELERY_QUEUES: the main worker takes everything, the "light" worker only the quick jobs (see HEAVY_TOOLS in the settings).
    subprocess.run(["celery", "-A", "baclab.taskapp", "worker", "-l", "INFO", "-Q", os.environ.get("CELERY_QUEUES", "celery,fast,heavy")])


class Command(BaseCommand):
    requires_system_checks = []

    def handle(self, *args, **options):
        print('Starting celery worker with autoreload...')
        autoreload.run_with_reloader(restart_celery)
