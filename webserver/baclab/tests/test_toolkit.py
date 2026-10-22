"""Tools that describe themselves (tools/<name>/tool.py) and tools added in the admin (models.CustomTool)."""
import os
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from baclab import tool_catalog
from baclab.models import CustomTool, JobRecord, ToolSetting
from baclab.toolkit import custom, registry
from baclab.toolkit.menu import CATEGORY_KEYS
from baclab.views import run_job


class ToolFolderTest(SimpleTestCase):
    """Conventions every tools/<name>/ folder has to follow (see tools/README.md)."""

    def folders(self):
        return [f for f in sorted(os.listdir(settings.TOOLS_DIR)) if os.path.isfile(os.path.join(settings.TOOLS_DIR, f, 'tool.py'))]

    def test_every_folder_registers_one_tool(self):
        names = [tool.name for tool in registry.builtin_tools()]
        for folder in self.folders():
            self.assertIn(folder.lower(), [name.lower() for name in names], folder)

    def test_tool_files_exist(self):
        for tool in registry.builtin_tools():
            if 'run' not in vars(tool) and 'build_job' not in vars(tool):   # the default job runs the tool's script
                self.assertTrue(os.path.isfile(tool.script_path), f'{tool.name}: missing {tool.script}')
                self.assertTrue(os.access(tool.script_path, os.X_OK), f'{tool.name}: {tool.script} is not executable')
            get_template(tool.template)   # submission page
            self.assertIn(tool.category, CATEGORY_KEYS, tool.name)

    def test_conda_environments_are_named_after_their_file(self):
        files = []
        for folder in self.folders():
            install = os.path.join(settings.TOOLS_DIR, folder, 'install')
            for file in os.listdir(install) if os.path.isdir(install) else []:
                files.append(file)
                if file.startswith('server_') and file.endswith('.yml'):
                    with open(os.path.join(install, file)) as handle:
                        first = next(line for line in handle if line.strip() and not line.startswith('#'))
                    self.assertEqual(first.strip(), f'name: {file[:-4]}', f'{folder}/install/{file}')
        self.assertEqual(len(files), len(set(files)), 'install files of different tools must have different names (the Dockerfiles copy them into one folder)')

    def test_example_files_exist(self):
        for tool in registry.builtin_tools():
            if tool.example:
                self.assertGreaterEqual(len(tool.example_files()), len(tool.example), f'{tool.name}: example files not found')

    def test_names_are_unique_and_not_reserved(self):
        names = [tool.name for tool in registry.builtin_tools()]
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(set(names) & registry.reserved_names())


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ToolkitPagesTest(TestCase):
    def enabled_tools(self):
        return [tool for tool in registry.builtin_tools() if tool_catalog.is_enabled(tool.name)]

    def test_off_by_default_tools_are_not_reachable(self):
        self.assertFalse(tool_catalog.is_enabled('basalt'))   # needs 128 GB RAM: off until an administrator switches it on
        self.assertEqual(self.client.get(registry.get('basalt').url).status_code, 404)

    def test_every_tool_page_renders(self):
        for tool in self.enabled_tools():
            response = self.client.get(tool.url)
            self.assertEqual(response.status_code, 200, tool.name)
            self.assertContains(response, 'multi-file-btn' if hasattr(tool.form, 'MAX_GENOMES') else '<form', msg_prefix=tool.name)

    def test_home_page_and_menu_list_the_tools(self):
        response = self.client.get(reverse('baclab:index'))
        self.assertEqual(response.status_code, 200)
        for tool in self.enabled_tools():
            self.assertContains(response, tool.url, msg_prefix=tool.name)
            self.assertContains(response, escape(tool.title), msg_prefix=tool.name)

    def test_switched_off_tool_disappears_and_returns_404(self):
        tool = registry.get('padloc')
        ToolSetting.objects.create(tool='padloc', enabled=False)
        self.assertNotContains(self.client.get(reverse('baclab:index')), tool.url)
        self.assertEqual(self.client.get(tool.url).status_code, 404)

    def test_environment_variable_beats_the_admin_switch(self):
        ToolSetting.objects.create(tool='padloc', enabled=False)
        with patch.dict(os.environ, {'ENABLE_TOOL_padloc': '1'}):
            self.assertTrue(tool_catalog.is_enabled('padloc'))
        self.assertFalse(tool_catalog.is_enabled('padloc'))

    def test_example_data_download(self):
        response = self.client.get(reverse('baclab:download_example_data', args=['padloc']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse('baclab:download_example_data', args=['nosuchtool'])).status_code, 404)

    def test_invalid_upload_is_rejected(self):
        tool = registry.get('padloc')
        bad = SimpleUploadedFile('genome.txt', b'>x\nACGT\n')
        response = self.client.post(tool.url, {'genomes': bad})
        self.assertEqual(response.status_code, 400)


class JobTestMixin:
    """Runs jobs for real: temp job folders, the Celery task in-process once the request's transaction commits."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = self.temp.name
        self.settings = override_settings(UPLOAD_DIR=f'{root}/uploads', DOWNLOAD_DIR=f'{root}/downloads', RESULTS_DIR=f'{root}/results',
                                          CUSTOM_TOOLS_DIR=f'{root}/custom_tools', CUSTOM_ENVS_DIR=f'{root}/custom_envs',
                                          LOCAL_DEBUG_MODE=False, CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
        self.settings.enable()
        # the example/test databases do not exist here; the tools' scripts are replaced or fake anyway
        self.no_missing_db = patch('baclab.db_status.missing_for_tool', return_value=[])
        self.no_missing_db.start()
        for folder in ('uploads', 'downloads', 'results'):
            os.makedirs(f'{root}/{folder}')

    def tearDown(self):
        self.no_missing_db.stop()
        self.settings.disable()
        self.temp.cleanup()

    def submit(self, url, files, data=None):
        """POST to a tool page; the Celery task runs in-process once the request's transaction commits."""
        def run_now(args, task_id):
            run_job.apply(args=args, task_id=task_id)

        with patch('baclab.tool_views.run_job.apply_async', side_effect=lambda args, task_id, **kwargs: run_now(args, task_id)):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, {'genomes': files, **(data or {})})
        self.assertEqual(response.status_code, 200, response.content[:300])
        return JobRecord.objects.latest('queued_at')


class ToolkitJobTest(JobTestMixin, TestCase):
    """A job of a folder tool: submitted through the page, run by run_job, shown on the results page."""

    def test_padloc_job_end_to_end(self):
        tool = registry.get('padloc')

        def fake_run(ctx):
            with open(os.path.join(ctx['output_dir'], 'padloc_results.csv'), 'w') as handle:
                handle.write('genome,system.number,seqid,system,target.name,protein.name,full.seq.E.value,domain.iE.value,target.coverage,hmm.coverage,start,end,strand\n')
                handle.write('g1,1,c1,CBASS_I,t1,p1,1e-5,1e-4,0.9,0.9,10,200,+\n')

        files = [SimpleUploadedFile('g1.fasta', b'>c1\nACGTACGT\n')]
        with patch.object(tool, 'run', side_effect=fake_run):
            job = self.submit(tool.url, files)
        self.assertEqual(job.status, 'finished', job.error_message)
        self.assertTrue(os.path.exists(os.path.join(settings.RESULTS_DIR, f'{job.job_id}.zip')))
        page = self.client.get(reverse('baclab:results'), {'job_id': job.job_id})
        self.assertContains(page, 'CBASS_I')
        self.assertContains(page, 'Please cite')   # the citation box comes from the Tool

    def test_failed_script_marks_job_failed_and_results_page_explains(self):
        tool = registry.get('padloc')
        files = [SimpleUploadedFile('g1.fasta', b'>c1\nACGT\n')]
        # the script exists but its conda environment does not: the job must fail cleanly, not crash the worker
        with patch.object(tool, 'run', side_effect=RuntimeError('boom')), patch('baclab.views.send_failure_email_admin') as mail:
            job = self.submit(tool.url, files)
        self.assertEqual(job.status, 'failed')
        mail.assert_called_once()
        page = self.client.get(reverse('baclab:results'), {'job_id': job.job_id})
        self.assertContains(page, 'did not produce any results')


class CustomToolTest(JobTestMixin, TestCase):
    """Tools added in the admin run real bash scripts."""

    def make_tool(self, **overrides):
        values = dict(name='wordcount', title='Word count', category='qc', enabled=True, accepted_extensions='.txt,.fa', min_files=1, max_files=3,
                      script='for f in "$INPUT_DIR"/*; do printf "%s\\t%s\\n" "$(basename "$f")" "$(grep -c . "$f")" >> "$OUTPUT_DIR/counts.tsv"; done\n',
                      result_kind='table', result_file='counts.tsv', result_title='Line counts', databases='')
        values.update(overrides)
        row = CustomTool(**values)
        row.full_clean()
        row.save()
        return row

    def test_custom_tool_job_end_to_end(self):
        row = self.make_tool()
        self.assertIn('Word count', self.client.get(reverse('baclab:index')).content.decode())
        page = self.client.get(reverse('baclab:custom_tool', args=[row.name]))
        self.assertContains(page, 'Word count')
        self.assertContains(page, '.txt')

        job = self.submit(reverse('baclab:custom_tool', args=[row.name]), [SimpleUploadedFile('a.txt', b'one\ntwo\n'), SimpleUploadedFile('b.txt', b'x\n')])
        self.assertEqual(job.status, 'finished', job.error_message)
        results = self.client.get(reverse('baclab:results'), {'job_id': job.job_id})
        self.assertContains(results, 'a.txt')
        self.assertContains(results, 'Line counts')

    def test_custom_tool_parameters_reach_the_script_and_are_checked(self):
        row = self.make_tool(
            name='params', title='Params',
            script='echo "$PARAM_MODE $PARAM_LEVEL $PARAM_STRICT" > "$OUTPUT_DIR/out.txt"\n',
            result_kind='files', result_file='',
            parameters='[{"name": "mode", "label": "Mode", "type": "choice", "choices": ["fast", "slow"], "default": "fast"},'
                       ' {"name": "level", "label": "Level", "type": "int", "min": 1, "max": 5, "default": 2},'
                       ' {"name": "strict", "label": "Strict", "type": "bool"}]')
        url = reverse('baclab:custom_tool', args=[row.name])
        files = [SimpleUploadedFile('a.txt', b'x\n')]
        # an unknown choice falls back to the default, a number is clamped, an unchecked box means "no"
        job = self.submit(url, files, {'param_mode': 'rm -rf /', 'param_level': '99'})
        self.assertEqual(job.status, 'finished', job.error_message)
        with open(os.path.join(settings.DOWNLOAD_DIR, job.job_id, 'out.txt')) as handle:
            self.assertEqual(handle.read().strip(), 'fast 5 no')

    def test_failing_custom_script_fails_the_job(self):
        row = self.make_tool(name='failing', title='Failing', script='echo oops >&2\nexit 3\n')
        with patch('baclab.views.send_failure_email_admin'):
            job = self.submit(reverse('baclab:custom_tool', args=[row.name]), [SimpleUploadedFile('a.txt', b'x\n')])
        self.assertEqual(job.status, 'failed')
        self.assertIn('oops', str(job.error_log))

    def test_disabled_custom_tool_is_hidden(self):
        row = self.make_tool(enabled=False)
        self.assertEqual(self.client.get(reverse('baclab:custom_tool', args=[row.name])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('baclab:index')), 'Word count')

    def test_editing_a_tool_is_picked_up_without_restart(self):
        row = self.make_tool()
        self.assertEqual(registry.get(row.name).title, 'Word count')
        row.title = 'Line counter'
        row.save()
        self.assertEqual(registry.get(row.name).title, 'Line counter')

    def test_wrapper_script_activates_environment_and_exports_parameters(self):
        params = custom.parse_parameters('[{"name": "mode", "type": "choice", "choices": ["a"], "default": "a"}]')
        text = custom.wrapper_script('mytool', 'echo hi\n', True, params)
        self.assertIn('conda activate', text)
        self.assertIn('export PARAM_MODE="${4}"', text)
        self.assertNotIn('conda activate', custom.wrapper_script('mytool', 'echo hi\n', False, params))


class CustomToolValidationTest(TestCase):
    def valid(self, **overrides):
        values = dict(name='okname', title='T', category='qc', accepted_extensions='.fa', min_files=1, max_files=2, script='echo hi')
        values.update(overrides)
        return CustomTool(**values)

    def test_valid_row_passes(self):
        self.valid().full_clean()

    def test_bad_values_are_rejected(self):
        for overrides in (
            {'name': 'Bad-Name'}, {'name': 'x'}, {'name': 'padloc'}, {'name': 'blast'}, {'name': 'admin'}, {'name': 'results'},
            {'accepted_extensions': 'fasta'}, {'accepted_extensions': ''}, {'min_files': 5, 'max_files': 2}, {'script': '   '},
            {'parameters': 'not json'}, {'parameters': '[{"name": "Bad Name"}]'},
            {'parameters': '[{"name": "m", "type": "choice", "choices": ["a b"]}]'},
            {'result_kind': 'table', 'result_file': ''}, {'result_file': '../etc/passwd', 'result_kind': 'table'},
            {'result_separator': 'x'}, {'environment_yml': 'just some text'},
        ):
            with self.assertRaises(ValidationError, msg=str(overrides)):
                self.valid(**overrides).full_clean()

    def test_name_cannot_change_after_creation(self):
        row = self.valid()
        row.full_clean()
        row.save()
        row.name = 'renamed'
        with self.assertRaises(ValidationError):
            row.full_clean()


class MissingDatabaseTest(TestCase):
    def test_page_warns_and_submission_is_refused_when_database_is_missing(self):
        tool = registry.get('padloc')
        with patch('baclab.db_status.missing_for_tool', return_value=['PADLOC-DB']):
            self.assertContains(self.client.get(tool.url), 'not ready yet')
            response = self.client.post(tool.url, {'genomes': SimpleUploadedFile('g.fasta', b'>c\nAC\n')})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'PADLOC-DB', response.content)
        self.assertFalse(JobRecord.objects.exists())


class AdminTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_superuser('boss', 'boss@example.com', 'pw')
        self.client.login(username='boss', password='pw')

    def test_system_status_page(self):
        response = self.client.get(reverse('admin:system_status'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PADLOC-DB')
        self.assertContains(response, 'BLAST')

    def test_admin_index_links_to_status_and_tool_form(self):
        self.assertContains(self.client.get(reverse('admin:index')), reverse('admin:system_status'))

    def test_add_tool_through_admin_form_and_build_environment_action(self):
        data = {'name': 'viaadmin', 'title': 'Via admin', 'category': 'qc', 'description': '', 'accepted_extensions': '.fa', 'min_files': 1, 'max_files': 2,
                'parameters': '', 'script': 'echo hi > "$OUTPUT_DIR/x.txt"', 'environment_yml': 'name: x\ndependencies:\n  - python', 'databases': '',
                'result_kind': 'files', 'result_file': '', 'result_title': '', 'result_separator': 'tab', 'keep_outputs': '', 'citation_text': '', 'citation_url': ''}
        response = self.client.post(reverse('admin:baclab_customtool_add'), data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['adminform'].form.errors)
        row = CustomTool.objects.get(name='viaadmin')
        self.assertEqual(row.env_status, 'pending')
        self.assertFalse(row.enabled)

        with patch('baclab.admin.build_custom_tool_environment.delay') as build, self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('admin:baclab_customtool_changelist'), {'action': 'build_environment', '_selected_action': [row.pk]})
        build.assert_called_once_with(row.pk)

        self.client.post(reverse('admin:baclab_customtool_changelist'), {'action': 'enable_tools', '_selected_action': [row.pk]})
        row.refresh_from_db()
        self.assertFalse(row.enabled)   # refused: the environment is not built yet


class ToolsMenuTest(TestCase):
    def test_menu_has_a_column_per_category_with_sorted_tools(self):
        response = self.client.get(reverse('baclab:index'))
        menu = response.context['tool_menu']
        self.assertGreaterEqual(len(menu), 5)
        for column in menu:
            titles = [tool['title'].lower() for tool in column['tools']]
            self.assertEqual(titles, sorted(titles))
        flat = {tool['title'] for column in menu for tool in column['tools']}
        self.assertIn('PADLOC (antiviral defence)', flat)   # tool folder
        self.assertIn('BLAST', flat)                         # hand-written tool
        self.assertNotIn('BASALT (metagenome binning)', flat)   # switched off by default
        self.assertContains(response, 'tools-column-title')

    def test_guides_page_and_no_template_leftovers_on_home(self):
        guides = self.client.get(reverse('baclab:guides'))
        self.assertEqual(guides.status_code, 200)
        self.assertContains(guides, 'How to use')
        self.assertContains(guides, 'How to use PADLOC')   # a tool folder's guide appears too
        home = self.client.get(reverse('baclab:index')).content.decode()
        self.assertNotIn('dyn_tools', home)
        self.assertNotIn('How to use Snippy', home)   # the guides moved to their own page


class ScreenPipelineTest(TestCase):
    """The genome screen runs other tools' scripts in turn and merges their results; here with fake scripts."""

    def test_pipeline_merges_steps_and_survives_a_failing_one(self):
        import importlib.util
        from baclab.toolkit import registry
        tool = registry.get('screen')
        with tempfile.TemporaryDirectory() as root:
            for relative, body in {
                'mlst/mlst_script.sh': 'printf "%s\\tecoli\\t10\\tadk(1)\\n" "$1/genome_1.fasta" > "$2/mlst_results.tsv"\n',
                'amrfinderplus/amrfinderplus_script.sh': 'printf "Gene symbol\\nblaTEM\\nsul1\\n" > "$2/genome_1_amrfinder.tsv"\n',
                'checkm2/checkm2_script.sh': 'echo broken >&2; exit 3\n',
            }.items():
                path = os.path.join(root, relative)
                os.makedirs(os.path.dirname(path))
                with open(path, 'w') as handle:
                    handle.write('#!/bin/bash\n' + body)
            out = os.path.join(root, 'job', 'output')
            os.makedirs(os.path.join(out, 'input'))
            with open(os.path.join(out, 'input', 'genome_1.fasta'), 'w') as handle:
                handle.write('>c1\nGGCC\n>c2\nATAT\nAT\n')
            with open(os.path.join(out, 'run_parameters.txt'), 'w') as handle:
                handle.write('step_mlst:on\nstep_amr:on\nstep_checkm2:on\n')
            with override_settings(TOOLS_DIR=root, DATABASES_DIR=root):
                with patch('baclab.db_catalog.is_installed', return_value=True):
                    tool.run({'job_id': 'screen-x', 'output_dir': out, 'downloads_dir': '', 'job_options': {}, 'command': []})
            profile = open(os.path.join(out, 'genome_profile.tsv')).read().splitlines()
            self.assertEqual(profile[0].split('\t')[:5], ['genome', 'size_bp', 'contigs', 'N50', 'GC_percent'])
            row = dict(zip(profile[0].split('\t'), profile[1].split('\t')))
            self.assertEqual((row['size_bp'], row['contigs'], row['MLST_ST'], row['AMR_genes']), ('10', '2', '10', '2'))
            self.assertNotIn('completeness_percent', row)   # that step failed
            status = open(os.path.join(out, 'step_status.tsv')).read()
            self.assertIn('checkm2\tCheckM2 completeness / contamination\tfailed', status)

    def test_all_steps_failing_fails_the_job(self):
        from baclab.toolkit import registry
        tool = registry.get('screen')
        with tempfile.TemporaryDirectory() as root:
            out = os.path.join(root, 'output')
            os.makedirs(os.path.join(out, 'input'))
            with open(os.path.join(out, 'input', 'g.fasta'), 'w') as handle:
                handle.write('>c\nAC\n')
            with override_settings(TOOLS_DIR=root), patch('baclab.db_catalog.is_installed', return_value=True):
                with self.assertRaises(RuntimeError):
                    tool.run({'job_id': 'screen-y', 'output_dir': out, 'downloads_dir': '', 'job_options': {}, 'command': []})


class FirstGenerationDatabaseGateTest(TestCase):
    def test_tool_with_a_missing_database_warns_and_refuses(self):
        with patch('baclab.db_status.missing_for_tool', return_value=['Kraken2 index']):
            page = self.client.get(reverse('baclab:kraken2'))
            self.assertContains(page, 'not ready yet')
            response = self.client.post(reverse('baclab:kraken2'), {'use_example_data': 'true', 'type': 'file'})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Kraken2 index', response.content)

    def test_tools_with_alternative_modes_are_not_gated(self):
        with patch('baclab.db_status.missing_for_tool', return_value=['something']):
            self.assertNotContains(self.client.get(reverse('baclab:cblaster')), 'not ready yet')


class AnnotationResultsPageTest(TestCase):
    def test_annotation_results_list_the_files_of_the_archive(self):
        import zipfile
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(f'{root}/downloads/annotationPipeline-t1')
            with zipfile.ZipFile(f'{root}/results/annotationPipeline-t1.zip', 'w') if os.makedirs(f'{root}/results') is None else None as archive:
                archive.writestr('genome.fasta/bakta/genome.gbff', 'LOCUS')
                archive.writestr('input/genome.fasta', '>x')
            JobRecord.objects.create(job_id='annotationPipeline-t1', job_type='annotationPipeline', status='finished')
            with override_settings(DOWNLOAD_DIR=f'{root}/downloads', RESULTS_DIR=f'{root}/results'):
                page = self.client.get(reverse('baclab:results'), {'job_id': 'annotationPipeline-t1'})
        self.assertContains(page, 'genome.fasta/bakta/genome.gbff')
        self.assertNotContains(page, 'input/genome.fasta')


class ToolOptionsTest(TestCase):
    def test_file_only_tool_refuses_pasted_sequences(self):
        response = self.client.post(reverse('baclab:mlst'), {'type': 'fasta', 'fasta': '>x\nACGT\n'})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'only accepts file uploads', response.content)

    def test_tool_that_takes_pasted_sequences_still_accepts_them(self):
        with patch('baclab.tool_views.create_job', return_value='blast-test') as create:
            response = self.client.post(reverse('baclab:blast'), {'type': 'fasta', 'fasta': '>x\nACGT\n', 'blast_type': 'blastn'})
        self.assertEqual(response.status_code, 200)
        create.assert_called_once()

    def test_exclude_leaves_working_files_out_of_the_results(self):
        tool = registry.get('checkm')
        with tempfile.TemporaryDirectory() as root:
            out, down = os.path.join(root, 'out'), os.path.join(root, 'down')
            for path in ('bins/a.txt', 'storage/b.txt', 'checkm_results.tsv'):
                os.makedirs(os.path.dirname(os.path.join(out, path)), exist_ok=True)
                open(os.path.join(out, path), 'w').write('x')
            tool.post_process({'output_dir': out, 'downloads_dir': down})
            self.assertEqual(sorted(os.listdir(down)), ['checkm_results.tsv'])

    def test_taxonomy_finder_is_switched_with_the_taxonomy_key(self):
        tool = registry.get('taxonomyfinder')
        ToolSetting.objects.create(tool='taxonomy', enabled=False)
        self.assertEqual(self.client.get(tool.url).status_code, 404)
        self.assertNotContains(self.client.get(reverse('baclab:index')), tool.url)

    def test_every_job_type_of_the_first_release_is_a_tool_folder(self):
        for name in ('abricate', 'amrfinderplus', 'ani', 'annotationPipeline', 'blast', 'cblaster', 'checkm', 'checkm2', 'fastaai', 'fastp', 'gecco',
                     'genomemining', 'gubbins', 'kraken2', 'mlst', 'mobsuite', 'multiqc', 'panaroo', 'phylogeny', 'plasmidfinder', 'quast', 'snippy',
                     'spades', 'taxonomyfinder'):
            with self.subTest(tool=name):
                self.assertIsNotNone(registry.get(name))


class PrerunExamplesTest(TestCase):
    def test_command_queues_the_examples_once(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as root, override_settings(DOWNLOAD_DIR=f'{root}/d', RESULTS_DIR=f'{root}/r', UPLOAD_DIR=f'{root}/u'):
            with patch('baclab.tool_views.run_job') as run, self.captureOnCommitCallbacks(execute=True):
                call_command('prerun_examples', '--tool', 'mlst', stdout=open(os.devnull, 'w'))
                call_command('prerun_examples', '--tool', 'mlst', stdout=open(os.devnull, 'w'))
            self.assertEqual(run.apply_async.call_count, 1)
        self.assertTrue(JobRecord.objects.filter(job_id='mlst-EXAMPLE').exists())


class ExampleButtonTest(TestCase):
    def test_every_tool_with_example_data_offers_the_example_results(self):
        for tool in registry.builtin_tools():
            if not tool.example:
                continue
            with self.subTest(tool=tool.name):
                page = self.client.get(tool.url)
                self.assertContains(page, reverse('baclab:example_results', args=[tool.name]), msg_prefix=tool.name)
                self.assertContains(page, 'View Example Results')

    def test_only_basalt_has_no_example(self):
        """BASALT needs 128 GB of RAM (it is off by default): every other tool ships example data."""
        self.assertEqual({tool.name for tool in registry.builtin_tools() if not tool.example}, {'basalt'})

    def test_example_files_exist_for_every_tool(self):
        for tool in registry.builtin_tools():
            if tool.example:
                with self.subTest(tool=tool.name):
                    self.assertTrue(tool.example_files(), f'{tool.name}: example files not found')


class ScreenExampleTest(TestCase):
    def test_page_has_the_example_button_and_the_example_files_exist(self):
        page = self.client.get(reverse('baclab:screen'))
        self.assertContains(page, 'Load Example Data')
        self.assertContains(page, 'use_example_data')
        tool = registry.get('screen')
        self.assertEqual(len(tool.example_files()), 3)      # every example file is really there
        self.assertEqual(tool.example_post['step_mlst'], 'on')


class GenomesPerJobTest(TestCase):
    def test_limit_comes_from_the_setting(self):
        from django.conf import settings
        for name in ('screen', 'defensefinder', 'padloc', 'genovi', 'rrefinder'):
            self.assertEqual(registry.get(name).form.MAX_GENOMES, settings.MAX_GENOMES_PER_JOB, name)
        self.assertContains(self.client.get(reverse('baclab:screen')), f'maxFiles: {settings.MAX_GENOMES_PER_JOB}')
