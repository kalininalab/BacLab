"""Privacy, limits, monitoring, usage report."""
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from baclab import tasks
from baclab.models import JobRecord, LabGroup, SiteLimits, get_user_group

User = get_user_model()


def user(name, group=None):
    u = User.objects.create_user(name, f'{name}@example.com', 'pw')
    if group:
        u.profile.group = group
        u.profile.save()
    return u


class PrivacyTest(TestCase):
    def setUp(self):
        self.lab = LabGroup.objects.create(name='Lab')
        self.alice, self.bob, self.carol = user('alice', self.lab), user('bob', self.lab), user('carol')
        self.job = JobRecord.objects.create(job_id='mlst-p1', job_type='mlst', status='finished', owner=self.alice, group=self.lab, private=True)
        self.url = reverse('baclab:results') + '?job_id=mlst-p1'

    def test_private_results_need_owner_or_group(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.login(username='carol', password='pw')
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout(); self.client.login(username='bob', password='pw')
        self.assertNotIn(self.client.get(self.url).status_code, (401, 403))
        self.client.logout(); self.client.login(username='alice', password='pw')
        self.assertNotIn(self.client.get(self.url).status_code, (401, 403))

    def test_public_jobs_stay_open_by_link(self):
        JobRecord.objects.filter(pk='mlst-p1').update(private=False)
        self.assertNotIn(self.client.get(self.url).status_code, (401, 403))

    def test_report_files_of_private_jobs_are_protected_too(self):
        response = self.client.get(reverse('baclab:tool_report_file', args=['mlst-p1', 'x.html']))
        self.assertEqual(response.status_code, 401)

    def test_owner_can_toggle_private(self):
        self.client.login(username='alice', password='pw')
        self.client.post(reverse('baclab:set_private', args=['mlst-p1']), {'private': '0'})
        self.job.refresh_from_db()
        self.assertFalse(self.job.private)
        self.client.logout(); self.client.login(username='bob', password='pw')
        self.assertEqual(self.client.post(reverse('baclab:set_private', args=['mlst-p1']), {'private': '1'}).status_code, 404)

    def test_new_job_can_be_marked_private_only_when_logged_in(self):
        from baclab.toolkit import registry
        tool = registry.get('padloc')
        with patch('baclab.db_status.missing_for_tool', return_value=[]), patch('baclab.tool_views.run_job.apply_async'), \
                override_settings(UPLOAD_DIR=tempfile.mkdtemp()):
            self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nAC\n'), 'private': 'on'})
            self.client.login(username='alice', password='pw')
            self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nAC\n'), 'private': 'on'})
        flags = list(JobRecord.objects.filter(job_type='padloc').order_by('queued_at').values_list('owner__username', 'private'))
        self.assertEqual(flags, [(None, False), ('alice', True)])


class LimitsTest(TestCase):
    def submit(self):
        from baclab.toolkit import registry
        tool = registry.get('padloc')
        with patch('baclab.db_status.missing_for_tool', return_value=[]), patch('baclab.tool_views.run_job.apply_async'), \
                override_settings(UPLOAD_DIR=tempfile.mkdtemp()):
            return self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nAC\n')})

    def test_no_limits_by_default(self):
        self.assertEqual(self.submit().status_code, 200)

    def test_user_limit(self):
        alice = user('alice')
        SiteLimits(max_active_jobs_per_user=1).save()
        JobRecord.objects.create(job_id='blast-1', job_type='blast', status='running', owner=alice)
        self.client.login(username='alice', password='pw')
        response = self.submit()
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'already have 1 job waiting', response.content)
        JobRecord.objects.filter(pk='blast-1').update(status='finished')
        self.assertEqual(self.submit().status_code, 200)

    def test_group_and_anonymous_limits(self):
        lab = LabGroup.objects.create(name='Lab')
        alice, bob = user('alice', lab), user('bob', lab)
        SiteLimits(max_active_jobs_per_group=1, max_active_jobs_anonymous=1).save()
        JobRecord.objects.create(job_id='blast-1', job_type='blast', status='queued', owner=alice, group=lab)
        self.client.login(username='bob', password='pw')
        self.assertEqual(self.submit().status_code, 400)
        self.client.logout()
        self.assertEqual(self.submit().status_code, 200)   # first anonymous job
        self.assertEqual(self.submit().status_code, 400)   # second one: the anonymous cap is 1


class MonitoringTest(TestCase):
    def test_stuck_job_alert_is_sent_once(self):
        old = timezone.now() - timedelta(hours=100)
        job = JobRecord.objects.create(job_id='blast-s', job_type='blast', status='running')
        JobRecord.objects.filter(pk=job.pk).update(started_at=old)
        with patch('baclab.notify.webhook') as hook, override_settings(ADMINS=[('Admin', 'admin@example.com')], DISK_ALERT_PERCENT=101):
            tasks.check_system()
            tasks.check_system()
        self.assertEqual(len([m for m in mail.outbox if 'stuck' in m.subject]), 1)
        self.assertEqual(hook.call_count, 1)

    def test_disk_alert_once_per_day(self):
        from django.core.cache import cache
        cache.clear()
        with patch('baclab.notify.webhook'), override_settings(ADMINS=[('Admin', 'admin@example.com')], DISK_ALERT_PERCENT=0):
            tasks.check_system()
            first = len([m for m in mail.outbox if 'full' in m.subject])
            tasks.check_system()
            second = len([m for m in mail.outbox if 'full' in m.subject])
        self.assertGreaterEqual(first, 1)
        self.assertEqual(first, second)

    def test_webhook_failure_never_raises(self):
        from baclab import notify
        with override_settings(NOTIFY_WEBHOOK_URL='http://127.0.0.1:9/none'):
            self.assertFalse(notify.webhook('hello'))

    def test_expiry_warning_mail(self):
        alice = user('alice')
        job = JobRecord.objects.create(job_id='blast-e', job_type='blast', status='finished', owner=alice)
        JobRecord.objects.filter(pk=job.pk).update(queued_at=timezone.now() - timedelta(days=27), finished_at=timezone.now() - timedelta(days=27))
        self.assertEqual(tasks.warn_expiring_results(), 1)
        self.assertEqual(tasks.warn_expiring_results(), 0)   # only once
        self.assertIn('will be deleted soon', mail.outbox[-1].subject)


class AdminReportsTest(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'boss@example.com', 'pw')
        self.client.login(username='boss', password='pw')

    def test_usage_report_and_csv(self):
        alice = user('alice')
        now = timezone.now()
        JobRecord.objects.create(job_id='blast-u', job_type='blast', status='finished', owner=alice, started_at=now - timedelta(hours=2), finished_at=now)
        page = self.client.get(reverse('admin:usage'))
        self.assertContains(page, 'alice')
        self.assertContains(page, '2.0')
        csv_response = self.client.get(reverse('admin:usage'), {'format': 'csv'})
        self.assertIn(b'alice', csv_response.content)

    def test_status_page_shows_disk_and_workers(self):
        page = self.client.get(reverse('admin:system_status'))
        self.assertContains(page, 'Disk and queues')


class ProjectTest(TestCase):
    def setUp(self):
        self.alice = user('alice')
        self.bob = user('bob')
        self.client.login(username='alice', password='pw')
        self.job = JobRecord.objects.create(job_id='mlst-pr1', job_type='mlst', status='finished', owner=self.alice)

    def test_create_assign_filter_and_overview(self):
        from baclab.models import Project
        self.client.post(reverse('baclab:set_project', args=['mlst-pr1']), {'new_project': 'Outbreak 2026'})
        project = Project.objects.get(name='Outbreak 2026')
        self.job.refresh_from_db()
        self.assertEqual(self.job.project, project)
        JobRecord.objects.create(job_id='mlst-pr2', job_type='mlst', status='finished', owner=self.alice)
        listing = self.client.get(reverse('baclab:my_jobs'), {'project': project.pk}).content.decode()
        self.assertIn('mlst-pr1', listing)
        self.assertNotIn('mlst-pr2', listing)
        overview = self.client.get(reverse('baclab:project_detail', args=[project.pk]))
        self.assertContains(overview, 'mlst-pr1')
        self.assertIn(b'mlst-pr1', self.client.get(reverse('baclab:project_detail', args=[project.pk]), {'format': 'csv'}).content)

    def test_zip_of_results_and_privacy_between_users(self):
        from baclab.models import Project
        project = Project.objects.create(name='P', owner=self.alice)
        JobRecord.objects.filter(pk='mlst-pr1').update(project=project)
        with tempfile.TemporaryDirectory() as results:
            with open(os.path.join(results, 'mlst-pr1.zip'), 'wb') as handle:
                handle.write(b'PK\x05\x06' + b'\0' * 18)
            with override_settings(RESULTS_DIR=results):
                response = self.client.get(reverse('baclab:project_download', args=[project.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(b''.join(response.streaming_content)), 20)
        self.client.logout(); self.client.login(username='bob', password='pw')
        self.assertEqual(self.client.get(reverse('baclab:project_detail', args=[project.pk])).status_code, 404)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ChainTest(TestCase):
    """Re-run, "use results in another tool" and genomes by NCBI accession."""

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.settings = override_settings(UPLOAD_DIR=f'{self.root.name}/uploads', DOWNLOAD_DIR=f'{self.root.name}/downloads',
                                          RESULTS_DIR=f'{self.root.name}/results', LOCAL_DEBUG_MODE=False)
        self.settings.enable()
        for name in ('uploads', 'downloads', 'results'):
            os.makedirs(f'{self.root.name}/{name}')
        self.no_db = patch('baclab.db_status.missing_for_tool', return_value=[])
        self.no_db.start()
        self.queue = patch('baclab.views.run_job.apply_async')
        self.apply_async = self.queue.start()
        self.alice = user('alice')
        self.client.login(username='alice', password='pw')

    def tearDown(self):
        self.queue.stop(); self.no_db.stop(); self.settings.disable(); self.root.cleanup()

    def finished_padloc_job(self):
        job_id = 'padloc-orig'
        base = f'{self.root.name}/downloads/{job_id}'
        os.makedirs(f'{base}/input')
        with open(f'{base}/input/g1.fasta', 'w') as handle:
            handle.write('>c\nACGT\n')
        with open(f'{base}/padloc_results.csv', 'w') as handle:
            handle.write('genome,system\n')
        with open(f'{base}/best.fna', 'w') as handle:
            handle.write('>x\nAC\n')
        return JobRecord.objects.create(job_id=job_id, job_type='padloc', status='finished', owner=self.alice,
                                        parameters={'inputs': ['g1.fasta'], 'settings': {}, 'fields': {'genomes': ['g1.fasta']}})

    def test_rerun_creates_a_new_job_with_the_same_inputs(self):
        self.finished_padloc_job()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('baclab:rerun', args=['padloc-orig']))
        self.assertEqual(response.status_code, 200)
        new = JobRecord.objects.exclude(job_id='padloc-orig').get(job_type='padloc')
        self.assertEqual(new.owner, self.alice)
        self.assertEqual(new.parameters['inputs'], ['g1.fasta'])
        self.assertTrue(os.path.exists(f'{self.root.name}/uploads/{new.job_id}/input/g1.fasta'))
        self.apply_async.assert_called_once()
        self.assertEqual(self.apply_async.call_args[1]['queue'], 'fast')

    def test_rerun_without_kept_inputs_says_so(self):
        JobRecord.objects.create(job_id='padloc-gone', job_type='padloc', status='finished', owner=self.alice, parameters={'fields': {'genomes': ['x.fasta']}})
        response = self.client.post(reverse('baclab:rerun', args=['padloc-gone']))
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'no longer kept', response.content)

    def test_rerun_of_a_legacy_tool_is_explained(self):
        JobRecord.objects.create(job_id='blast-old', job_type='blast', status='finished', owner=self.alice)
        self.assertEqual(self.client.post(reverse('baclab:rerun', args=['blast-old'])).status_code, 400)

    def test_send_results_to_another_tool(self):
        self.finished_padloc_job()
        page = self.client.get(reverse('baclab:send_to', args=['padloc-orig']))
        self.assertContains(page, 'best.fna')
        self.assertNotContains(page, 'g1.fasta')   # the run's own input is not offered
        with self.captureOnCommitCallbacks(execute=True):
            ok = self.client.post(reverse('baclab:send_to', args=['padloc-orig']), {'tool': 'defensefinder', 'files': ['best.fna']})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(JobRecord.objects.filter(job_type='defensefinder', owner=self.alice).exists())
        bad = self.client.post(reverse('baclab:send_to', args=['padloc-orig']), {'tool': 'defensefinder', 'files': ['../../etc/passwd']})
        self.assertEqual(bad.status_code, 400)
        wrong = self.client.post(reverse('baclab:send_to', args=['padloc-orig']), {'tool': 'bigscape', 'files': ['best.fna']})
        self.assertEqual(wrong.status_code, 400)

    def test_nobody_else_can_rerun_my_job(self):
        self.finished_padloc_job()
        user('mallory')
        self.client.logout(); self.client.login(username='mallory', password='pw')
        self.assertEqual(self.client.post(reverse('baclab:rerun', args=['padloc-orig'])).status_code, 404)

    def test_ncbi_accessions_are_validated_and_queued(self):
        from baclab.toolkit import registry
        tool = registry.get('padloc')
        bad = self.client.post(tool.url, {'accessions': 'not-an-accession'})
        self.assertEqual(bad.status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            ok = self.client.post(tool.url, {'accessions': 'GCF_000819615.1\nGCF_000819615.1'})
        self.assertEqual(ok.status_code, 200)
        job = JobRecord.objects.get(job_type='padloc')
        self.assertEqual(job.parameters['accessions'], ['GCF_000819615.1'])
        self.assertEqual(self.apply_async.call_args[1]['args'][0]['accessions'], ['GCF_000819615.1'])
        # too few genomes for a tool that needs 3
        gtotree = registry.get('gtotree')
        self.assertEqual(self.client.post(gtotree.url, {'accessions': 'GCF_000819615.1'}).status_code, 400)

    def test_worker_fetches_accessions_before_running(self):
        from baclab import ncbi
        from baclab.toolkit import registry
        from baclab.views import run_job
        tool = registry.get('padloc')
        job_id = 'padloc-acc'
        base = f'{self.root.name}/uploads/{job_id}'
        os.makedirs(f'{base}/input'); os.makedirs(f'{base}/output/input')
        JobRecord.objects.create(job_id=job_id, job_type='padloc', status='queued')

        def fake_fetch(accessions, target_dir, extensions=()):
            for acc in accessions:
                with open(os.path.join(target_dir, f'{acc}.fna'), 'w') as handle:
                    handle.write('>x\nACGT\n')
            return [f'{acc}.fna' for acc in accessions]

        def fake_run(ctx):
            self.assertTrue(os.path.exists(f'{base}/input/GCF_000819615.1.fna'))
            with open(os.path.join(ctx['output_dir'], 'padloc_results.csv'), 'w') as handle:
                handle.write('genome,system.number,seqid,system\n')

        job = {'jobId': job_id, 'command': ['true'], 'uploadDir': f'{base}/input', 'outputDir': f'{base}/output',
               'resultsDir': f'{self.root.name}/downloads/{job_id}', 'accessions': ['GCF_000819615.1']}
        with patch.object(ncbi, 'fetch_into', side_effect=fake_fetch), patch.object(tool, 'run', side_effect=fake_run):
            run_job.apply(args=[job])
        self.assertEqual(JobRecord.objects.get(job_id=job_id).status, 'finished')


class LiveMonitorTest(TestCase):
    def fake_proc(self, root, busy_first, busy_second):
        """A fake /proc whose CPU counters change between two reads."""
        def write(stat):
            with open(os.path.join(root, 'stat'), 'w') as handle:
                handle.write(stat)
        write('cpu  100 0 100 800 0 0 0 0\ncpu0 50 0 50 400 0 0 0 0\ncpu1 50 0 50 400 0 0 0 0\n')
        with open(os.path.join(root, 'meminfo'), 'w') as handle:
            handle.write('MemTotal: 1000000 kB\nMemFree: 100000 kB\nMemAvailable: 250000 kB\nSwapTotal: 2000 kB\nSwapFree: 1000 kB\n')
        with open(os.path.join(root, 'loadavg'), 'w') as handle:
            handle.write('1.50 1.00 0.50 2/300 12345\n')
        return write

    def test_cpu_memory_and_load_from_proc(self):
        from baclab import monitoring
        with tempfile.TemporaryDirectory() as root:
            write = self.fake_proc(root, None, None)
            # between the two samples cpu0 gets 100 busy of 100 total ticks, cpu1 stays idle
            with patch('baclab.monitoring.time.sleep', side_effect=lambda s: write('cpu  200 0 100 900 0 0 0 0\ncpu0 150 0 50 400 0 0 0 0\ncpu1 50 0 50 500 0 0 0 0\n')):
                cpu = monitoring.cpu_usage(root)
            self.assertEqual(cpu['percent'], 50.0)
            self.assertEqual(cpu['cores'], [100.0, 0.0])
            memory = monitoring.memory_usage(root)
            self.assertEqual((memory['total'], memory['used'], memory['percent']), (1000000 * 1024, 750000 * 1024, 75.0))
            self.assertEqual(memory['swap_used'], 1000 * 1024)
            self.assertEqual(monitoring.load_average(root), [1.5, 1.0, 0.5])

    def test_gpu_parsing_and_absence(self):
        from baclab import monitoring
        self.assertEqual(monitoring.gpu_usage.__name__, 'gpu_usage')
        with patch('baclab.monitoring.shutil.which', return_value=None):
            self.assertEqual(monitoring.gpu_usage(), [])
        fake = type('R', (), {'stdout': '0, NVIDIA A100, 37, 4096, 40960, 55, 120.5\n1, NVIDIA A100, 0, 0, 40960, 40, [N/A]\n'})
        with patch('baclab.monitoring.shutil.which', return_value='/usr/bin/nvidia-smi'), patch('baclab.monitoring.subprocess.run', return_value=fake):
            gpus = monitoring.gpu_usage()
        self.assertEqual(len(gpus), 2)
        self.assertEqual((gpus[0]['utilization'], gpus[0]['memory_percent']), (37.0, 10.0))
        self.assertIsNone(gpus[1]['power'])

    def test_pages_need_staff_and_return_json(self):
        self.assertEqual(self.client.get(reverse('admin:monitor_data')).status_code, 302)
        User.objects.create_superuser('boss', 'b@example.com', 'pw')
        self.client.login(username='boss', password='pw')
        JobRecord.objects.create(job_id='blast-r', job_type='blast', status='running', started_at=timezone.now())
        self.assertContains(self.client.get(reverse('admin:monitor')), 'Live monitor')
        data = self.client.get(reverse('admin:monitor_data')).json()
        for key in ('cpu', 'memory', 'gpus', 'disks', 'jobs', 'load'):
            self.assertIn(key, data)
        self.assertEqual(data['jobs']['running_count'], 1)
        self.assertGreaterEqual(len(data['cpu']['cores']), 1)


class DemoDataTest(TestCase):
    def test_demo_data_pages_render_and_can_be_removed(self):
        import re
        from django.core.management import call_command
        from baclab.models import Project
        with tempfile.TemporaryDirectory() as root:
            with override_settings(DOWNLOAD_DIR=f'{root}/d', RESULTS_DIR=f'{root}/r', UPLOAD_DIR=f'{root}/u'):
                call_command('create_demo_data', stdout=open(os.devnull, 'w'))
                self.assertEqual(User.objects.filter(email__endswith='@demo.baclab.example').count(), 10)
                self.assertEqual(LabGroup.objects.count(), 3)
                self.assertGreaterEqual(JobRecord.objects.count(), 30)
                self.client.login(username='m.schumacher', password='demo-baclab-1')
                listing = self.client.get(reverse('baclab:my_jobs'))
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(self.client.get(reverse('baclab:my_jobs'), {'scope': 'group'}).status_code, 200)
                # every finished demo run of every user: detail page, results page and zip work
                for job in JobRecord.objects.filter(status='finished'):
                    self.client.logout(); self.client.login(username=job.owner.username, password='demo-baclab-1')
                    self.assertEqual(self.client.get(reverse('baclab:job_detail', args=[job.job_id])).status_code, 200, job.job_id)
                    page = self.client.get(reverse('baclab:results'), {'job_id': job.job_id})
                    self.assertEqual(page.status_code, 200, job.job_id)
                    self.assertNotContains(page, 'did not produce any results', msg_prefix=job.job_id)
                    self.assertEqual(self.client.get(reverse('baclab:results'), {'job_id': job.job_id, 'download': 'True'}).status_code, 200)
                for project in Project.objects.all()[:3]:
                    self.client.logout(); self.client.login(username=project.owner.username, password='demo-baclab-1')
                    self.assertEqual(self.client.get(reverse('baclab:project_detail', args=[project.pk])).status_code, 200)
                call_command('create_demo_data', '--remove', stdout=open(os.devnull, 'w'))
                self.assertFalse(User.objects.filter(email__endswith='@demo.baclab.example').exists())
                self.assertEqual(JobRecord.objects.count(), 0)
                self.assertEqual(os.listdir(f'{root}/d'), [])


class QueuedJobPageTest(TestCase):
    def test_a_queued_job_is_reported_as_queued_even_when_no_worker_has_reserved_it(self):
        JobRecord.objects.create(job_id='abricate-q1', job_type='abricate', status='queued')
        with patch('baclab.views.app') as celery_app:
            celery_app.control.inspect.return_value.active.return_value = {}
            celery_app.control.inspect.return_value.reserved.return_value = {}
            page = self.client.get(reverse('baclab:results'), {'job_id': 'abricate-q1'})
        self.assertContains(page, 'queued and waits')
        self.assertNotContains(page, 'Job ID not found')

    def test_unknown_job_id_still_says_not_found(self):
        with patch('baclab.views.app') as celery_app:
            celery_app.control.inspect.return_value.active.return_value = {}
            celery_app.control.inspect.return_value.reserved.return_value = {}
            page = self.client.get(reverse('baclab:results'), {'job_id': 'abricate-never'})
        self.assertContains(page, 'Job ID not found')

    def test_queues_without_a_worker_are_reported(self):
        from baclab import monitoring
        inspector = type('I', (), {'ping': lambda self: {'w1': {'ok': 'pong'}}, 'active_queues': lambda self: {'w1': [{'name': 'celery'}]}})()
        with patch('redis.Redis.from_url') as redis_client, patch('baclab.taskapp.celery.app.control.inspect', return_value=inspector):
            redis_client.return_value.llen.side_effect = lambda queue: {'celery': 0, 'fast': 3, 'heavy': 0}[queue]
            report = monitoring.queue_report()
        self.assertEqual(report['unserved'], ['fast'])


class ResultsWithOtherTasksTest(TestCase):
    def test_other_celery_tasks_do_not_break_the_results_page(self):
        """An admin database build (first argument: an integer) running on a worker must not crash the results page of a waiting job."""
        with patch('baclab.views.app') as celery_app:
            inspector = celery_app.control.inspect.return_value
            inspector.active.return_value = {'w1': [{'args': [7]}, {'args': []}, {'args': [{'jobId': 'blast-other'}]}]}
            inspector.reserved.return_value = {'w1': [{'args': [3]}]}
            page = self.client.get(reverse('baclab:results'), {'job_id': 'blast-xyz'})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Job ID not found')
