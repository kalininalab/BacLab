"""Errors a tool can raise to give the user a specific message instead of the generic failure one."""

from django.conf import settings


def contact_message():
    return f"If you have further questions, please email us with your job id: {settings.ADMIN_EMAIL}"


class JobError(Exception):
    """A job failure with its own message and archive name.

    Subclass it and set:
      archive_prefix  - the failed-job archive is called "<archive_prefix>-<job id>.zip"
      job_message     - stored on the job record (what the status page shows)
      results_message - what the results page shows; a string, or a function of the job id
                        (default: the job_message followed by the contact message)
      notify_admin    - e-mail the admins about this failure (default: no, it is a user input problem)
    """
    archive_prefix = 'failed'
    job_message = "An unexpected error occurred during job execution. The administrators have been notified."
    results_message = None
    notify_admin = False

    registry = []   # every subclass, so the results page can recognise their archives

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        JobError.registry.append(cls)

    @classmethod
    def results_page_message(cls, job_id):
        if callable(cls.results_message):
            return cls.results_message(job_id)
        return cls.results_message or (cls.job_message + " " + contact_message())


def failed_results_message():
    """Shown on the results page when a job failed with an unexpected error."""
    return "Your job did not produce any results. You can try different database configurations. " + contact_message()
