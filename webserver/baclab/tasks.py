from celery import shared_task
import os
import shutil
from .file_manager import FileManager
import csv
import json
import tempfile
import zipfile
import tarfile
from datetime import datetime
from django.conf import settings
from django.db.models import Q as models_Q
from .models import JobRecord, InhouseStrain, CustomDatabase
from .error_utils import format_error_log
from baclab.tools.registry import get_tool
from baclab.toolkit import registry as toolkit_registry


def is_kept(item, keep):
    """Results that are never cleaned: the ids in KEEP_RESULTS and the example results of the tools
    ("<tool>-EXAMPLE", also as "<tool>-EXAMPLE.zip" in the results folder)."""
    name = item[:-4] if item.endswith('.zip') else item
    return item in keep or name in keep or name.endswith('-EXAMPLE')


def remove_old_subdirs(dir, max_age, keep, overrides=None):
    """Delete the job folders (and result archives) in dir that are older than max_age days."""
    if not os.path.isdir(dir):
        return

    now = datetime.now()

    for item in os.listdir(dir):
        if is_kept(item, keep):
            continue

        path = os.path.join(dir, item)
        is_archive = os.path.isfile(path) and item.endswith('.zip')
        if not (os.path.isdir(path) or is_archive):
            continue

        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        diff = now - mtime

        job = item[:-4] if is_archive else item
        if diff.days > (overrides or {}).get(job, max_age):   # an owner can ask to keep a job longer
            if is_archive:
                os.remove(path)
            else:
                shutil.rmtree(path, ignore_errors=True)


@shared_task
def clean_old_results():
    print("Cleaning old results...")
    overrides = dict(JobRecord.objects.filter(retention_days__isnull=False).values_list('job_id', 'retention_days'))
    remove_old_subdirs(settings.RESULTS_DIR, settings.MAX_RESULTS_AGE, settings.KEEP_RESULTS, overrides)
    remove_old_subdirs(settings.UPLOAD_DIR, settings.MAX_RESULTS_AGE, settings.KEEP_RESULTS, overrides)
    remove_old_subdirs(settings.DOWNLOAD_DIR, settings.MAX_RESULTS_AGE, settings.KEEP_RESULTS, overrides)

    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=settings.MAX_RESULTS_AGE)
    # records of jobs an owner asked to keep longer stay as long as their results
    deleted_count, _ = JobRecord.objects.filter(queued_at__lt=cutoff, retention_days__isnull=True).delete()
    print(f"Deleted {deleted_count} old JobRecords.")


@shared_task
def process_inhouse_strain(strain_id):
    strain = InhouseStrain.objects.get(strain_id=strain_id)
    strain.status = "running"
    strain.error_message = ""
    strain.save()

    step = "init"
    tool_name = "inhouse_strain"

    try:
        # Define directories
        strains_db_dir = os.path.dirname(settings.INHOUSE_STRAINS_LIST)
        strain_dir = os.path.join(strains_db_dir, "strains", strain.strain_id)
        os.makedirs(strain_dir, exist_ok=True)

        # Copy FASTA to the strain directory
        genome_path = os.path.join(strain_dir, f"{strain.strain_id}.fasta")
        if not os.path.exists(genome_path):
            shutil.copy2(strain.genome_fasta.path, genome_path)

        # List the strain immediately so partial results are visible on the Strains
        # page even if a later pipeline step fails - each result column checks its
        # own output on disk/DB independently, so this doesn't show fake results.
        tsv_path = os.path.join(strains_db_dir, "Inhouse_strains.tsv")
        file_exists = os.path.exists(tsv_path)
        if not file_exists:
            with open(tsv_path, "w", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["STRAIN", "RandomName"])

        strain_exists = False
        with open(tsv_path, "r") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) > 0 and row[0] == strain.strain_id:
                    strain_exists = True
                    break

        if not strain_exists:
            with open(tsv_path, "a", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow([
                    strain.strain_id,
                    strain.strain_id
                ])

        # Run selected pipelines using modular tool wrappers
        # Prokka
        if strain.run_prokka:
            step = "prokka_processing"
            tool_name = "prokka"
            prokka_out = os.path.join(strain_dir, "prokka")
            prokka_tool = get_tool('prokka')(
                job_id=strain.strain_id,
                input_dir=strain_dir,
                output_dir=prokka_out,
                cores=8
            )
            prokka_tool.run_single_genome(genome_path, prokka_out)

        # AntiSMASH
        if strain.run_antismash:
            step = "antismash_processing"
            tool_name = "antismash"
            antismash_out = os.path.join(strain_dir, "antismash")
            antismash_tool = get_tool('antismash')(
                job_id=strain.strain_id,
                input_dir=strain_dir,
                output_dir=antismash_out,
                cores=8
            )
            antismash_tool.run_single_genome(genome_path, antismash_out, strain.strain_id)

        # GTDB-Tk
        if strain.run_gtdbtk:
            step = "gtdbtk_processing"
            tool_name = "taxonomy"
            gtdbtk_out = os.path.join(strain_dir, "gtdbtk")
            tax_tool = get_tool('taxonomy')(
                job_id=strain.strain_id,
                input_dir=strain_dir,
                output_dir=gtdbtk_out,
                cores=8
            )
            classification = tax_tool.run_gtdbtk_inhouse(strain_dir)
            if classification:
                strain.taxonomy = classification

        # Copy Prokka FAA and GBK to AnnotationDB
        if strain.run_prokka:
            step = "prokka_post_process"
            tool_name = "prokka"
            prokka_out = os.path.join(strain_dir, "prokka")
            prokka_tool = get_tool('prokka')(
                job_id=strain.strain_id,
                input_dir=strain_dir,
                output_dir=prokka_out,
                cores=8
            )
            prokka_tool.post_process_strain(prokka_out, strain.strain_id)

        # Copy AntiSMASH results to AntismashDB
        if strain.run_antismash:
            step = "antismash_post_process"
            tool_name = "antismash"
            antismash_out = os.path.join(strain_dir, "antismash")
            antismash_tool = get_tool('antismash')(
                job_id=strain.strain_id,
                input_dir=strain_dir,
                output_dir=antismash_out,
                cores=8
            )
            antismash_tool.copy_to_antismash_db(antismash_out, strain.strain_id)

        strain.status = "completed"
        strain.error_message = ""
        strain.save()

    except Exception as e:
        strain.status = "failed"
        strain.error_message = str(e)
        stdout = getattr(e, "stdout", "") or getattr(e, "output", "") or ""
        stderr = getattr(e, "stderr", "") or ""
        returncode = getattr(e, "returncode", None)
        strain.error_log = format_error_log(
            exc=e,
            step=step,
            tool_name=tool_name,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode
        )
        strain.save()


@shared_task
def build_custom_database(db_id):
    custom_db = CustomDatabase.objects.get(id=db_id)
    custom_db.status = "building"
    custom_db.error_message = ""
    custom_db.save()

    try:
        with tempfile.TemporaryDirectory() as tmpdirname:
            uploaded_file = custom_db.input_files.path

            try:
                FileManager.extract_archive(uploaded_file, tmpdirname)
            except ValueError:
                FileManager.copy_file(uploaded_file, os.path.join(tmpdirname, os.path.basename(uploaded_file)))

            tool = toolkit_registry.get(custom_db.tool)
            builder = getattr(tool, 'build_custom_database', None)
            if builder is None:
                raise ValueError(f"The tool '{custom_db.tool}' does not take custom databases.")
            builder(tmpdirname, custom_db.db_name)

        custom_db.status = "ready"
        custom_db.save()
    except Exception as e:
        custom_db.status = "failed"
        custom_db.error_message = str(e)
        custom_db.save()

from celery import chain

@shared_task
def run_single_tool_task(tool_name: str, job_id: str, input_dir: str, output_dir: str, options: dict):
    from baclab.tools.registry import get_tool
    tool = get_tool(tool_name)(job_id=job_id, input_dir=input_dir, output_dir=output_dir)
    tool.execute(options)
    return True

@shared_task
def zip_job_results_task(previous_result, job_id: str, output_dir: str, zip_path: str):
    from baclab.file_manager import FileManager
    import os
    if not os.path.exists(zip_path):
        write_citation_file(output_dir, job_type=job_id.split('-')[0])
        FileManager.zip_directory(output_dir, zip_path)
    # Also update DB status here
    from baclab.models import JobRecord
    JobRecord.objects.filter(job_id=job_id).update(status='finished')
    return True


def write_citation_file(output_dir: str, job_type: str = None):
    """
    Drops a CITATION.txt into a job's output directory before it gets zipped,
    so "please cite" travels with the results into whatever paper or pipeline
    the user takes them to - not just the website, which they may never come
    back to. Includes both the specific tool's own citation(s) (from
    the tools' `citation=`, same source as the "Please cite" box on every tool page) and
    BacLab's own platform citation (PLATFORM_CITATION) - both live in
    baclab/citations.py, so editing that file is all that's ever needed here.
    """
    from baclab.citations import PLATFORM_CITATION, citations_for

    from baclab import tool_versions
    version = tool_versions.version_of(job_type) if job_type else ''
    lines = ["If you use these results in a publication, please cite:\n"]
    if version:
        lines.insert(0, f"Tool version used: {job_type} {version}")

    for entry in citations_for(job_type) if job_type else []:
        line = entry["text"]
        if entry.get("url"):
            line += f"\n{entry['url']}"
        lines.append(line)

    platform_line = PLATFORM_CITATION["text"]
    if PLATFORM_CITATION.get("url"):
        platform_line += f"\n{PLATFORM_CITATION['url']}"
    else:
        platform_line += "\n(manuscript in preparation - check the BacLab site for a DOI)"
    lines.append(f"And the BacLab platform itself:\n{platform_line}")

    try:
        with open(os.path.join(output_dir, "CITATION.txt"), "w") as f:
            f.write("\n\n".join(lines) + "\n")
    except OSError:
        pass

@shared_task
def run_server_benchmark_task(benchmark_id):
    from .models import ServerBenchmark
    import subprocess
    import json
    import os
    
    try:
        bench = ServerBenchmark.objects.get(id=benchmark_id)
    except ServerBenchmark.DoesNotExist:
        return
        
    script_path = "/app/benchmark_tools.py"
    outdir = f"/app/baclab/media/benchmarks/{benchmark_id}"
    
    cmd = [
        "python3", script_path, 
        "--download-representative",
        "--outdir", outdir,
        "--json-out", os.path.join(outdir, "results.json")
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Read the json results
        results_file = os.path.join(outdir, "results.json")
        if os.path.exists(results_file):
            with open(results_file, 'r') as rf:
                bench.results_json = json.load(rf)
            bench.status = "Completed"
        else:
            bench.status = "Failed (No JSON output)"
    except subprocess.CalledProcessError as e:
        bench.status = f"Failed (Code {e.returncode})"
    except Exception as e:
        bench.status = f"Error: {str(e)}"
        
    bench.save()


@shared_task
def build_custom_tool_environment(tool_id):
    """Create the conda environment of a tool added in the admin (CustomTool.environment_yml) on the persistent
    data volume, so it survives image updates. Progress and the end of the log are kept on the CustomTool row."""
    import subprocess
    import tempfile
    from .models import CustomTool
    from .toolkit import custom

    row = CustomTool.objects.get(pk=tool_id)
    CustomTool.objects.filter(pk=row.pk).update(env_status="building", env_log="")
    prefix = custom.env_prefix(row.name)
    log = ""
    try:
        os.makedirs(os.path.dirname(prefix), exist_ok=True)
        if os.path.isdir(prefix):
            shutil.rmtree(prefix)
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as handle:
            handle.write(row.environment_yml + "\n")
            yml_path = handle.name
        manager = shutil.which("mamba") or shutil.which("conda")
        proc = subprocess.run([manager, "env", "create", "-y", "-p", prefix, "-f", yml_path],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        log = proc.stdout[-20000:]
        os.unlink(yml_path)
        status = "ready" if proc.returncode == 0 else "failed"
    except Exception as err:
        log += f"\n{type(err).__name__}: {err}"
        status = "failed"
    CustomTool.objects.filter(pk=row.pk).update(env_status=status, env_log=log)
    return status


@shared_task
def check_system():
    """Hourly: tell the administrators about jobs that seem stuck and about disks that are nearly full (each only once)."""
    from datetime import timedelta
    from django.core.cache import cache
    from django.utils import timezone
    from . import monitoring, notify

    now = timezone.now()
    stuck = JobRecord.objects.filter(stuck_alert_sent=False).filter(
        models_Q(status="running", started_at__lt=now - timedelta(hours=settings.STUCK_RUNNING_HOURS)) |
        models_Q(status="queued", queued_at__lt=now - timedelta(hours=settings.STUCK_QUEUED_HOURS)))
    for job in stuck:
        notify.alert(f"[BacLab] Job {job.job_id} looks stuck",
                     f"Job {job.job_id} ({job.job_type}) has been {job.status} since {(job.started_at or job.queued_at):%Y-%m-%d %H:%M}.\n"
                     "Check the worker logs; in the admin (Job records) it can be marked as failed.")
        JobRecord.objects.filter(pk=job.pk).update(stuck_alert_sent=True)

    for row in monitoring.disk_report():
        key = f"disk-alert-{row['path']}"
        if row['percent'] >= settings.DISK_ALERT_PERCENT and not cache.get(key):
            notify.alert(f"[BacLab] {row['name']} is {row['percent']:.0f}% full",
                         f"{row['path']}: {monitoring.human(row['used'])} of {monitoring.human(row['total'])} used, {monitoring.human(row['free'])} free.")
            cache.set(key, True, 24 * 3600)   # at most one message per day
    return stuck.count()


@shared_task
def warn_expiring_results():
    """Daily: e-mail the owners (who gave an address) of jobs whose results are deleted within a week, once per job."""
    from . import email_policy, email_templates
    sent = 0
    for job in JobRecord.objects.filter(status="finished", expiry_warned=False, owner__isnull=False).select_related("owner"):
        if not 0 <= job.days_left < settings.EXPIRY_WARNING_DAYS:
            continue
        address = (job.owner.email or "").strip()
        if address and not email_policy.check(address):
            url = f"{settings.WEBSITE_LINK.rstrip('/')}/results/?job_id={job.job_id}"
            email_templates.send('expiry', address, job_id=job.job_id, job_name=job.label or job.job_id, tool=job.tool_label,
                                 results_url=url, expires=f"{job.expires_at:%Y-%m-%d}")
            sent += 1
        JobRecord.objects.filter(pk=job.pk).update(expiry_warned=True)
    return sent
