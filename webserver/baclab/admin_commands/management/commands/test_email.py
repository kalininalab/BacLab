from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from baclab import email_templates


class Command(BaseCommand):
    help = ('Sends a sample of the notification e-mails (job finished / failed / results will be deleted) with the texts from the admin '
            '(E-mail messages) to one address. Local mode writes them to the log instead of sending them.')

    def add_arguments(self, parser):
        parser.add_argument('--to', required=True, help='address that receives the samples')
        parser.add_argument('--kind', action='append', choices=list(email_templates.KINDS), help='only this message (repeatable); default: all')

    def handle(self, *args, **options):
        self.stdout.write(f"E-mail backend: {settings.EMAIL_BACKEND}; server {settings.EMAIL_HOST}:{settings.EMAIL_PORT}; sender {settings.SERVER_EMAIL}")
        try:
            count = email_templates.send_samples(options['to'], options['kind'])
        except Exception as error:
            raise CommandError(f"Could not send: {error}")
        self.stdout.write(self.style.SUCCESS(f"{count} message(s) handed to the mail system for {options['to']}."))
