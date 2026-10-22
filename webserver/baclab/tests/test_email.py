"""The notification e-mails: default texts, texts edited in the admin, placeholders, test messages."""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from baclab import email_templates
from baclab.models import EmailMessages, JobRecord
from baclab.views import send_job_notification_email
from baclab.tasks import warn_expiring_results


class DefaultMessagesTest(TestCase):
    def test_finished_message_has_the_job_and_the_link(self):
        send_job_notification_email('mlst-abc', 'a@example.org', 'http://x/results/?job_id=mlst-abc', success=True)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['a@example.org'])
        self.assertEqual(message.subject, '[BacLab] Job mlst-abc Finished')
        self.assertIn('http://x/results/?job_id=mlst-abc', message.body)

    def test_failed_message_has_the_error(self):
        send_job_notification_email('mlst-abc', 'a@example.org', 'http://x/', success=False, error_msg='boom')
        self.assertEqual(mail.outbox[0].subject, '[BacLab] Job mlst-abc Failed')
        self.assertIn('Error: boom', mail.outbox[0].body)

    def test_no_address_no_mail(self):
        send_job_notification_email('mlst-abc', '', 'http://x/', success=True)
        self.assertEqual(mail.outbox, [])

    def test_sender_and_prefix_are_set_in_every_mode(self):
        from django.conf import settings
        self.assertEqual(settings.EMAIL_SUBJECT_PREFIX, '[BacLab] ')
        self.assertIn('@', settings.SERVER_EMAIL)
        self.assertNotEqual(settings.SERVER_EMAIL, 'root@localhost')


class EditedMessagesTest(TestCase):
    def setUp(self):
        EmailMessages.objects.update_or_create(pk=1, defaults=dict(
            finished_subject='Done: {job_name} ({tool})', finished_body='Hello!\n{job_id} is ready: {results_url}\nKeep {unknown}.',
            failed_subject='', failed_body='Sorry, {job_id} failed: {error}'))
        JobRecord.objects.create(job_id='mlst-abc', job_type='mlst', status='finished', label='My isolates')

    def test_edited_finished_message(self):
        send_job_notification_email('mlst-abc', 'a@example.org', 'http://x/r', success=True)
        message = mail.outbox[0]
        self.assertEqual(message.subject, '[BacLab] Done: My isolates (MLST)')
        self.assertIn('mlst-abc is ready: http://x/r', message.body)
        self.assertIn('{unknown}', message.body)          # not a known placeholder: left as typed

    def test_empty_text_falls_back_to_the_default(self):
        send_job_notification_email('mlst-abc', 'a@example.org', 'http://x/r', success=False, error_msg='boom')
        message = mail.outbox[0]
        self.assertEqual(message.subject, '[BacLab] Job mlst-abc Failed')      # subject left empty
        self.assertEqual(message.body.strip(), 'Sorry, mlst-abc failed: boom')  # body edited

    def test_unknown_placeholder_is_refused_when_saving(self):
        row = EmailMessages(finished_body='see {resultsurl}')
        with self.assertRaises(ValidationError) as caught:
            row.full_clean()
        self.assertIn('finished_body', caught.exception.message_dict)

    def test_expiry_warning_uses_the_edited_text(self):
        EmailMessages.objects.update(expiry_subject='Last chance: {job_name}', expiry_body='{job_id} goes on {expires}: {results_url}')
        user = get_user_model().objects.create_user('u1', 'u1@example.org', 'pw')
        JobRecord.objects.filter(job_id='mlst-abc').update(owner=user, finished_at=timezone.now() - timedelta(days=28), expiry_warned=False)
        self.assertEqual(warn_expiring_results(), 1)
        self.assertEqual(mail.outbox[0].subject, '[BacLab] Last chance: My isolates')
        self.assertIn('mlst-abc goes on', mail.outbox[0].body)


class AdminAndTestMessagesTest(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('boss', 'boss@example.org', 'pw')
        self.client.force_login(self.admin)

    def post_form(self, **extra):
        data = {f'{k}_{p}': '' for k in ('finished', 'failed', 'expiry') for p in ('subject', 'body')}
        data.update(extra)
        return self.client.post(reverse('admin:baclab_emailmessages_change', args=[1]), data, follow=True)

    def test_admin_page_and_index_link(self):
        page = self.client.get(reverse('admin:baclab_emailmessages_changelist'), follow=True)   # one row: the list goes straight to it
        self.assertContains(page, 'Send a test to')
        self.assertContains(page, 'Restore the default texts')
        self.assertContains(self.client.get(reverse('admin:index')), 'E-mail messages')

    def test_the_page_starts_with_the_default_texts(self):
        row = EmailMessages.objects.get(pk=1)
        self.assertEqual(row.finished_subject, 'Job {job_id} Finished')
        self.assertIn('View results: {results_url}', row.finished_body)
        self.assertIn('Error: {error}', row.failed_body)
        self.assertIn('{expires}', row.expiry_body)

    def test_restore_defaults(self):
        EmailMessages.objects.filter(pk=1).update(finished_subject='Changed', finished_body='Changed')
        response = self.post_form(finished_subject='Changed', finished_body='Changed', restore_defaults='on')
        self.assertContains(response, 'default texts were restored')
        self.assertEqual(EmailMessages.objects.get(pk=1).finished_subject, 'Job {job_id} Finished')

    def test_saving_with_a_test_address_sends_one_sample_of_each(self):
        response = self.post_form(finished_subject='Hi {job_id}', send_test_to='me@example.org')
        self.assertContains(response, '3 test messages sent to me@example.org')
        self.assertEqual([m.to for m in mail.outbox], [['me@example.org']] * 3)
        self.assertEqual(mail.outbox[0].subject, '[BacLab] Hi mlst-sample-1a2b3c')
        self.assertEqual(EmailMessages.objects.count(), 1)
        self.assertEqual(EmailMessages.objects.get(pk=1).finished_subject, 'Hi {job_id}')

    def test_saving_without_a_test_address_sends_nothing(self):
        self.post_form()
        self.assertEqual(mail.outbox, [])

    def test_mail_server_error_is_shown_not_raised(self):
        with patch('baclab.admin.send_samples', side_effect=OSError('connection refused')):
            response = self.post_form(send_test_to='me@example.org')
        self.assertContains(response, 'connection refused')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_local_mode_says_where_the_messages_went(self):
        with patch('baclab.admin.send_samples', return_value=3):
            response = self.post_form(send_test_to='me@example.org')
        self.assertContains(response, 'written to the server log')


class TestEmailCommandTest(TestCase):
    def test_command_sends_samples(self):
        out = StringIO()
        call_command('test_email', '--to', 'me@example.org', '--kind', 'failed', stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Job mlst-sample-1a2b3c Failed', mail.outbox[0].subject)
        self.assertIn('1 message(s)', out.getvalue())

    def test_command_reports_a_broken_mail_server(self):
        with patch('baclab.email_templates.send', side_effect=OSError('refused')):
            with self.assertRaises(CommandError):
                call_command('test_email', '--to', 'me@example.org', stdout=StringIO())

    def test_render_ignores_unknown_kinds_of_context(self):
        subject, body = email_templates.render('finished', job_id='x', job_name='x', tool='t', results_url='u', surplus='1')
        self.assertEqual(subject, 'Job x Finished')
