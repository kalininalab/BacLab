"""Fair-share limits on jobs that are queued or running at the same time (admin -> Job limits)."""
from .models import JobRecord, SiteLimits, get_user_group

ACTIVE = ('queued', 'running')


def check(request):
    """None when the visitor may submit another job, else a message. 0 means no limit."""
    from django.conf import settings
    limits = SiteLimits.objects.first()
    if limits is None:
        return None
    user = getattr(request, 'user', None)
    if settings.ACCOUNTS_ENABLED and user is not None and user.is_authenticated:
        if limits.max_active_jobs_per_user and JobRecord.objects.filter(owner=user, status__in=ACTIVE).count() >= limits.max_active_jobs_per_user:
            return f"You already have {limits.max_active_jobs_per_user} {'job' if limits.max_active_jobs_per_user == 1 else 'jobs'} waiting or running. Please wait for one to finish before submitting more."
        group = get_user_group(user)
        if group and limits.max_active_jobs_per_group and JobRecord.objects.filter(group=group, status__in=ACTIVE).count() >= limits.max_active_jobs_per_group:
            return f"Your group already has {limits.max_active_jobs_per_group} {'job' if limits.max_active_jobs_per_group == 1 else 'jobs'} waiting or running. Please try again later."
    elif limits.max_active_jobs_anonymous and JobRecord.objects.filter(owner__isnull=True, status__in=ACTIVE).count() >= limits.max_active_jobs_anonymous:
        return "The server is busy with other users' jobs. Please try again in a while" + (" or log in." if settings.ACCOUNTS_ENABLED else ".")
    return None
