import os
import re
import shutil
import subprocess
import time
import uuid
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand

from baclab import db_status, tool_catalog
from baclab.toolkit import registry
from baclab.toolkit.files import copy_input_to_downloads


def conda_environments():
    """Names of the conda environments that exist in this container (including those of tools added in the admin)."""
    try:
        out = subprocess.run(['conda', 'env', 'list'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return {os.path.basename(line.split()[-1]) for line in out.splitlines() if line.strip() and not line.startswith('#')}


def required_environments():
    """{environment: [tools/<folder> that mention it]}, found in the tool scripts."""
    found = {}
    for root, _, files in os.walk(settings.TOOLS_DIR):
        for name in files:
            if name.endswith('.sh') and not name.startswith('download_'):
                with open(os.path.join(root, name), errors='ignore') as handle:
                    for env in set(re.findall(r'conda activate (?:--no-stack )?(server_[a-z0-9_]+)', handle.read())):
                        found.setdefault(env, set()).add(os.path.relpath(root, settings.TOOLS_DIR).split(os.sep)[0])
    return found


class Command(BaseCommand):
    help = ("Checks the installation from inside the containers: conda environments, databases and - with --run - runs the "
            "tools that have example data on that data, exactly as a job would.")

    def add_arguments(self, parser):
        parser.add_argument('--run', action='store_true', help='also run the example job of every tool that describes itself with a toolkit Tool')
        parser.add_argument('--tool', action='append', default=[], help='only this tool (repeatable); implies --run for it')

    def ok(self, text):
        self.stdout.write(self.style.SUCCESS('PASS  ') + text)

    def bad(self, text):
        self.failures += 1
        self.stdout.write(self.style.ERROR('FAIL  ') + text)

    def skip(self, text):
        self.stdout.write(self.style.WARNING('SKIP  ') + text)

    def handle(self, *args, **options):
        self.failures = 0
        wanted = set(options['tool'])
        enabled = tool_catalog.enabled_map()

        self.stdout.write(self.style.MIGRATE_HEADING('Conda environments'))
        existing = conda_environments()
        if existing is None:
            self.skip('conda is not available here')
        else:
            for env, folders in sorted(required_environments().items()):
                if wanted and not wanted & (folders | {env[len('server_'):]}):
                    continue
                (self.ok if env in existing else self.bad)(f"{env}  ({', '.join(sorted(folders))})")

        self.stdout.write(self.style.MIGRATE_HEADING('Databases'))
        for row in db_status.overview():
            entry = row['entry']
            if wanted and not wanted & set(entry['tools']):
                continue
            needed = any(tool_catalog.is_enabled(name, enabled) for name in entry['tools'])
            if row['installed']:
                self.ok(entry['title'])
            elif needed and not entry.get('optional'):
                self.bad(f"{entry['title']} is missing  ->  ./baclab db install {entry['key']}")
            else:
                self.skip(f"{entry['title']} is not installed (not needed by an enabled tool)")

        if options['run'] or wanted:
            self.stdout.write(self.style.MIGRATE_HEADING('Example jobs'))
            for tool in registry.builtin_tools():
                if wanted and tool.name not in wanted:
                    continue
                self.run_example(tool, enabled)

        if self.failures:
            self.stdout.write(self.style.ERROR(f'\n{self.failures} check(s) failed.'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('\nEverything checked is fine.'))

    def run_example(self, tool, enabled):
        if not tool.example:
            return self.skip(f'{tool.name}: no example data')
        if not tool_catalog.is_enabled(tool.name, enabled):
            return self.skip(f'{tool.name}: switched off')
        missing = db_status.missing_for_tool(tool)
        if missing:
            return self.skip(f"{tool.name}: database missing ({'; '.join(missing)})")
        job_id = f'{tool.name}-selftest{uuid.uuid4().hex[:8]}'
        job_dir = os.path.join(settings.UPLOAD_DIR, job_id)
        downloads = os.path.join(settings.DOWNLOAD_DIR, job_id)
        started = time.time()
        try:
            input_dir, output_dir = os.path.join(job_dir, 'input'), os.path.join(job_dir, 'output')
            os.makedirs(input_dir)
            os.makedirs(output_dir)
            for source, name in tool.example_files():
                shutil.copyfile(source, os.path.join(input_dir, name))
            shutil.copytree(input_dir, os.path.join(output_dir, 'input'))
            job = tool.build_job(SimpleNamespace(FILES={}, POST=dict(tool.example_post), saved_files={}), job_id)
            ctx = {'job_id': job_id, 'output_dir': job['outputDir'], 'downloads_dir': job['resultsDir'], 'job_options': job.get('options', {}), 'command': job['command']}
            tool.run(ctx)
            tool.post_process(ctx)
            copy_input_to_downloads(ctx['output_dir'], ctx['downloads_dir'])
            produced = [f for _, _, files in os.walk(downloads) for f in files]
            if len([f for f in produced]) <= len(tool.example_files()):
                self.bad(f'{tool.name}: ran, but produced no result files')
            else:
                self.ok(f'{tool.name}: {len(produced)} files in {time.time() - started:.0f} s')
        except Exception as error:   # report and go on with the next tool
            self.bad(f'{tool.name}: {str(error).strip().splitlines()[-1] if str(error).strip() else type(error).__name__}')
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)
            shutil.rmtree(downloads, ignore_errors=True)
