"""Which notification e-mail addresses are accepted (set by the administrators in the admin: E-mail policy)."""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def patterns():
    """The allowed domain patterns: the admin's E-mail policy, else the NOTIFICATION_EMAIL_DOMAINS setting (comma separated), else none."""
    try:
        from .models import EmailPolicy
        policy = EmailPolicy.objects.first()
        if policy and policy.patterns():
            return policy.patterns()
    except Exception:   # before the first migrate
        pass
    return [p.strip() for p in getattr(settings, 'NOTIFICATION_EMAIL_DOMAINS', '').split(',') if p.strip()]


def friendly(rule):
    """A pattern as people write domains: example\\.org -> example.org, .*\\.edu -> *.edu (complicated expressions are shown as they are)."""
    if any(c in rule for c in '()|[]+?{}^$'):
        return rule
    return rule.replace('\\.', '.').replace('.*', '*')


def describe():
    """A short sentence for the forms, or '' when every address is accepted."""
    rules = patterns()
    if not rules:
        return ''
    return "Only addresses ending in " + ", ".join(f"@{friendly(rule)}" for rule in rules) + " are accepted."


def check(email):
    """None when the address may be used, else a message for the user. Empty addresses are fine (notifications are optional)."""
    email = (email or '').strip()
    if not email:
        return None
    try:
        validate_email(email)
    except ValidationError:
        return "This is not a valid e-mail address."
    rules = patterns()
    if not rules:
        return None
    domain = email.rsplit('@', 1)[1]
    for rule in rules:
        try:
            if re.fullmatch(rule, domain, re.IGNORECASE):
                return None
        except re.error:
            continue   # a broken rule never locks everybody out
    return f"This e-mail address cannot be used here. {describe()}"
