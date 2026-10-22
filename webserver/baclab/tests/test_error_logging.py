import sys
import os
import subprocess
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from baclab.models import JobRecord, InhouseStrain
from baclab.error_utils import format_error_log
from baclab.toolkit import registry as toolkit_registry
from baclab.views import mark_job_status, run_job
from baclab.tasks import process_inhouse_strain
from baclab.tools.antismash import AntismashError


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class ErrorLoggingTestCase(TestCase):
    """
    Verification test suite for structured JSON error logging across error_utils,
    JobRecord.error_log, and InhouseStrain.error_log.
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

    def test_format_error_log_basic(self):
        try:
            raise ValueError("Test value error")
        except Exception as e:
            err_log = format_error_log(e, step="test_step", tool_name="test_tool")

        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "test_tool")
        self.assertEqual(err_log["step"], "test_step")
        self.assertEqual(err_log["error_type"], "ValueError")
        self.assertEqual(err_log["error_message"], "Test value error")
        self.assertIn("ValueError: Test value error", err_log["traceback"])
        self.assertEqual(err_log["stdout"], "")
        self.assertEqual(err_log["stderr"], "")
        self.assertIsNone(err_log["returncode"])

    def test_format_error_log_called_process_error(self):
        cpe = subprocess.CalledProcessError(
            returncode=1,
            cmd=["test_cmd"],
            output=b"sample stdout",
            stderr=b"sample stderr"
        )
        err_log = format_error_log(cpe, step="subprocess_step", tool_name="blast")

        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "blast")
        self.assertEqual(err_log["error_type"], "CalledProcessError")
        self.assertEqual(err_log["step"], "subprocess_step")
        self.assertEqual(err_log["stdout"], "sample stdout")
        self.assertEqual(err_log["stderr"], "sample stderr")
        self.assertEqual(err_log["returncode"], 1)

    def test_format_error_log_none_exception(self):
        err_log = format_error_log(exc=None, step="init", tool_name="prokka")
        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "prokka")
        self.assertEqual(err_log["step"], "init")
        self.assertEqual(err_log["error_type"], "UnknownError")
        self.assertEqual(err_log["error_message"], "")
        self.assertEqual(err_log["traceback"], "")

    def test_mark_job_status_saves_error_log(self):
        jr = JobRecord.objects.create(
            job_id="test-job-101",
            job_type="cblaster",
            status="queued"
        )
        mock_log = {
            "timestamp": "2026-08-13T14:00:00Z",
            "tool_name": "cblaster",
            "step": "cblaster_search",
            "error_type": "RuntimeError",
            "error_message": "Execution failed",
            "traceback": "Traceback info...",
            "stdout": "out",
            "stderr": "err",
            "returncode": 2
        }
        mark_job_status("test-job-101", "failed", error_message="Execution failed", error_log=mock_log)
        jr.refresh_from_db()

        self.assertEqual(jr.status, "failed")
        self.assertEqual(jr.error_message, "Execution failed")
        self.assertEqual(jr.error_log, mock_log)

    @patch("baclab.views._handle_job_failure")
    @patch("subprocess.run")
    def test_run_job_subprocess_failure_populates_error_log(self, mock_subprocess, mock_handle_failure):
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=2,
            cmd=["blastn"],
            output=b"blast standard output",
            stderr=b"blast error log output"
        )
        job_id = "blast-err-01"
        jr = JobRecord.objects.create(job_id=job_id, job_type="blast", status="queued")

        job_dict = self._create_mock_job_dict(job_id, command="blastn -query bad.fasta")
        run_job.apply(args=[job_dict])

        jr.refresh_from_db()
        self.assertEqual(jr.status, "failed")
        self.assertIsNotNone(jr.error_log)
        self.assertIsInstance(jr.error_log, dict)

        err_log = jr.error_log
        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "blast")
        self.assertEqual(err_log["step"], "job_execution")
        self.assertEqual(err_log["error_type"], "CalledProcessError")
        self.assertEqual(err_log["returncode"], 2)
        self.assertEqual(err_log["stdout"], "blast standard output")
        self.assertEqual(err_log["stderr"], "blast error log output")

    @patch("baclab.views._handle_job_failure")
    def test_run_job_antismash_error_populates_error_log(self, mock_handle_failure):
        job_id = "annotationPipeline-err-01"
        jr = JobRecord.objects.create(job_id=job_id, job_type="annotation", status="queued")

        job_dict = self._create_mock_job_dict(job_id, options={"antismash": True})
        with patch.object(toolkit_registry.get("annotationPipeline"), "run", side_effect=AntismashError("antiSMASH failed to produce GBK files")):
            run_job.apply(args=[job_dict])

        jr.refresh_from_db()
        self.assertEqual(jr.status, "failed")
        self.assertIsNotNone(jr.error_log)

        err_log = jr.error_log
        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "antismash")
        self.assertEqual(err_log["step"], "antismash_execution")
        self.assertEqual(err_log["error_type"], "AntismashError")
        self.assertEqual(err_log["error_message"], "antiSMASH failed to produce GBK files")

    @patch("baclab.views._handle_job_failure")
    @patch("subprocess.run")
    def test_run_job_cblaster_no_results_error_populates_error_log(self, mock_subproc, mock_handle_failure):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")
        errors = sys.modules["baclab_tool_cblaster"]
        job_id = "cblaster-err-01"
        jr = JobRecord.objects.create(job_id=job_id, job_type="cblaster", status="queued")

        job_dict = self._create_mock_job_dict(job_id, command="cblaster search")
        with patch.object(toolkit_registry.get("cblaster"), "post_process", side_effect=errors.NoResults("cblaster_search_folder")):
            run_job.apply(args=[job_dict])

        jr.refresh_from_db()
        self.assertEqual(jr.status, "failed")
        self.assertIn("did not yield any hits", jr.error_message)
        err_log = jr.error_log
        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "cblaster")
        self.assertEqual(err_log["error_type"], "NoResults")
        self.assertEqual(mock_handle_failure.call_args[0][3], f"no-results-{job_id}.zip")

    @patch("baclab.views._handle_job_failure")
    @patch("subprocess.run")
    def test_run_job_cblaster_value_error_populates_error_log(self, mock_subproc, mock_handle_failure):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")
        errors = sys.modules["baclab_tool_cblaster"]
        job_id = "cblaster-err-02"
        jr = JobRecord.objects.create(job_id=job_id, job_type="cblaster", status="queued")

        job_dict = self._create_mock_job_dict(job_id, command="cblaster search")
        with patch.object(toolkit_registry.get("cblaster"), "post_process", side_effect=errors.CBlasterValueError("Invalid matrix option")):
            run_job.apply(args=[job_dict])

        jr.refresh_from_db()
        self.assertEqual(jr.status, "failed")
        err_log = jr.error_log
        self.assertEqual(err_log["tool_name"], "cblaster")
        self.assertEqual(err_log["error_type"], "CBlasterValueError")
        self.assertEqual(err_log["error_message"], "Invalid matrix option")
        self.assertEqual(mock_handle_failure.call_args[0][3], f"value-error-{job_id}.zip")

    @patch("baclab.views._handle_job_failure")
    @patch("subprocess.run")
    def test_run_job_generic_value_error_invalid_fasta(self, mock_subprocess, mock_handle_failure):
        mock_subprocess.side_effect = ValueError("FASTA file header corrupted")
        job_id = "blast-err-02"
        jr = JobRecord.objects.create(job_id=job_id, job_type="blast", status="queued")

        job_dict = self._create_mock_job_dict(job_id, command="blastn -query corrupted.fasta")
        run_job.apply(args=[job_dict])

        jr.refresh_from_db()
        self.assertEqual(jr.status, "failed")
        self.assertIsNotNone(jr.error_log)

        err_log = jr.error_log
        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "blast")
        self.assertEqual(err_log["step"], "job_execution")
        self.assertEqual(err_log["error_type"], "ValueError")
        self.assertEqual(err_log["error_message"], "FASTA file header corrupted")

    @patch("os.makedirs")
    @patch("shutil.copy2")
    @patch("baclab.tools.prokka.ProkkaTool.run_single_genome")
    def test_process_inhouse_strain_failure_populates_error_log(self, mock_prokka_run, mock_copy2, mock_makedirs):
        cpe = subprocess.CalledProcessError(
            returncode=1,
            cmd=["prokka"],
            output=b"prokka output",
            stderr=b"prokka syntax error in sequence"
        )
        mock_prokka_run.side_effect = cpe

        fasta_file = SimpleUploadedFile("invalid_strain.fasta", b"invalid header\nATCG\n")
        strain = InhouseStrain.objects.create(
            strain_id="strain-err-101",
            genome_fasta=fasta_file,
            run_prokka=True,
            run_antismash=False,
            run_gtdbtk=False,
            status="pending"
        )

        with tempfile.TemporaryDirectory() as strains_db:
            with override_settings(INHOUSE_STRAINS_LIST=os.path.join(strains_db, "Inhouse_strains.tsv")):
                process_inhouse_strain.apply(args=["strain-err-101"])

        strain.refresh_from_db()
        self.assertEqual(strain.status, "failed")
        self.assertIsNotNone(strain.error_log)
        self.assertIsInstance(strain.error_log, dict)

        err_log = strain.error_log
        self.assertIn("timestamp", err_log)
        self.assertEqual(err_log["tool_name"], "prokka")
        self.assertEqual(err_log["step"], "prokka_processing")
        self.assertEqual(err_log["error_type"], "CalledProcessError")
        self.assertEqual(err_log["returncode"], 1)
        self.assertEqual(err_log["stdout"], "prokka output")
        self.assertEqual(err_log["stderr"], "prokka syntax error in sequence")
