import json
import os
import re
import shutil

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import path, reverse

from baclab.accounts import job_access_denied
from baclab.toolkit import Tool, cores
from baclab.toolkit.errors import JobError, contact_message
from baclab.toolkit.forms import UploadFileForm
from django import forms


class NoResults(JobError):
    """cblaster found nothing: the input did not hit the selected database."""
    archive_prefix = 'no-results'
    job_message = ("No results found for the cblaster search. This likely means that your input sequence did not yield any hits in the selected database. "
                   "Please try again with a different sequence or database.")
    results_message = staticmethod(lambda job_id: f"No results found in selected database. If you have further questions, please email us with your job id: {settings.ADMIN_EMAIL}")

    def __init__(self, folder_name=""):
        self.folder_name = folder_name
        super().__init__(f"No results found for {folder_name}")


class CBlasterValueError(JobError):
    """cblaster stopped with a ValueError (bad input or database)."""
    archive_prefix = 'value-error'
    job_message = ("cblaster encountered a ValueError during execution. This could be due to an issue with the input data or the selected database. "
                   "Please review your input and try again.")
    results_message = staticmethod(lambda job_id: f"Your job encountered a value error. Please fix your input. {contact_message()}")

    def __init__(self, msg="ValueError encountered in cblaster search"):
        super().__init__(msg)


class InsufficientResults(Exception):
    """cblaster produced fewer output files than a finished search does."""

    def __init__(self, folder_name="", count=0):
        self.folder_name, self.count = folder_name, count
        super().__init__(f"Insufficient results ({count}) in {folder_name}")


NUMERIC_FIELDS = ['decimals_st', 'decimals_bt', 'maximum_hits', 'maximum_intergenicgap', 'minimum_uniquequeryhits', 'minimum_hitsinclusters', 'percentage',
                  'maximum_evalue', 'minimum_identitiy', 'minimum_query_coverage', 'maximum_distance', 'maximum_clusters']


def database_options():
    """The databases offered on the page: database_options.json in the CblasterDB folder (custom databases of the admin add to it)."""
    try:
        with open(os.path.join(settings.CBLASTER_DATABASE_PATH, 'database_options.json')) as handle:
            options = json.load(handle).get('database_options', [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        print(f"Error loading cblaster database options: {error}")
        return []
    validated = []
    for option in options:
        if not isinstance(option, dict) or not all(key in option for key in ('value', 'label', 'mode')):
            print(f"Warning: Skipping cblaster option with missing required fields: {option}")
            continue
        mode = option['mode'].lower()
        if mode not in ('remote', 'local'):
            print(f"Warning: Skipping cblaster option with invalid mode '{mode}': {option}")
            continue
        validated.append({'value': option['value'], 'label': option['label'], 'mode': mode, 'show_warning': option.get('show_warning', False)})
    return validated


class SearchForm(UploadFileForm):
    """The upload form, plus the checks of cblaster's own settings (they end up on a command line)."""

    def clean(self):
        cleaned = super().clean()
        sanitization = settings.CBLASTER_SPECIFIC_SANITIZATION
        sensitivity = self.data.get('dmnd_sensitivity')
        if sensitivity is not None and sensitivity not in sanitization['allowed_dmnd_sensitivity']:
            raise forms.ValidationError(f"Invalid dmnd_sensitivity: {sensitivity}")
        for field in NUMERIC_FIELDS:
            if field in self.data and not re.fullmatch(sanitization['input_value_pattern'], str(self.data[field])):
                raise forms.ValidationError(f"Invalid value for {field}: {self.data[field]}")
        return cleaned


def fix_fasta_headers(request, input_dir):
    """A sequence pasted without its header line gets one."""
    if not os.path.exists(input_dir):
        return
    for file in os.listdir(input_dir):
        if file.endswith((".fasta", ".fa", ".faa", ".fna")):
            file_path = os.path.join(input_dir, file)
            with open(file_path, "r") as f:
                content = f.read()
            if not content.startswith(">"):
                with open(file_path, "w") as f:
                    f.write(">Sequence1\n" + content)


def arguments(request):
    options = request.POST
    mode = options.get("mode", "remote")
    database = options.get("database", "comman_myxo_BGCs_cblaster")
    if mode == "local" and not database.startswith("/"):
        if not database.endswith(".dmnd"):
            database = f"{database}.dmnd"
        database = f"/databases/CblasterDB/{database}"
    defaults = [('decimals_st', '4'), ('decimals_bt', '4')]
    return ([mode, database, str(options.get("find_intermediate_genes", "false")).lower()]
            + [str(options.get(key, default)) for key, default in defaults]
            + [options.get("key_function", "len")]
            + [str(options.get(key, default)) for key, default in [
                ('maximum_hits', '100'), ('maximum_intergenicgap', '20000'), ('minimum_uniquequeryhits', '3'), ('minimum_hitsinclusters', '3'),
                ('percentage', '50'), ('maximum_evalue', '0.01'), ('minimum_identitiy', '30'), ('minimum_query_coverage', '50'),
                ('maximum_distance', '20000'), ('maximum_clusters', '100')]]
            + [options.get("dmnd_sensitivity", "fast"), cores()])


def post_process(ctx):
    """Keep each query's results/ folder; a search without hits or with a ValueError fails with its own message."""
    output_dir, downloads_dir = ctx['output_dir'], ctx['downloads_dir']
    if not os.path.exists(output_dir):
        return
    for folder_name in os.listdir(output_dir):
        folder_path = os.path.join(output_dir, folder_name)
        if not os.path.isdir(folder_path) or folder_name == "input":
            continue
        results_path = os.path.join(folder_path, "results")

        log_path = os.path.join(folder_path, "logs", "cblaster-search.1.log")
        if os.path.exists(log_path):
            with open(log_path, "r") as log_file:
                lines = log_file.readlines()
                if lines and lines[-1].startswith("No results found"):
                    raise NoResults(folder_name)
                elif lines and lines[-1].startswith("ValueError"):
                    raise CBlasterValueError()

        if os.path.exists(results_path):
            result_count = len(os.listdir(results_path))
            if result_count < 5:
                raise InsufficientResults(folder_name, result_count)
            os.makedirs(downloads_dir, exist_ok=True)
            for root, _, files in os.walk(results_path):
                rel = os.path.relpath(root, results_path)
                target_root = downloads_dir if rel == '.' else os.path.join(downloads_dir, rel)
                os.makedirs(target_root, exist_ok=True)
                for f in files:
                    shutil.copy2(os.path.join(root, f), os.path.join(target_root, f))


def cblaster_results(request, job_id, download_dir):
    html_files = []

    for f in os.listdir(download_dir):
        if f.lower().endswith(".html"):
            html_files.append(f)

    if not html_files:
        return None
    
    html_files.sort()
    first_base = html_files[0].rsplit(".html", 1)[0]
    cblaster_url = reverse('baclab:cblaster_results_view')
    return redirect(f'{cblaster_url}?path_info={job_id}/{first_base}')


def cblaster_results_view(request):
    context = {}
    if 'path_info' not in request.GET or \
       any(x in request.GET['path_info'] for x in ['..', '"', '\'', '//']):
        return HttpResponseBadRequest("Invalid sample ID")
    splitted_path = request.GET['path_info'].split("---")

    base = splitted_path[0]                  # e.g. cblaster-UUID/cluster_summary
    parts = base.split("/", 1)
    job_id = parts[0]
    file_base = parts[1] if len(parts) > 1 else ""

    downloads_path = os.path.join(settings.DOWNLOAD_DIR, job_id)
    html_files = []
    if os.path.isdir(downloads_path):
        for f in os.listdir(downloads_path):
            if f.lower().endswith(".html"):
                html_files.append(f)
    html_files.sort()
    current_file = (file_base + ".html") if file_base else (html_files[0] if html_files else "")
    context["job_id"] = job_id
    context["cblaster_html_files"] = html_files
    context["current_cblaster_file"] = current_file
    context["sample_url"] = reverse('baclab:cblaster_file', args=[job_id, current_file]) if current_file else ""
    context["sample_anchor"] = ""
    return render(request, 'cblaster_results_view.html', context)


def serve_cblaster_file(request, job_id, filename):
    # basic sanitization
    if any(x in filename for x in ['..', '/', '\\']) or any(x in job_id for x in ['..','/','\\']):
        return HttpResponseBadRequest("Invalid path")
    denied = job_access_denied(request, job_id)
    if denied:
        return HttpResponse(denied[1], status=denied[0])
    downloads_path = os.path.join(settings.DOWNLOAD_DIR, job_id)
    abs_path = os.path.join(downloads_path, filename)
    if not abs_path.endswith(".html"):
        return HttpResponseBadRequest("Only HTML files allowed")
    if not abs_path.startswith(os.path.abspath(downloads_path)):
        return HttpResponseBadRequest("Out of scope")
    if not os.path.exists(abs_path):
        raise Http404("File not found")
    resp = FileResponse(open(abs_path, "rb"))
    resp["X-Frame-Options"] = "SAMEORIGIN"
    return resp



def build_custom_database(tmpdirname, db_name):
    """Make a local cblaster (DIAMOND) database from the GenBank files an administrator uploaded."""
    import subprocess
    db_dir = "/databases/CblasterDB"
    os.makedirs(db_dir, exist_ok=True)

    file_list_path = os.path.join(tmpdirname, "file_list.txt")
    with open(file_list_path, "w") as fl:
        for root, _, files in os.walk(tmpdirname):
            for f in files:
                if f != "file_list.txt":
                    fl.write(os.path.join(root, f) + "\n")

    cmd = (f"source /opt/conda/etc/profile.d/conda.sh && conda activate server_cblaster && cd {db_dir} && "
           f"cblaster config --email admin@example.com && cblaster makedb '{file_list_path}' -n '{db_name}' -f")
    subprocess.run(cmd, shell=True, executable="/bin/bash", check=True)

    json_path = os.path.join(db_dir, "database_options.json")
    options = {"database_options": []}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as jf:
                options = json.load(jf)
        except Exception:
            pass

    for opt in options.get("database_options", []):
        if opt.get("value") == db_name:
            opt["label"] = f"{db_name} (Custom)"
            opt["mode"] = "local"
            break
    else:
        options.setdefault("database_options", []).append({"value": db_name, "label": f"{db_name} (Custom)", "mode": "local", "show_warning": False})
    with open(json_path, "w") as jf:
        json.dump(options, jf, indent=4)


tool = Tool(
    name='cblaster',
    title='cblaster',
    category='search',
    file_only=True,
    requires_databases=False,   # remote searches need no local database
    form=SearchForm,
    prepare_inputs=fix_fasta_headers,
    args=arguments,
    exclude=['*/logs'],   # Snakemake's per-run logs
    post_process=post_process,
    results=cblaster_results,
    page_context=lambda: {'database_options': database_options()},
    custom_database=build_custom_database,
    urls=[path('cblaster/results', cblaster_results_view, name='cblaster_results_view'),
          path('cblaster/file/<str:job_id>/<str:filename>', serve_cblaster_file, name='cblaster_file')],
    citation=[
        {
            'text': 'Gilchrist CLM, Booth TJ, van Wersch B, van Grieken L, Medema MH, Chooi YH. 2021. cblaster: a remote search tool for rapid identification and visualization of homologous gene clusters. Bioinformatics Advances 1(1).',
            'url': 'https://github.com/gamcil/cblaster',
        },
    ],
    example=[('cblaster_example.fasta', 'cblaster_example.fasta')],
    example_post={'mode': 'local', 'database': 'mibig_4.0'},   # the local MIBiG database that ./baclab db install cblaster provides

)
