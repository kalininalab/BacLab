import os
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from baclab.models import JobRecord, InhouseStrain, CustomDatabase
from baclab.views import run_job
from baclab.tasks import process_inhouse_strain, build_custom_database


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class ModularToolsTestCase(TestCase):
    """
    Verification test suite for refactored modular tools and Celery tasks.
    Verifies that jobs and tasks transition status cleanly:
      - JobRecord: queued -> running -> finished
      - InhouseStrain: pending -> running -> completed
      - CustomDatabase: pending -> building -> ready
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_dir = os.path.join(self.temp_dir.name, "upload")
        self.output_dir = os.path.join(self.temp_dir.name, "output")
        self.results_dir = os.path.join(self.temp_dir.name, "results")
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_mock_job_dict(self, job_id, command="echo mock", options=None):
        return {
            "jobId": job_id,
            "command": command,
            "uploadDir": self.upload_dir,
            "outputDir": self.output_dir,
            "resultsDir": self.results_dir,
            "options": options or {},
        }

    @patch("subprocess.run")
    @patch("baclab.views.FileManager.zip_directory")
    def test_run_job_annotation_pipeline(self, mock_zip, mock_subprocess):
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        job_id = "annotationPipeline-test-01"
        jr = JobRecord.objects.create(job_id=job_id, job_type="annotation", status="queued")

        self.assertEqual(jr.status, "queued")
        self.assertIsNone(jr.started_at)
        self.assertIsNone(jr.finished_at)

        job_dict = self._create_mock_job_dict(
            job_id,
            options={"prokka": True, "antismash": False, "bakta": False}
        )

        with patch("baclab.tools.prokka.ProkkaTool.execute") as mock_prokka_exec:
            run_job.apply(args=[job_dict])
            mock_prokka_exec.assert_called_once()

        jr.refresh_from_db()
        self.assertEqual(jr.status, "finished")
        self.assertIsNotNone(jr.started_at)
        self.assertIsNotNone(jr.finished_at)
        self.assertIsNotNone(jr.duration)

    def test_run_job_of_the_tools_with_their_own_folder(self):
        """Every tool that lives in tools/<name>/ goes through the same steps: the script runs, post-processing runs once, the job finishes."""
        from baclab.toolkit import registry
        names = ['abricate', 'amrfinderplus', 'ani', 'blast', 'checkm', 'checkm2', 'fastaai', 'fastp', 'gecco', 'genomemining', 'gubbins', 'kraken2', 'mlst',
                 'mobsuite', 'multiqc', 'panaroo', 'phylogeny', 'plasmidfinder', 'quast', 'snippy', 'spades', 'taxonomyfinder']
        for name in names:
            with self.subTest(tool=name):
                job_id = f"{name}-test-01"
                jr = JobRecord.objects.create(job_id=job_id, job_type=name, status="queued")
                self.assertIsNotNone(registry.get(name))
                job_dict = self._create_mock_job_dict(job_id, command=f"{name}_script.sh")
                with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="done", stderr="")) as run, \
                        patch("baclab.views.zip_folder"), patch.object(registry.get(name), "post_process") as post:
                    run_job.apply(args=[job_dict])
                jr.refresh_from_db()
                self.assertEqual(jr.status, "finished")
                run.assert_called()
                post.assert_called_once()

    @patch("os.makedirs")
    @patch("shutil.copy2")
    @patch("baclab.tools.prokka.ProkkaTool.run_single_genome")
    @patch("baclab.tools.prokka.ProkkaTool.post_process_strain")
    @patch("baclab.tools.antismash.AntismashTool.run_single_genome")
    @patch("baclab.tools.antismash.AntismashTool.copy_to_antismash_db")
    @patch("baclab.tools.taxonomy.TaxonomyTool.run_gtdbtk_inhouse")
    def test_process_inhouse_strain_success(
        self,
        mock_gtdbtk,
        mock_antismash_copy,
        mock_antismash_run,
        mock_prokka_post,
        mock_prokka_run,
        mock_copy2,
        mock_makedirs,
    ):
        mock_gtdbtk.return_value = "d__Bacteria;p__Pseudomonadota"
        fasta_file = SimpleUploadedFile("strain_01.fasta", b">seq1\nATCGATCG\n")
        strain = InhouseStrain.objects.create(
            strain_id="strain-mod-01",
            genome_fasta=fasta_file,
            run_prokka=True,
            run_antismash=True,
            run_gtdbtk=True,
            status="pending",
        )

        self.assertEqual(strain.status, "pending")

        with tempfile.TemporaryDirectory() as temp_db_dir:
            tsv_path = os.path.join(temp_db_dir, "Inhouse_strains.tsv")
            real_join = os.path.join
            with patch("baclab.tasks.os.path.join", side_effect=lambda *args: tsv_path if args and args[-1] == "Inhouse_strains.tsv" else real_join(*args)):
                process_inhouse_strain.apply(args=["strain-mod-01"])

        strain.refresh_from_db()
        self.assertEqual(strain.status, "completed")
        self.assertEqual(strain.taxonomy, "d__Bacteria;p__Pseudomonadota")
        self.assertEqual(strain.error_message, "")
        mock_prokka_run.assert_called_once()
        mock_antismash_run.assert_called_once()
        mock_gtdbtk.assert_called_once()

    def test_build_custom_database_of_the_tools_that_take_one(self):
        """The admin's custom databases are built by the tool the database is for (blast, cblaster, genomemining, phylogeny)."""
        from baclab.toolkit import registry
        for name in ('blast', 'cblaster', 'genomemining', 'phylogeny'):
            with self.subTest(tool=name):
                db = CustomDatabase.objects.create(db_name=f"mod_test_{name}_db", tool=name,
                                                   input_files=SimpleUploadedFile(f"{name}.fasta", b">seq1\nATCG\n"), status="pending")
                with patch.object(registry.get(name), "build_custom_database") as build:
                    build_custom_database.apply(args=[db.id])
                db.refresh_from_db()
                self.assertEqual(db.status, "ready")
                build.assert_called_once()

    def test_custom_database_for_a_tool_that_takes_none_fails_with_a_message(self):
        db = CustomDatabase.objects.create(db_name="mod_test_none", tool="mlst", input_files=SimpleUploadedFile("x.fasta", b">a\nA\n"), status="pending")
        build_custom_database.apply(args=[db.id])
        db.refresh_from_db()
        self.assertEqual(db.status, "failed")
        self.assertIn("does not take custom databases", db.error_message)

    @patch("baclab.views.run_job.apply_async")
    def test_cblaster_submission_with_example_data(self, mock_apply_async):
        from django.test import Client
        client = Client()

        with tempfile.TemporaryDirectory() as temp_upload:
            with override_settings(UPLOAD_DIR=temp_upload):
                with self.captureOnCommitCallbacks(execute=True):   # the job is queued once the request's transaction commits
                    response = client.post(
                        reverse('baclab:cblaster'),
                        data={
                            'use_example_data': 'true',
                            'mode': 'local',
                            'database': 'mibig_4.0',
                            'dmnd_sensitivity': 'fast',
                            'maximum_hits': '100',
                            'find_intermediate_genes': 'on',
                            'maximum_distance': '20000',
                            'maximum_clusters': '100',
                            'maximum_evalue': '0.01',
                            'minimum_identitiy': '30',
                            'minimum_query_coverage': '50',
                            'maximum_intergenicgap': '20000',
                            'percentage': '50',
                            'minimum_uniquequeryhits': '3',
                            'minimum_hitsinclusters': '3',
                            'decimals_st': '4',
                            'decimals_bt': '4',
                            'key_function': 'len',
                            'hit_attribute': 'identity',
                        }
                    )

                self.assertEqual(response.status_code, 200)
                mock_apply_async.assert_called_once()
                job_args = mock_apply_async.call_args[1]['args'][0]
                job_id = job_args['jobId']

                # Verify JobRecord is created
                jr = JobRecord.objects.get(job_id=job_id)
                self.assertEqual(jr.status, 'queued')
                self.assertEqual(jr.job_type, 'cblaster')

                # Verify example file was copied to input path
                input_dir = os.path.join(temp_upload, job_id, 'input')
                self.assertTrue(os.path.exists(input_dir))
                files = os.listdir(input_dir)
                self.assertTrue(any('example' in f or f.endswith('.fasta') for f in files))

    def test_cblaster_template_renders_example_button(self):
        from django.test import Client
        client = Client()
        response = client.get(reverse('baclab:cblaster'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Load Example Data')
        self.assertContains(response, 'use_example_data')
        self.assertContains(response, 'loadExampleData()')

