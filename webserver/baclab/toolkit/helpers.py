"""Small helpers for building a tool's command line."""
import os

from django.conf import settings


def cores():
    """Number of CPU cores a job may use, as a command line argument."""
    return str(settings.CORES_PER_JOB)


def database(name):
    """Path of a shared database / model folder (databases/<name> on the host)."""
    return os.path.join(settings.DATABASES_DIR, name)


def choice(value, allowed, default):
    """A user-supplied option, or the default when it is not one of the allowed values (never trust the form)."""
    return value if value in allowed else default
