
import os
from celery import Celery
from django.apps import apps, AppConfig
from django.conf import settings


if not settings.configured:
    # set the default Django settings module for the 'celery' program.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')  # pragma: no cover


app = Celery('baclab')


class CeleryAppConfig(AppConfig):
    name = 'baclab.taskapp'
    verbose_name = 'Celery Config'

    def ready(self):
        # Using a string here means the worker will not have to
        # pickle the object when using Windows.
        # - namespace='CELERY' means all celery-related configuration keys
        #   should have a `CELERY_` prefix.
        app.config_from_object('django.conf:settings', namespace='CELERY')
        installed_apps = [app_config.name for app_config in apps.get_app_configs()]
        app.autodiscover_tasks(lambda: installed_apps, force=True)

        from celery.schedules import crontab
        app.conf.beat_schedule = {
            'clean_old_results_every_day': {
                'task': 'baclab.tasks.clean_old_results',
                'schedule': crontab(hour=0, minute=0),
            },
            'check_system_every_hour': {
                'task': 'baclab.tasks.check_system',
                'schedule': crontab(minute=7),
            },
            'warn_expiring_results_every_day': {
                'task': 'baclab.tasks.warn_expiring_results',
                'schedule': crontab(hour=8, minute=30),
            },
        }


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')  # pragma: no cover
