"""Optional user accounts: own jobs, group mates' jobs, everything still works anonymously."""
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from baclab.models import JobRecord, LabGroup, UserProfile, get_user_group
from baclab.tasks import clean_old_results

User = get_user_model()


def make_user(name, group=None):
    user = User.objects.create_user(name, f'{name}@example.com', 'pw')
    if group:
        user.profile.group = group
        user.profile.save()
    return user


def make_job(owner, job_id, **extra):
    return JobRecord.objects.create(job_id=job_id, job_type='blast', status='finished', owner=owner,
                                    group=get_user_group(owner) if owner else None, **extra)


class AccountsTest(TestCase):
    def setUp(self):
        self.lab = LabGroup.objects.create(name='Lab A')
        self.other_lab = LabGroup.objects.create(name='Lab B')
        self.alice = make_user('alice', self.lab)
        self.bob = make_user('bob', self.lab)
        self.carol = make_user('carol', self.other_lab)
        self.dave = make_user('dave')   # no group

    def login(self, user):
        self.client.login(username=user.username, password='pw')

    def test_profile_is_created_for_every_user(self):
        self.assertTrue(hasattr(self.dave, 'profile'))
        self.assertIsNone(get_user_group(self.dave))
        self.assertEqual(get_user_group(self.alice), self.lab)

    def test_site_works_without_login_and_offers_it(self):
        response = self.client.get(reverse('baclab:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('baclab:login'))
        self.assertEqual(self.client.get(reverse('baclab:my_jobs')).status_code, 302)   # only this page needs a login

    def test_login_and_logout_links(self):
        self.login(self.alice)
        page = self.client.get(reverse('baclab:index'))
        self.assertContains(page, 'my jobs')
        self.assertContains(page, 'logout (alice')

    def test_my_jobs_lists_own_jobs_only(self):
        make_job(self.alice, 'blast-a1')
        make_job(self.bob, 'blast-b1')
        make_job(None, 'blast-anon')
        self.login(self.alice)
        page = self.client.get(reverse('baclab:my_jobs')).content.decode()
        self.assertIn('blast-a1', page)
        self.assertNotIn('blast-b1', page)
        self.assertNotIn('blast-anon', page)

    def test_group_tab_shows_group_mates_but_not_other_groups(self):
        make_job(self.alice, 'blast-a1')
        make_job(self.bob, 'blast-b1')
        make_job(self.carol, 'blast-c1')
        self.login(self.alice)
        page = self.client.get(reverse('baclab:my_jobs'), {'scope': 'group'}).content.decode()
        self.assertIn('blast-b1', page)
        self.assertNotIn('blast-a1', page)   # own jobs are on the other tab
        self.assertNotIn('blast-c1', page)

    def test_user_without_group_has_no_group_tab(self):
        make_job(self.alice, 'blast-a1')
        self.login(self.dave)
        page = self.client.get(reverse('baclab:my_jobs'), {'scope': 'group'}).content.decode()
        self.assertNotIn('blast-a1', page)
        self.assertNotIn('?scope=group', page)

    def test_job_detail_permissions(self):
        make_job(self.alice, 'blast-a1')
        url = reverse('baclab:job_detail', args=['blast-a1'])
        self.login(self.alice)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout(); self.login(self.bob)
        self.assertEqual(self.client.get(url).status_code, 200)   # same group
        self.client.logout(); self.login(self.carol)
        self.assertEqual(self.client.get(url).status_code, 404)   # other group
        self.client.logout(); self.login(self.dave)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_only_the_owner_can_label_and_extend(self):
        make_job(self.alice, 'blast-a1')
        self.login(self.bob)
        self.assertEqual(self.client.post(reverse('baclab:set_label', args=['blast-a1']), {'label': 'mine now'}).status_code, 404)
        self.client.logout(); self.login(self.alice)
        self.client.post(reverse('baclab:set_label', args=['blast-a1']), {'label': 'K12 reference'})
        self.client.post(reverse('baclab:set_retention', args=['blast-a1']), {'days': '90'})
        job = JobRecord.objects.get(job_id='blast-a1')
        self.assertEqual((job.label, job.retention_days), ('K12 reference', 90))
        self.assertEqual(self.client.post(reverse('baclab:set_retention', args=['blast-a1']), {'days': '5000'}).status_code, 400)

    def test_cleanup_keeps_jobs_their_owner_extended(self):
        with tempfile.TemporaryDirectory() as root:
            dirs = {name: os.path.join(root, name) for name in ('results', 'uploads', 'downloads')}
            for path in dirs.values():
                os.makedirs(os.path.join(path, 'blast-keep'))
                os.makedirs(os.path.join(path, 'blast-drop'))
            old = (timezone.now() - timedelta(days=60)).timestamp()
            for path in dirs.values():
                for job in ('blast-keep', 'blast-drop'):
                    os.utime(os.path.join(path, job), (old, old))
            make_job(self.alice, 'blast-keep', retention_days=90)
            with override_settings(RESULTS_DIR=dirs['results'], UPLOAD_DIR=dirs['uploads'], DOWNLOAD_DIR=dirs['downloads'], MAX_RESULTS_AGE=30):
                clean_old_results()
            self.assertTrue(os.path.isdir(os.path.join(dirs['results'], 'blast-keep')))
            self.assertFalse(os.path.isdir(os.path.join(dirs['results'], 'blast-drop')))

    def test_new_jobs_get_owner_and_group(self):
        from baclab.toolkit import registry
        tool = registry.get('padloc')
        self.login(self.alice)
        with patch('baclab.db_status.missing_for_tool', return_value=[]), patch('baclab.tool_views.run_job.apply_async'), \
                override_settings(UPLOAD_DIR=tempfile.mkdtemp()):
            self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nACGT\n'), 'email': ''})
        job = JobRecord.objects.get(job_type='padloc')
        self.assertEqual((job.owner, job.group), (self.alice, self.lab))
        self.assertEqual(job.parameters['inputs'], ['g.fasta'])

    def test_anonymous_jobs_have_no_owner(self):
        from baclab.toolkit import registry
        tool = registry.get('padloc')
        with patch('baclab.db_status.missing_for_tool', return_value=[]), patch('baclab.tool_views.run_job.apply_async'), \
                override_settings(UPLOAD_DIR=tempfile.mkdtemp()):
            self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nACGT\n')})
        job = JobRecord.objects.get(job_type='padloc')
        self.assertIsNone(job.owner)

    @override_settings(ACCOUNTS_ENABLED=False)
    def test_accounts_can_be_switched_off(self):
        self.login(self.alice)
        self.assertEqual(self.client.get(reverse('baclab:my_jobs')).status_code, 404)
        page = self.client.get(reverse('baclab:index'))
        self.assertNotContains(page, reverse('baclab:login'))
        self.assertNotContains(page, 'my jobs')

    def test_signup_only_when_allowed(self):
        self.assertEqual(self.client.get(reverse('baclab:signup')).status_code, 404)
        with override_settings(ALLOW_SIGNUP=True):
            response = self.client.post(reverse('baclab:signup'), {'username': 'newuser', 'password1': 'S3cure-passw0rd!', 'password2': 'S3cure-passw0rd!'})
            self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(username='newuser').profile.group is None)


class AdminUserTest(TestCase):
    def test_adding_a_user_with_a_group_in_the_admin(self):
        User.objects.create_superuser('boss', 'boss@example.com', 'pw')
        self.client.login(username='boss', password='pw')
        group = LabGroup.objects.create(name='Lab A')
        response = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'test2', 'password1': 'S3cure-passw0rd!', 'password2': 'S3cure-passw0rd!',
            'profile-TOTAL_FORMS': '1', 'profile-INITIAL_FORMS': '0', 'profile-MIN_NUM_FORMS': '0', 'profile-MAX_NUM_FORMS': '1',
            'profile-0-group': str(group.pk), 'profile-0-id': '', 'profile-0-user': '',
        })
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['errors'])
        self.assertEqual(get_user_group(User.objects.get(username='test2')), group)
        self.assertEqual(UserProfile.objects.filter(user__username='test2').count(), 1)


class EmailPolicyTest(TestCase):
    def policy(self, text):
        from baclab.models import EmailPolicy
        EmailPolicy.objects.all().delete()
        EmailPolicy(allowed_domain_patterns=text).save()

    def test_no_policy_allows_everything(self):
        from baclab import email_policy
        self.assertIsNone(email_policy.check('anyone@anywhere.org'))
        self.assertIsNone(email_policy.check(''))
        self.assertEqual(email_policy.describe(), '')

    def test_patterns_are_regular_expressions_on_the_domain(self):
        from baclab import email_policy
        self.policy('example\\.org\n.*\\.uni-example\\.de\n(a|b)\\.net')
        for ok in ('x@example.org', 'x@EXAMPLE.ORG', 'x@cs.uni-example.de', 'x@b.net'):
            self.assertIsNone(email_policy.check(ok), ok)
        for bad in ('x@gmail.com', 'x@example.org.evil.com', 'x@evilexample.org', 'x@uni-example.de', 'not an address'):
            self.assertIsNotNone(email_policy.check(bad), bad)

    def test_broken_pattern_is_refused_by_the_admin_and_never_locks_people_out(self):
        from django.core.exceptions import ValidationError
        from baclab import email_policy
        from baclab.models import EmailPolicy
        with self.assertRaises(ValidationError):
            EmailPolicy(allowed_domain_patterns='(unclosed').full_clean()
        self.policy('(unclosed\nexample\\.org')   # saved around validation
        self.assertIsNone(email_policy.check('x@example.org'))

    @override_settings(NOTIFICATION_EMAIL_DOMAINS='example\\.org, .*\\.edu')
    def test_setting_is_used_when_the_admin_has_no_policy(self):
        from baclab import email_policy
        self.assertIsNone(email_policy.check('x@mit.edu'))
        self.assertIsNotNone(email_policy.check('x@gmail.com'))

    def test_submission_with_a_disallowed_address_is_refused(self):
        from baclab.toolkit import registry
        self.policy('example\\.org')
        tool = registry.get('padloc')
        with patch('baclab.db_status.missing_for_tool', return_value=[]), patch('baclab.tool_views.run_job.apply_async'), \
                override_settings(UPLOAD_DIR=tempfile.mkdtemp()):
            bad = self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nAC\n'), 'email': 'x@gmail.com'})
            good = self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nAC\n'), 'email': 'x@example.org'})
            anonymous = self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nAC\n'), 'email': ''})
        self.assertEqual(bad.status_code, 400)
        self.assertIn(b'@example', bad.content)
        self.assertEqual(good.status_code, 200)
        self.assertEqual(anonymous.status_code, 200)   # notifications stay optional
        self.assertContains(self.client.get(tool.url), 'Only addresses ending in')

    def test_account_email_follows_the_policy(self):
        self.policy('example\\.org')
        user = make_user('erin')
        self.client.login(username='erin', password='pw')
        self.client.post(reverse('baclab:set_email'), {'email': 'erin@gmail.com'})
        user.refresh_from_db()
        self.assertEqual(user.email, 'erin@example.com')   # unchanged (make_user used example.com... refused later)
        self.client.post(reverse('baclab:set_email'), {'email': 'erin@example.org'})
        user.refresh_from_db()
        self.assertEqual(user.email, 'erin@example.org')
        self.assertContains(self.client.get(reverse('baclab:my_jobs')), 'erin@example.org')


class LdapGroupTest(TestCase):
    """The group of an LDAP user comes from an LDAP attribute (here with a stand-in for django-auth-ldap's user object)."""

    def test_group_is_created_and_assigned_from_the_attribute(self):
        from types import SimpleNamespace
        from django.contrib.auth.signals import user_logged_in
        user = make_user('ldapuser')
        user.ldap_user = SimpleNamespace(attrs={'department': ['Microbiology'], 'mail': ['x@example.org']})
        with override_settings(LDAP_GROUP_ATTRIBUTE='department'):
            user_logged_in.send(sender=User, request=None, user=user)
        self.assertEqual(get_user_group(user).name, 'Microbiology')
        with override_settings(LDAP_GROUP_ATTRIBUTE=''):
            other = make_user('plain')
            other.ldap_user = SimpleNamespace(attrs={'department': ['X']})
            user_logged_in.send(sender=User, request=None, user=other)
        self.assertIsNone(get_user_group(other))
