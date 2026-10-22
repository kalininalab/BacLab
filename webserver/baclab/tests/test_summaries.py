import os
import tempfile

from django.test import SimpleTestCase, TestCase, override_settings

from baclab import summaries
from baclab.models import JobRecord


def write(folder, name, text):
    with open(os.path.join(folder, name), 'w') as handle:
        handle.write(text)


class SummarizerTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_checkm2_good_and_bad(self):
        write(self.dir, 'checkm2_results.tsv', 'Name\tCompleteness\tContamination\ng1\t99.1\t0.4\n')
        result = summaries.summarize('checkm2', self.dir)
        self.assertEqual(result['status'], 'good')
        self.assertIn('99.1', result['headline'])
        write(self.dir, 'checkm2_results.tsv', 'Name\tCompleteness\tContamination\ng1\t70\t9\n')
        self.assertEqual(summaries.summarize('checkm2', self.dir)['status'], 'warn')

    def test_padloc_counts_systems(self):
        write(self.dir, 'padloc_results.csv', 'genome,system.number,system,seqid\ng1,1,CBASS_I,c1\ng1,1,CBASS_I,c1\ng1,2,RM_type_I,c2\n')
        result = summaries.summarize('padloc', self.dir)
        self.assertIn('2 defence systems', result['headline'])

    def test_mlst_and_kraken2_and_ani(self):
        write(self.dir, 'mlst_results.tsv', 'g.fasta\tecoli\t10\tadk(10)\n')
        self.assertEqual(summaries.summarize('mlst', self.dir)['headline'], 'ecoli ST10')
        write(self.dir, 'kraken2_results.tsv', '95.0\t100\t90\tS\t562\t  Escherichia coli\n5.0\t10\t10\tS\t1\tOther\n')
        self.assertIn('Escherichia coli', summaries.summarize('kraken2', self.dir)['headline'])
        write(self.dir, 'ani_results.tsv', 'Query\tReference\tANI\ta.fa\ta.fa\t100\na.fa\tb.fa\t97.2\n'.replace('Query\tReference\tANI\ta.fa\ta.fa\t100\n', 'Query\tReference\tANI\n'))
        self.assertIn('97.2', summaries.summarize('ani', self.dir)['headline'])

    def test_fallback_counts_files_and_broken_input_does_not_raise(self):
        write(self.dir, 'something.txt', 'x')
        self.assertIn('1 result file', summaries.summarize('unknowntool', self.dir)['headline'])
        write(self.dir, 'amrfinderplus_results.tsv', '\x00\x01 not a table')
        self.assertTrue(summaries.summarize('amrfinderplus', self.dir)['headline'])
        self.assertEqual(summaries.summarize('mlst', os.path.join(self.dir, 'missing')), {})


class EnsureSummaryTest(TestCase):
    def test_summary_is_computed_once_for_finished_jobs_only(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'mlst-1'))
            write(os.path.join(root, 'mlst-1'), 'mlst_results.tsv', 'g.fasta\tecoli\t131\n')
            with override_settings(DOWNLOAD_DIR=root):
                running = JobRecord.objects.create(job_id='mlst-0', job_type='mlst', status='running')
                done = JobRecord.objects.create(job_id='mlst-1', job_type='mlst', status='finished')
                self.assertIsNone(summaries.ensure_summary(running))
                self.assertEqual(summaries.ensure_summary(done)['headline'], 'ecoli ST131')
                done.refresh_from_db()
                self.assertEqual(done.summary['headline'], 'ecoli ST131')


class VersionsAndMethodsTest(TestCase):
    def test_versions_are_read_from_conda_meta_and_dist_info(self):
        from baclab import tool_versions
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'server_padloc', 'conda-meta'))
            write(os.path.join(root, 'server_padloc', 'conda-meta'), 'padloc-2.0.0-hdfd78af_0.json', '{}')
            site = os.path.join(root, 'server_genovi', 'lib', 'python3.7', 'site-packages', 'GenoVi-0.2.16.dist-info')
            os.makedirs(site)
            tool_versions.version_of.cache_clear()
            self.assertEqual(tool_versions.version_of('padloc', root), '2.0.0')
            self.assertEqual(tool_versions.version_of('genovi', root), '0.2.16')
            self.assertEqual(tool_versions.version_of('unknown', root), '')
        tool_versions.version_of.cache_clear()

    def test_methods_text_mentions_tool_settings_and_citation(self):
        from baclab import methods
        job = JobRecord.objects.create(job_id='padloc-m', job_type='padloc', status='finished',
                                       parameters={'inputs': ['a.fasta', 'b.fasta'], 'settings': {'mode': 'fast'}})
        text = methods.methods_text(job)
        self.assertIn('PADLOC', text)
        self.assertIn('2 input files', text)
        self.assertIn('mode = fast', text)
        self.assertIn('Please cite', text)
