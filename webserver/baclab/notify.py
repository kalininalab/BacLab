"""Messages to the administrators: e-mail and, optionally, a chat webhook (Slack / Microsoft Teams / anything that takes {"text": ...})."""
import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import mail_admins

logger = logging.getLogger(__name__)


def webhook(text):
    """Post text to NOTIFY_WEBHOOK_URL when it is set. Never raises: a chat outage must not break a job."""
    url = getattr(settings, 'NOTIFY_WEBHOOK_URL', '')
    if not url:
        return False
    try:
        request = urllib.request.Request(url, data=json.dumps({'text': text}).encode(), headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(request, timeout=10).read()
        return True
    except Exception as error:
        logger.warning('Webhook notification failed: %s', error)
        return False


def alert(subject, message):
    """Tell the administrators: e-mail (ADMINS) plus the webhook."""
    try:
        mail_admins(subject, message, fail_silently=True)
    except Exception as error:
        logger.warning('Admin mail failed: %s', error)
    webhook(f"*{subject}*\n{message}")
