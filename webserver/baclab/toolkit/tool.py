"""What the portal needs to know about a tool.

Every tools/<name>/tool.py defines one `tool = Tool(...)`; the rest of the portal (pages, job runner,
results, menus, URLs) is driven by it. Only `name`, `title` and `category` are required - everything
else has a default that fits a simple "run a script, show a table" tool.

Tools added in the admin (models.CustomTool) are turned into the same `Tool` objects by toolkit.custom,
so the portal treats both kinds alike.
"""
import os

from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import reverse

from .files import copy_output_to_downloads, copy_outputs, prune_paths, run_command
from .forms import UploadFileForm


class Tool:
    def __init__(self, name, title, category, *, form=UploadFileForm, form_kwargs=None, script=None, args=(), build_job=None,
                 run=None, outputs=None, post_process=None, results=None, citation=(), example=(), page_context=None,
                 urls=(), zip_exclude=(), failure_files=None, faq=(), faq_title=None, prepare_inputs=None,
                 description='', databases=(), template=None, source='builtin', file_only=False, requires_databases=True,
                 settings_key=None, custom_database=None, exclude=(), example_post=None, example_check=None):
        """
        name         the job type: URL (/<name>/), template <name>.html, job ids "<name>-<uuid>"
        title        shown in the menus
        category     key of a category in toolkit/categories.py
        form         Django form validating the upload (default: one file or pasted FASTA)
        script       the script to run (default <name>_script.sh in the tool's directory)
        args         the script is called as <script> <input dir> <output dir> *args; args is a list, or a
                     function of the request returning one
        build_job    full control: function (request, job_id) -> job dict; replaces script/args
        prepare_inputs function (request, input_dir) run on the uploaded files before the job is built
                     (e.g. renaming them to fixed names the script looks for)
        run          function (ctx) replacing "run the command" (ctx has job_id, command, output_dir, ...)
        outputs      what to keep from the output directory: names, sub-folders or glob patterns
                     (default: everything). post_process(ctx) replaces this entirely
        results      function (request, job_id, download_dir) -> response, or None if nothing to show
        citation     list of {'text': ..., 'url': ...}
        example      example files: names, or (source, name used in the job) pairs, or a folder (all its files);
                     looked up in the tool's example_data/ folder and then in the shared one
        page_context function () -> dict of extra variables for the submission page
        urls         extra django url patterns for this tool
        zip_exclude  file extensions left out of the results zip
        failure_files function (relative path) -> bool: which files go into the failed-job archive
        faq          the "How to use" steps (list of sentences); or provide <name>_faq.html for custom HTML
        description  one sentence under the page title
        databases    folders under databases/ the tool needs; the database status page and `check_databases`
                     report on them (see baclab/db_catalog.py for how to describe how they are installed)
        template     the submission page (default <name>.html in the tool's folder)
        source       'builtin' (a tools/<name>/ folder) or 'custom' (added in the admin)
        file_only    the input is too large to paste: refuse a pasted sequence (type=fasta) and accept uploaded files only
        requires_databases  False for tools that have modes without a database (the page and job do not insist on the catalog databases)
        settings_key the key under which the tool is switched on/off (enabled_tools.csv, admin tool switches) when it is not the name
        exclude      names, sub-folders or glob patterns (relative to the output folder) that are internal working data and are left out of the results
        example_post settings the example run ("View Example Results", `baclab selftest`) is given, as the form would post them
        example_check function () -> None, or a message saying what has to be prepared before the example can run (e.g. a database to build)
        custom_database function (tmpdir, db_name) that builds a database an administrator uploads for this tool (admin -> Custom databases)
        """
        self.name, self.title, self.category = name, title, category
        self.description, self.databases = description, list(databases)
        self.template, self.source = template or f'{name}.html', source
        self.file_only, self.requires_databases = file_only, requires_databases
        self.exclude = list(exclude)
        self._example_post = example_post or {}
        self.example_check = example_check
        self.settings_key = settings_key or name
        if custom_database:
            self.build_custom_database = custom_database
        self.form, self.form_kwargs = form, form_kwargs or {}
        self.script = script or f'{name}_script.sh'
        self.args = args if callable(args) else (lambda request, args=args: list(args))
        self.outputs = outputs
        self.results = results
        self.citation = list(citation)
        self.example = [(item, item) if isinstance(item, str) else tuple(item) for item in example]
        self.page_context = page_context or (lambda: {})
        self.urls = list(urls)
        self.zip_exclude = list(zip_exclude)
        self.failure_files = failure_files
        self.faq, self.faq_title = list(faq), faq_title
        self.prepare_inputs = prepare_inputs
        self.directory = None          # set by the registry
        # Replaceable steps: a function given to the constructor shadows the default method.
        if build_job:
            self.build_job = build_job
        if run:
            self.run = run
        if post_process:
            self.post_process = post_process

    @property
    def url(self):
        """Where the tool's submission page lives."""
        if self.source == 'custom':
            return reverse('baclab:custom_tool', args=[self.name])
        return reverse(f'baclab:{self.name}')

    @property
    def faq_template(self):
        """<name>_faq.html if the tool has its own FAQ entry, else the standard one built from `faq`."""
        try:
            get_template(f'{self.name}_faq.html')
            return f'{self.name}_faq.html'
        except TemplateDoesNotExist:
            return 'tool_faq.html'

    # ---- defaults for the steps of a job ----
    @property
    def script_path(self):
        return os.path.join(self.directory, self.script)

    def build_job(self, request, job_id):
        """The job description handed to the job runner."""
        job_path = os.path.join(settings.UPLOAD_DIR, job_id)
        if self.prepare_inputs:
            self.prepare_inputs(request, os.path.join(job_path, 'input'))
        command = [self.script_path, os.path.join(job_path, 'input'), os.path.join(job_path, 'output')]
        return {
            'jobId': job_id,
            'command': command + [str(arg) for arg in self.args(request)],
            'uploadDir': os.path.join(job_path, 'input'),
            'outputDir': os.path.join(job_path, 'output'),
            'resultsDir': os.path.join(settings.DOWNLOAD_DIR, job_id),
        }

    @property
    def example_post(self):
        """The settings the example run is given: a dict, or a function (called each time) for settings that depend on the installation."""
        extra = self._example_post() if callable(self._example_post) else self._example_post
        return {'organism': 'none', **extra}

    def example_files(self):
        """(path, name used in the job) of the example files that exist."""
        folders = [os.path.join(self.directory, 'example_data')] if self.directory else []
        found = []
        for source, name in self.example:
            for folder in folders + [settings.EXAMPLE_DATA_DIR]:
                path = os.path.join(folder, source)
                if os.path.isdir(path):
                    found += [(os.path.join(path, file), file) for file in sorted(os.listdir(path))]
                    break
                if os.path.exists(path):
                    found.append((path, name))
                    break
        return found

    def run(self, ctx):
        run_command(ctx['command'], ctx['output_dir'])

    def post_process(self, ctx):
        """Fill the downloads folder (what is zipped and shown) from the raw output folder."""
        if self.outputs is None:
            copy_output_to_downloads(ctx['output_dir'], ctx['downloads_dir'])
        else:
            copy_outputs(ctx['output_dir'], ctx['downloads_dir'], self.outputs)
        prune_paths(ctx['downloads_dir'], self.exclude)
