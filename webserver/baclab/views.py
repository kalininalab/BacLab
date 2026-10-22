from django.shortcuts import render
from django.shortcuts import get_object_or_404
import os
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_http_methods
import shutil
from .file_manager import FileManager
from .tasks import write_citation_file
import zipfile
from django.core.mail import EmailMultiAlternatives

from .taskapp.celery import app
from .models import JobRecord
from .error_utils import format_error_log
from . import email_templates, ncbi
from .accounts import job_access_denied
from .toolkit import registry as toolkit_registry
from .toolkit.errors import JobError
from .toolkit.files import copy_input_to_downloads, zip_folder
from baclab.tools.antismash import AntismashError
from urllib.parse import urlparse
from celery.result import AsyncResult
import pandas as pd
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone
from django.db.models import Count, Prefetch
from datetime import timedelta
import glob

log_file_path = os.path.join(os.path.dirname(__file__), 'log_file')
delete_log_file_path = os.path.join(os.path.dirname(__file__), 'delete_log_file')

website_link = settings.WEBSITE_LINK
if isinstance(website_link, urlparse('').__class__):
    website_link = website_link.geturl()

antismash_data_path = settings.ANTISMASH_DATA_PATH
antismash_strains_name_mapping = {}
try:
    antismash_strains_list = os.listdir(antismash_data_path)
    for strain in antismash_strains_list:
        antismash_strains_name_mapping[strain.lower()] = strain
except (FileNotFoundError, OSError):
    pass

annotation_db_path = settings.ANNOTATION_DB_PATH
annotation_strains_name_mapping = {}
AnnotationDB_list = []
try:
    AnnotationDB_list = os.listdir(annotation_db_path)
    with open(settings.INHOUSE_STRAINS_LIST) as strains_file:
        lines = strains_file.readlines()
        for line in lines[1:]:
            splitted = line.split('\t')
            if len(splitted) >= 2:
                annotation_strains_name_mapping[splitted[0].strip()] = splitted[1].strip()
except (FileNotFoundError, OSError):
    pass

# Load phylogeny strain options
# Load cblaster database options
def get_tool_name_from_job_id(job_id: str) -> str:
    """The tool a job id belongs to (job ids are "<job type>-<uuid>"); used to label error logs."""
    job_type = job_id.split('-')[0]
    return job_type or 'generic_tool'


def run_toolkit_job(tool, job_id, command, output_dir, downloads_dir, job_options):
    """Run a job of a tool that describes itself with a toolkit Tool (tools/<name>/tool.py or added in the admin)."""
    ctx = {
        'job_id': job_id,
        'output_dir': output_dir,
        'downloads_dir': downloads_dir,
        'job_options': job_options,
        'command': command,
    }
    tool.run(ctx)
    tool.post_process(ctx)
    # Every job's results include what the user actually submitted, however much post-processing trimmed
    copy_input_to_downloads(output_dir, downloads_dir)
    write_citation_file(downloads_dir, job_type=job_id.split('-')[0])


@app.task(bind=True)
def run_job(self, job):
    job_id = job['jobId']
    command = job['command']
    input_dir = job['uploadDir']
    output_dir = job['outputDir']
    downloads_dir = job['resultsDir']
    job_options = job.get('options', {})
    archive_name = f"{job_id}.zip"
    command_error = None
    notify_email = job.get('email')
    results_url = job.get('results_url')

    # Estimate time based on input file sizes
    size_mb = FileManager.get_dir_size_mb(input_dir)
    job_type = job_id.split('-')[0]
    toolkit_tool = toolkit_registry.get(job_type)
    mins = int(size_mb * (6 if job_type in ('annotationPipeline', 'genomemining') else 2)) + 1
    label = f"Running {toolkit_tool.title}" if toolkit_tool is not None else "Processing data"
    msg = f"{label} (Est. {mins} mins for {size_mb:.1f} MB)"

    self.update_state(state='PROGRESS', meta={'progress': 50, 'message': msg})

    mark_job_status(job_id, "running")

    try:
        zip_path = os.path.join(settings.RESULTS_DIR, archive_name)
        if toolkit_tool is None:
            raise RuntimeError(f"No tool is registered for job type '{job_type}'")
        if job.get('accessions'):   # genomes the user named by NCBI accession are fetched now, on the worker
            fetched = ncbi.fetch_into(job['accessions'], input_dir, getattr(toolkit_tool.form, 'ALLOWED_EXTENSIONS', ()))
            for name in fetched:
                shutil.copy2(os.path.join(input_dir, name), os.path.join(output_dir, 'input', name))
        run_toolkit_job(toolkit_tool, job_id, command, output_dir, downloads_dir, job_options)
        if not os.path.exists(zip_path):
            # Zip the curated downloads folder, not the raw output folder with the tool's intermediate files
            zip_folder(downloads_dir, zip_path, exclude_extensions=toolkit_tool.zip_exclude)
            print(f"Created archive: {zip_path}")

        mark_job_status(job_id, "finished")
        send_job_notification_email(job_id, notify_email, results_url, success=True)

        if not settings.LOCAL_DEBUG_MODE:
            shutil.rmtree(os.path.join(settings.UPLOAD_DIR, job_id), ignore_errors=True)

    except AntismashError as err:
        print(f"Error running job {job_id}: {err}")
        err_log = format_error_log(err, step="antismash_execution", tool_name="antismash")
        error_message = "antiSMASH failed to produce expected output. This could be due to issues with the input sequence, such as it being too short or invalid, or due to an internal error in antiSMASH. Please review your input and try again."
        mark_job_status(job_id, "failed", error_message, error_log=err_log)
        send_job_notification_email(job_id, notify_email, results_url, success=False, error_msg=error_message)
        error_output_archive_name = f"antismash-error-{job_id}.zip"
        _handle_job_failure(job_id, command, str(err), error_output_archive_name, downloads_dir, send_admin_email=False)

    except JobError as err:
        print(f"Error running job {job_id}: {err}")
        err_log = format_error_log(err, step="job_execution", tool_name=get_tool_name_from_job_id(job_id))
        mark_job_status(job_id, "failed", err.job_message, error_log=err_log)
        send_job_notification_email(job_id, notify_email, results_url, success=False, error_msg=err.job_message)
        _handle_job_failure(job_id, command, str(err), f"{err.archive_prefix}-{job_id}.zip", downloads_dir,
                            send_admin_email=err.notify_admin, include=getattr(toolkit_tool, 'failure_files', None))

    except Exception as err:
        print(f"Error running job {job_id}: {err}")
        stdout = getattr(err, 'stdout', '') or getattr(err, 'output', '') or ''
        stderr = getattr(err, 'stderr', '') or ''
        returncode = getattr(err, 'returncode', None)
        tool_name = get_tool_name_from_job_id(job_id)
        err_log = format_error_log(err, step="job_execution", tool_name=tool_name, stdout=stdout, stderr=stderr, returncode=returncode)
        error_message = "An unexpected error occurred during job execution. The administrators have been notified."
        mark_job_status(job_id, "failed", error_message, error_log=err_log)
        send_job_notification_email(job_id, notify_email, results_url, success=False, error_msg=error_message)
        error_output_archive_name = f"failed-{job_id}.zip"
        _handle_job_failure(job_id, command, str(err), error_output_archive_name, downloads_dir, send_admin_email=True,
                            include=getattr(toolkit_tool, 'failure_files', None))

    print(f"Finished job: {job_id}")

def _handle_job_failure(job_id, command, error_msg, output_archive_name, downloads_dir, send_admin_email=True, include=None):
    """Helper to handle job failures and create error archives. include(relative path) -> bool, if given, picks
    which files of the job's output go into the archive."""
    output_error_zip_path = os.path.join(settings.RESULTS_DIR, output_archive_name)
    error_zip_paths = [output_error_zip_path]
    source_dir = os.path.join(settings.UPLOAD_DIR, job_id, "output")

    if job_id.startswith('taxonomyfinder-'):
        def include(rel_path):   # noqa: F811 - the taxonomy finder keeps only its logs and the input
            return rel_path.endswith('.log') or rel_path.startswith('input' + os.sep)

    if include:
        with zipfile.ZipFile(output_error_zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, source_dir)
                    if include(rel_path):
                        archive.write(file_path, rel_path)
    else:
        FileManager.zip_directory(source_dir, output_error_zip_path)

    if not settings.LOCAL_DEBUG_MODE:
        if send_admin_email:
            send_failure_email_admin(job_id, command, error_msg, error_zip_paths)
        shutil.rmtree(os.path.join(settings.UPLOAD_DIR, job_id), ignore_errors=True)
        shutil.rmtree(downloads_dir, ignore_errors=True)

def _render_site_page(request, page_key):
    from .models import SitePage, PageSection
    page = get_object_or_404(
        SitePage.objects.prefetch_related(
            Prefetch('sections', queryset=PageSection.objects.filter(is_published=True))
        ),
        page_key=page_key,
    )
    return render(request, 'site_page.html', {'page': page})

def guides(request):
    return render(request, 'guides.html', {})

def about(request):
    return _render_site_page(request, 'contact')


def index(request):
    """Main dashboard showing stats purely from Database."""
    def format_duration(td):
        if not td: return None
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

    context = {
        'total_jobs': JobRecord.objects.count(),
        'running_jobs': JobRecord.objects.filter(status='running').count(),
        'queued_jobs': JobRecord.objects.filter(status='queued').count(),
        'finished_jobs': JobRecord.objects.filter(status='finished').count(),
        'failed_jobs': JobRecord.objects.filter(status='failed').count(),
        'use_db_stats': True
    }

    # Job Type Breakdown
    job_types_stats = []
    type_summary = JobRecord.objects.values('job_type').annotate(total=Count('job_id')).order_by('-total')

    for item in type_summary:
        jt = item['job_type']
        finished_set = JobRecord.objects.filter(job_type=jt, status='finished', started_at__isnull=False, finished_at__isnull=False)

        total_duration = timedelta()
        for jr in finished_set:
            if jr.started_at and jr.finished_at:
                total_duration += (jr.finished_at - jr.started_at)

        avg_duration = total_duration / finished_set.count() if finished_set.exists() else None

        job_types_stats.append({
            'job_type': jt,
            'count': item['total'],
            'finished_count': finished_set.count(),
            'total_duration': format_duration(total_duration),
            'avg_duration': format_duration(avg_duration),
        })

    context['job_types_stats'] = job_types_stats
    return render(request, 'index.html', context)

def terms(request):
    return _render_site_page(request, 'terms')

def after_upload(request):
    return render(request, 'after_upload.html', {})

def qrcode(request):
    return render(request, 'qrcode.html', {})

def matching_file_in_dir(dir, *patterns):
    for pattern in patterns:
        hits = glob.glob(os.path.join(dir, pattern))
        if hits:
            return sorted(hits)[0]
    return None


def _task_job_id(task):
    """The job id a Celery task of run_job belongs to; None for other tasks (database builds, clean-up, ...), whose first argument is not a job."""
    args = task.get('args') or []
    first = args[0] if args else None
    return first.get('jobId') if isinstance(first, dict) else None


@require_http_methods(["GET"])
def results(request):
    if 'job_id' not in request.GET:
        return render(request, 'results.html', {})

    job_id = request.GET['job_id']
    job_type = job_id.split('-')[0]
    job_download_dir = os.path.join(settings.DOWNLOAD_DIR, job_id)
    job_results_archive = os.path.join(settings.RESULTS_DIR, f"{job_id}.zip")

    denied = job_access_denied(request, job_id)
    if denied:
        return render(request, 'results.html', {'error': denied[1], 'job_id': job_id}, status=denied[0])

    toolkit_tool = toolkit_registry.get(job_type)
    show_results = toolkit_tool.results if toolkit_tool is not None else None
    if '..' in job_id or '/' in job_id or show_results is None:
        return render(request, 'results.html', {'error': "Job ID does not match expected format.", 'job_id': job_id})

    if 'download' in request.GET:
        if not os.path.exists(job_results_archive):
            raise Http404("File does not exist")

        response = FileResponse(open(job_results_archive, 'rb'))
        response['Content-Disposition'] = f'attachment; filename="{job_id}.zip"'
        return response

    if not os.path.exists(job_results_archive):
        queue = app.control.inspect()
        active_tasks = queue.active()
        scheduled_tasks = queue.reserved()
        if active_tasks:
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    if _task_job_id(task) == job_id:
                        return render(request, 'results.html', {'processing': "Job is running, please check back later", 'job_id': job_id})

        if scheduled_tasks:
            for worker, tasks in scheduled_tasks.items():
                for index, task in enumerate(tasks):
                    if _task_job_id(task) == job_id:
                        queued_jobs = index + 1
                        return render(request, 'results.html', {
                            'processing': f"Job is queued, there are {queued_jobs} jobs in front of you.",
                            'job_id': job_id
                        })

        record = JobRecord.objects.filter(job_id=job_id).first()
        if record is not None and record.status in ('queued', 'running'):
            # The queue inspection above only sees jobs a worker has already reserved; the database knows every job
            waiting = "Job is running, please check back later" if record.status == 'running' else "Job is queued and waits for a free worker"
            return render(request, 'results.html', {'processing': waiting, 'job_id': job_id})

        if os.path.exists(os.path.join(settings.RESULTS_DIR, f"failed-{job_id}.zip")):
            return render(request, 'results.html', {'error': f"Your job did not produce any results. You can try different database configurations. If you have further questions, please email us with your job id: {settings.ADMIN_EMAIL}", 'job_id': job_id})

        for error in JobError.registry:   # failures a tool gave its own message (toolkit.errors.JobError)
            if os.path.exists(os.path.join(settings.RESULTS_DIR, f"{error.archive_prefix}-{job_id}.zip")):
                return render(request, 'results.html', {'error': error.results_page_message(job_id), 'job_id': job_id})

        if os.path.exists(os.path.join(settings.RESULTS_DIR, f"no-results-{job_id}.zip")):
            return render(request, 'results.html', {'error': f"No results found in selected database. If you have further questions, please email us with your job id: {settings.ADMIN_EMAIL}", 'job_id': job_id})

        if os.path.exists(os.path.join(settings.RESULTS_DIR, f"value-error-{job_id}.zip")):
            return render(request, 'results.html', {'error': f"Your job encountered a value error. Please fix your input. If you have further questions, please email us with your job id: {settings.ADMIN_EMAIL}", 'job_id': job_id})
        
        if os.path.exists(os.path.join(settings.RESULTS_DIR, f"antismash-error-{job_id}.zip")):
            job_status, job_error_message = get_job_status(job_id)

            return render(request, 'results.html', {'error': job_error_message + f"If you have further questions, please email us with your job id: {settings.ADMIN_EMAIL}", 'job_id': job_id})
        return render(request, 'results.html', {'error': "Job ID not found. If you run your job more than 30 days ago, please submit a new job.", 'job_id': job_id})

    if os.path.isdir(job_download_dir):
        result = show_results(request, job_id, job_download_dir)
        if result:
            return result

    return render(request, 'results.html', {'error': f"Your job did not produce any results. You can try different configurations. If you have further questions, please email us with your job id: {settings.ADMIN_EMAIL}", 'job_id': job_id})

def serve_antismash_dev(request, relpath):
    if not settings.LOCAL_MODE:
        return HttpResponseBadRequest("Not available in production")
    if ".." in relpath or relpath.startswith("/"):
        return HttpResponseBadRequest("Invalid path")
    abs_path = os.path.normpath(os.path.join(antismash_data_path, relpath))
    if not abs_path.startswith(os.path.abspath(antismash_data_path)):
        return HttpResponseBadRequest("Out of scope")
    if not os.path.exists(abs_path):
        raise Http404("File not found")
    if os.path.isdir(abs_path):
        idx = os.path.join(abs_path, "index.html")
        if os.path.exists(idx):
            abs_path = idx
        else:
            return HttpResponseBadRequest("Directory listing disabled")
    resp = FileResponse(open(abs_path, "rb"))
    # Allow iframe embedding from same origin
    resp["X-Frame-Options"] = "SAMEORIGIN"
    return resp

def sample(request):
    context = {}
    if 'path_info' not in request.GET or \
       any([x in request.GET['path_info'] for x in ['..', '"', '\'', '//']]):
        return HttpResponseBadRequest("Invalid sample ID")
    splitted_path = request.GET['path_info'].split("---")
    context["sample_url"] = f"{settings.ANTISMASH_DATA_PATH}/" + splitted_path[0] + "/index.html"
    context["sample_anchor"] = ""
    if len(splitted_path) > 1:
        context["sample_anchor"] = "#"+splitted_path[1]
    genome = splitted_path[0].split("/")[0]

    return render(request, 'sample.html', context=context)

def upload_file(request, tool):
    return render(request, 'upload_file.html', {'tool': tool})

def download_file(request, tool, file):
    return render(request, 'download_file.html', {'tool': tool, 'file': file})

def serve_cblaster_dev(request, relpath):
    if not settings.LOCAL_MODE:
        return HttpResponseBadRequest("Not available in production")
    if ".." in relpath or relpath.startswith("/"):
        return HttpResponseBadRequest("Invalid path")
    abs_path = os.path.normpath(os.path.join(settings.DOWNLOAD_DIR, relpath))
    if not abs_path.startswith(os.path.abspath(settings.DOWNLOAD_DIR)):
        return HttpResponseBadRequest("Out of scope")
    if not os.path.exists(abs_path):
        raise Http404("File not found")
    if os.path.isdir(abs_path):
        idx = os.path.join(abs_path, "index.html")
        if os.path.exists(idx):
            abs_path = idx
        else:
            return HttpResponseBadRequest("Directory listing disabled")
    resp = FileResponse(open(abs_path, "rb"))
    # Allow iframe embedding from same origin
    resp["X-Frame-Options"] = "SAMEORIGIN"
    return resp

# Modified version of django.core.mail.mail_admins()
@app.task
def send_failure_email_admin(job_id, command, command_error, error_archive_path):
    """Send a message to the admins, as defined by the ADMINS setting."""
    if not settings.ADMINS:
        return
    if not all(isinstance(a, (list, tuple)) and len(a) == 2 for a in settings.ADMINS):
        raise ValueError("The ADMINS setting must be a list of 2-tuples.")

    subject = f"Job {job_id} Failed"
    message = (
        f"Dear Admin,\n\n"
        f"The job with ID {job_id} on BacLab has failed.\n\n"
        f"Command: {' '.join(command)}\n"
        f"Error: {command_error}\n\n"
        f"Please check the error logs for more details.\n\n"
        f"Best regards,\n"
        f"BacLab Team"
    )

    mail = EmailMultiAlternatives(
        "%s%s" % (settings.EMAIL_SUBJECT_PREFIX, subject),
        message,
        settings.SERVER_EMAIL,
        [a[1] for a in settings.ADMINS],
    )
    for error_archive in error_archive_path:
        mail.attach_file(error_archive)
    mail.send(fail_silently=True)   # a missing or broken mail server must never break job handling

def send_job_notification_email(job_id, email, results_url, success, error_msg=None):
    """Notify the submitting user by email that their job finished or failed (the texts are edited in the admin: E-mail messages)."""
    if not email:
        return
    record = JobRecord.objects.filter(job_id=job_id).first()
    email_templates.send('finished' if success else 'failed', email, job_id=job_id, job_name=(record.label if record and record.label else job_id),
                         tool=(record.tool_label if record else job_id.split('-')[0]), results_url=results_url, error=error_msg or '')

def make_annotation_link_strains(sample_name, strain_og_name):
    """
    Expected sample_name pattern: StrainName_ProteinID
    Produces: /annotation/StrainName_ProteinID
    """
    return f'/faa_viewer/{sample_name}:{strain_og_name}'

def generate_protein_link(row):
    filename = f"{row['RandomName']}.faa"
    safe_strain = escape(str(row['STRAIN']))
    safe_random_name = escape(str(row['RandomName']))
    # Check if the specific file exists dynamically or in the cached list
    if filename in AnnotationDB_list or os.path.exists(os.path.join(settings.ANNOTATION_DB_PATH, filename)):
        link = make_annotation_link_strains(row['RandomName'], row['STRAIN'])
        if link:
            return f'<a title="{safe_random_name}" href="{link}">{safe_strain}</a>'
    return ""

def fasta_to_pandas(filename):
    ids = []
    seqs = []
    with open(filename, 'r') as f:
        current_seq = []
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if current_seq:
                    seqs.append("".join(current_seq))
                if "=" in line:
                    ids.append(line[1:].split("=")[0][:-2])
                else:
                    ids.append(line[1:])
                current_seq = []
            else:
                current_seq.append(line)
        # Append the last sequence
        if current_seq:
            seqs.append("".join(current_seq))
            
    return pd.DataFrame({"Header": ids, "Sequence": seqs})

def faa_viewer(request, strain):
    if any(x in strain for x in ['..', '"', '\'', '/']):
        return HttpResponseBadRequest("Invalid subject ID")

    
    file_name = strain.split(":")[0].strip()
    strain_og_name = strain.split(":")[1].strip()

    annotation_path = os.path.join(settings.ANNOTATION_DB_PATH, f"{file_name}.faa")

    if not os.path.isfile(annotation_path):
        return HttpResponseBadRequest("No results found for the given subject ID")

    faa_df = fasta_to_pandas(annotation_path)
    faa_df_html = faa_df.to_html(
        classes='display nowrap', 
        escape=True,
        table_id='faaTable',     
        index=False
    )

    return render(request, 'faa_viewer.html', {'faaTable': faa_df_html, 'strain_name': escape(strain_og_name)})

def generate_taxonomy_link(row):
    strain = str(row['STRAIN'])
    safe_strain = escape(strain)
    
    # First check the database directly (this is where new GTDB-Tk runs save their result)
    from .models import InhouseStrain
    db_strain = InhouseStrain.objects.filter(strain_id=strain).first()
    if db_strain and db_strain.taxonomy:
        link = reverse('baclab:taxonomy_viewer', kwargs={'strain': strain})
        return f'<a title="Taxonomy for {safe_strain}" href="{link}">View</a>'
    
    # Fallback to checking the TSV files
    tax_file_path = getattr(settings, 'INHOUSE_TAXONOMY_PATH', '')
    from .models import GlobalStrainResource
    res = GlobalStrainResource.objects.first()
    if res and res.taxonomy_db and os.path.exists(res.taxonomy_db.path):
        tax_file_path = res.taxonomy_db.path

    if os.path.exists(tax_file_path):
        try:
            tax_df = pd.read_csv(tax_file_path, sep="\t", engine='python', header=0)
            if strain in tax_df['Strain'].values:
                link = reverse('baclab:taxonomy_viewer', kwargs={'strain': strain})
                return f'<a title="Taxonomy for {safe_strain}" href="{link}">View</a>'
        except Exception:
            pass
            
    return ""

def taxonomy_viewer(request, strain):
    if any(x in strain for x in ['..', '"', '\'', '/']):
        return HttpResponseBadRequest("Invalid strain ID")
    
    tax_data = None
    
    # 1. First try the uploaded custom taxonomy DB (if available)
    from .models import GlobalStrainResource
    res = GlobalStrainResource.objects.first()
    if res and res.taxonomy_db and os.path.exists(res.taxonomy_db.path):
        try:
            tax_df = pd.read_csv(res.taxonomy_db.path, sep="\t", engine='python', header=0).fillna('NA')
            strain_tax = tax_df[tax_df['Strain'] == strain]
            if not strain_tax.empty:
                tax_data = strain_tax.iloc[0].to_dict()
        except Exception:
            pass
            
    # 2. If not found in uploaded DB (e.g. newly processed strain), fallback to GTDB-Tk generated DB
    if not tax_data and os.path.exists(settings.INHOUSE_TAXONOMY_PATH):
        try:
            tax_df = pd.read_csv(settings.INHOUSE_TAXONOMY_PATH, sep="\t", engine='python', header=0).fillna('NA')
            strain_tax = tax_df[tax_df['Strain'] == strain]
            if not strain_tax.empty:
                tax_data = strain_tax.iloc[0].to_dict()
        except Exception:
            pass
            
    # 3. If still not found, check the Django database for a raw string fallback
    if not tax_data:
        from .models import InhouseStrain
        db_strain = InhouseStrain.objects.filter(strain_id=strain).first()
        if db_strain and db_strain.taxonomy:
            tax_data = {'Strain': strain, 'classification': db_strain.taxonomy, 'Note': 'Full GTDB-Tk metrics missing from DB files (fallback view)'}

    if not tax_data:
        return HttpResponseBadRequest("Taxonomy not found for this strain in any database.")
        
    # Ensure taxonomic ranks are parsed if they exist as a raw string but not individually
    if 'Domain' not in tax_data and 'classification' in tax_data:
        raw_tax = str(tax_data.get('classification', ''))
        tax_parts = raw_tax.split(';')
        for part in tax_parts:
            if part.startswith('d__'): tax_data['Domain'] = part[3:]
            elif part.startswith('p__'): tax_data['Phylum'] = part[3:]
            elif part.startswith('c__'): tax_data['Class'] = part[3:]
            elif part.startswith('o__'): tax_data['Order'] = part[3:]
            elif part.startswith('f__'): tax_data['Family'] = part[3:]
            elif part.startswith('g__'): tax_data['Genus'] = part[3:]
            elif part.startswith('s__'): tax_data['Species'] = part[3:]
    
    return render(request, 'taxonomy_viewer.html', {'tax_data': tax_data})

def taxonomy_database_viewer(request):
    tax_file_path = settings.INHOUSE_TAXONOMY_PATH
    from .models import GlobalStrainResource
    res = GlobalStrainResource.objects.first()
    if res and res.taxonomy_db and os.path.exists(res.taxonomy_db.path):
        tax_file_path = res.taxonomy_db.path
        
    if not os.path.exists(tax_file_path):
        return render(request, 'taxonomy_database.html', {'TaxonomyTable': '<p>Taxonomy database has not been created or uploaded yet.</p>'})
    
    try:
        tax_df = pd.read_csv(tax_file_path, sep="\t", engine='python', header=0).fillna('NA')
        tax_df_html = tax_df.to_html(classes='display', escape=False, table_id='TaxonomyTable', index=False)
    except Exception as e:
        tax_df_html = f"<p>Error loading taxonomy database: {e}</p>"
        
    return render(request, 'taxonomy_database.html', {'TaxonomyTable': tax_df_html})

def phylogenetic_tree_viewer(request):
    from .models import GlobalStrainResource
    res = GlobalStrainResource.objects.first()
    
    file_path = None
    if res and res.phylogenetic_tree and os.path.exists(res.phylogenetic_tree.path):
        file_path = res.phylogenetic_tree.path
    elif os.path.exists(os.path.join(settings.PHYLOGENETIC_TREES_PATH, "myxo_tree.nwk")):
        file_path = os.path.join(settings.PHYLOGENETIC_TREES_PATH, "myxo_tree.nwk")
        
    if not file_path:
        return render(request, 'phylogenetic_tree.html', {'newick_data': ''})
        
    try:
        with open(file_path, 'r') as f:
            newick_data = f.read().strip()
    except Exception:
        newick_data = ''
        
    return render(request, 'phylogenetic_tree.html', {'newick_data': newick_data})

def generate_antismash_link(row):
    filename = f"{row['RandomName']}"
    og_name = f"{row['STRAIN']}"
    safe_strain = escape(str(row['STRAIN']))
    safe_random_name = escape(str(row['RandomName']))
    # Check if the specific folder exists dynamically or in the cached mapping
    if og_name in antismash_strains_name_mapping.keys() or os.path.isdir(os.path.join(settings.ANTISMASH_DATA_PATH, og_name)):
        link = make_antismash_link(antismash_strains_name_mapping.get(og_name, og_name))
        if link:
            return f'<a title="{safe_random_name}" href="{link}">{safe_strain}</a>'
    return ""

def make_antismash_link(og_name):
    """
    Expected sample_name pattern: contig<number>_<genome>.region<number>
    Produces: /sample?path_info=<genome>
    """
    return f'/sample?path_info={og_name}'

def download_file(request, file_type, strain_name):

    file_path = ""
    if file_type == "faa":
        mapped_name = annotation_strains_name_mapping.get(strain_name, strain_name)
        file_path = os.path.join(settings.ANNOTATION_DB_PATH, mapped_name + '.faa')
    if file_type == "gbk":
        mapped_name = annotation_strains_name_mapping.get(strain_name, strain_name)
        file_path = os.path.join(settings.ANNOTATION_DB_PATH, mapped_name + '.gbk')
    if file_type == "nwk":
        file_path = os.path.join(settings.PHYLOGENETIC_TREES_PATH, "myxo_tree.nwk")

    if file_path and os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=f"{strain_name}.{file_type}")

    raise Http404("File not found")

def _build_strains_table_html(strain_ids=None):
    strains_file_path = settings.INHOUSE_STRAINS_LIST
    columns = ["STRAIN", "RandomName"]
    try:
        strains_df = pd.read_csv(strains_file_path, sep="\t", engine='python', header=0, usecols=columns)
        strains_df = strains_df.drop_duplicates(subset=['STRAIN'], keep='last')

        if strain_ids is not None:
            strains_df = strains_df[strains_df['STRAIN'].isin(strain_ids)]

        strains_df["PROTEINS"] = strains_df.apply(generate_protein_link, axis=1)
        strains_df["ANTISMASH"] = strains_df.apply(generate_antismash_link, axis=1)
        strains_df["TAXONOMY (GTDBTK)"] = strains_df.apply(generate_taxonomy_link, axis=1)

        # Omit strains that have no results at all
        strains_df = strains_df[
            (strains_df["PROTEINS"] != "") |
            (strains_df["ANTISMASH"] != "") |
            (strains_df["TAXONOMY (GTDBTK)"] != "")
        ]
    except Exception:
        strains_df = pd.DataFrame(columns=columns)

    return strains_df.to_html(classes='display', escape=False, table_id='StrainsTable', index=False)


def _strain_resource_flags():
    from .models import GlobalStrainResource
    res = GlobalStrainResource.objects.first()

    tree_exists = False
    if res and res.phylogenetic_tree and os.path.exists(res.phylogenetic_tree.path):
        tree_exists = True
    elif os.path.exists(os.path.join(settings.PHYLOGENETIC_TREES_PATH, "myxo_tree.nwk")):
        tree_exists = True

    tax_exists = False
    if res and res.taxonomy_db and os.path.exists(res.taxonomy_db.path):
        tax_exists = True
    elif os.path.exists(settings.INHOUSE_TAXONOMY_PATH):
        tax_exists = True

    return tree_exists, tax_exists


def strains(request, strains_list):
    if strains_list != "inhouse":
        raise Http404("File not found")

    tree_exists, tax_exists = _strain_resource_flags()

    return render(request, 'strains.html', {
        'StrainsTable': _build_strains_table_html(),
        'tree_exists': tree_exists,
        'tax_exists': tax_exists,
        'page_title': 'All Strains Collection',
    })

def strain_collection(request, collection_slug):
    from .models import InhouseStrainCollection
    collection = get_object_or_404(InhouseStrainCollection, slug=collection_slug)
    strain_ids = list(collection.strains.values_list('strain_id', flat=True))
    tree_exists, tax_exists = _strain_resource_flags()

    return render(request, 'strains.html', {
        'StrainsTable': _build_strains_table_html(strain_ids=strain_ids),
        'tree_exists': tree_exists,
        'tax_exists': tax_exists,
        'page_title': collection.name,
    })

def write_parameters(post_request, output_dir):
    keys_to_skip = ["csrfmiddlewaretoken", "type", "fasta", "file", "use_example_data", "email"]

    # for blast
    if "co-occurence" not in post_request.keys():
        keys_to_skip.append("min_pident_cooccurence")
        keys_to_skip.append("min_qcovs_cooccurence")

    with open(f"{os.path.join(output_dir, 'run_parameters.txt')}", "w") as ofile:
        for key in post_request.keys():
            if key not in keys_to_skip:
                ofile.write(f"{key}:{post_request[key]}\n")

def mark_job_status(job_id, status, error_message=None, error_log=None):
    """Updates the JobRecord in the database."""
    try:
        jr = JobRecord.objects.get(job_id=job_id)
    except JobRecord.DoesNotExist:
        print(f"JobRecord with job_id {job_id} does not exist.")
        return

    now = timezone.now()
    jr.status = status
    if error_message:
        jr.error_message = error_message
    if error_log is not None:
        jr.error_log = error_log

    if status == "running":
        jr.started_at = now
    elif status in ["finished", "failed"]:
        jr.finished_at = now
        if not jr.started_at:
            jr.started_at = jr.queued_at
            print(f"Warning: Job {job_id} had no started_at time. Setting it to queued_at time: {jr.queued_at}")

    jr.save()

def get_job_status(job_id):
    """Retrieves the status of a job from the database."""
    try:
        jr = JobRecord.objects.get(job_id=job_id)
        return jr.status, jr.error_message
    except JobRecord.DoesNotExist:
        print(f"JobRecord with job_id {job_id} does not exist.")
        return None
    

def job_progress(request, job_id):
    """
    API endpoint for the frontend to poll job progress.
    """
    res = AsyncResult(job_id)
    response_data = {
        'state': res.state,
    }
    if res.state == 'PROGRESS':
        response_data['progress'] = res.info.get('progress', 0)
        response_data['message'] = res.info.get('message', 'Processing...')
    elif res.state == 'FAILURE':
        response_data['message'] = str(res.info)
    
    return JsonResponse(response_data)