import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import LiveServerTestCase, TestCase, override_settings
from django.urls import reverse

from baclab.models import ApiToken, JobRecord, LabGroup

User = get_user_model()
CLIENT = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'baclab-client')


def make_token(name='alice', group=None):
    user = User.objects.create_user(name, f'{name}@example.com', 'pw')
    if group:
        user.profile.group = group
        user.profile.save()
    token, key = ApiToken.create_for(user, 'test')
    return user, key


class ApiTest(TestCase):
    def setUp(self):
        self.alice, self.key = make_token('alice')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {self.key}'}
        self.upload = override_settings(UPLOAD_DIR=tempfile.mkdtemp())
        self.upload.enable()
        self.no_db = patch('baclab.db_status.missing_for_tool', return_value=[])
        self.no_db.start()
        self.queue = patch('baclab.views.run_job.apply_async')
        self.queue.start()

    def tearDown(self):
        self.queue.stop(); self.no_db.stop(); self.upload.disable()

    def test_key_is_required_and_only_its_hash_is_stored(self):
        self.assertEqual(self.client.get(reverse('baclab:api_tools')).status_code, 401)
        self.assertEqual(self.client.get(reverse('baclab:api_tools'), HTTP_AUTHORIZATION='Bearer lm_wrong').status_code, 401)
        token = ApiToken.objects.get()
        self.assertNotIn(self.key, token.key_hash)
        self.assertEqual(self.client.get(reverse('baclab:api_tools'), **self.auth).status_code, 200)
        token.refresh_from_db()
        self.assertIsNotNone(token.last_used)

    def test_tool_list(self):
        names = {t['name'] for t in self.client.get(reverse('baclab:api_tools'), **self.auth).json()['tools']}
        self.assertIn('padloc', names)
        self.assertNotIn('basalt', names)   # switched off

    def test_submit_status_and_ownership(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('baclab:api_submit', args=['padloc']),
                                       {'genomes': SimpleUploadedFile('g.fasta', b'>c\nACGT\n'), 'private': 'on'}, **self.auth)
        self.assertEqual(response.status_code, 201, response.content)
        job_id = response.json()['job_id']
        job = JobRecord.objects.get(job_id=job_id)
        self.assertEqual((job.owner, job.private), (self.alice, True))
        self.assertEqual(self.client.get(reverse('baclab:api_job', args=[job_id]), **self.auth).json()['status'], 'queued')
        self.assertEqual(len(self.client.get(reverse('baclab:api_jobs'), **self.auth).json()['jobs']), 1)
        # somebody else cannot see it
        _, other_key = make_token('mallory')
        self.assertEqual(self.client.get(reverse('baclab:api_job', args=[job_id]), HTTP_AUTHORIZATION=f'Bearer {other_key}').status_code, 404)

    def test_group_members_can_see_each_others_jobs(self):
        lab = LabGroup.objects.create(name='Lab')
        a, key_a = make_token('a1', lab)
        b, key_b = make_token('b1', lab)
        JobRecord.objects.create(job_id='padloc-g', job_type='padloc', status='queued', owner=a, group=lab)
        self.assertEqual(self.client.get(reverse('baclab:api_job', args=['padloc-g']), HTTP_AUTHORIZATION=f'Bearer {key_b}').status_code, 200)

    def test_errors_are_json(self):
        bad = self.client.post(reverse('baclab:api_submit', args=['padloc']), {}, **self.auth)
        self.assertEqual(bad.status_code, 400)
        self.assertIn('error', bad.json())
        self.assertEqual(self.client.post(reverse('baclab:api_submit', args=['nosuch']), {}, **self.auth).status_code, 404)

    def test_download_needs_a_finished_job(self):
        JobRecord.objects.create(job_id='padloc-d', job_type='padloc', status='finished', owner=self.alice)
        with tempfile.TemporaryDirectory() as results:
            with override_settings(RESULTS_DIR=results):
                self.assertEqual(self.client.get(reverse('baclab:api_download', args=['padloc-d']), **self.auth).status_code, 404)
                with open(os.path.join(results, 'padloc-d.zip'), 'wb') as handle:
                    handle.write(b'PK\x05\x06' + b'\0' * 18)
                ok = self.client.get(reverse('baclab:api_download', args=['padloc-d']), **self.auth)
                self.assertEqual(ok.status_code, 200)

    @override_settings(API_ENABLED=False)
    def test_api_can_be_switched_off(self):
        self.assertEqual(self.client.get(reverse('baclab:api_tools'), **self.auth).status_code, 404)

    @override_settings(ACCOUNTS_ENABLED=False)
    def test_api_needs_accounts(self):
        self.assertEqual(self.client.get(reverse('baclab:api_tools'), **self.auth).status_code, 404)

    def test_keys_page_creates_shows_once_and_revokes(self):
        self.client.login(username='alice', password='pw')
        page = self.client.post(reverse('baclab:api_keys'), {'name': 'cluster'})
        self.assertContains(page, 'lm_')
        self.assertNotContains(self.client.get(reverse('baclab:api_keys')), 'Your new key')
        token = ApiToken.objects.get(name='cluster')
        self.client.post(reverse('baclab:api_key_delete', args=[token.pk]))
        self.assertFalse(ApiToken.objects.filter(name='cluster').exists())


class ClientScriptTest(LiveServerTestCase):
    """The command-line client against a real (live test) server."""

    def test_client_lists_tools_and_submits(self):
        user, key = make_token('cli')
        env = dict(os.environ, BACLAB_URL=self.live_server_url, BACLAB_TOKEN=key)
        with tempfile.NamedTemporaryFile('w', suffix='.fasta', delete=False) as handle:
            handle.write('>c\nACGT\n')
        try:
            with patch('baclab.db_status.missing_for_tool', return_value=[]), patch('baclab.views.run_job.apply_async'), \
                    override_settings(UPLOAD_DIR=tempfile.mkdtemp()):
                tools = subprocess.run([sys.executable, CLIENT, 'tools'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                self.assertIn('padloc', tools.stdout, tools.stderr)
                submit = subprocess.run([sys.executable, CLIENT, 'submit', 'padloc', handle.name], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True)
                self.assertTrue(submit.stdout.strip().startswith('padloc-'), submit.stderr)
        finally:
            os.unlink(handle.name)
        self.assertTrue(JobRecord.objects.filter(job_type='padloc', owner=user).exists())
