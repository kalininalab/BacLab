"""What an administrator wants to know before the server fills up: disk, queues, workers."""
import os
import shutil
import subprocess
import time

from django.conf import settings

QUEUES = ('celery', 'fast', 'heavy')


def disk_report():
    """[{name, path, total, used, free, percent}] for the data and databases volumes."""
    rows = []
    for name, path in (('Data (jobs, results)', os.path.dirname(settings.UPLOAD_DIR.rstrip('/')) or '/data'),
                       ('Reference databases', settings.DATABASES_DIR)):
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        rows.append({'name': name, 'path': path, 'total': usage.total, 'used': usage.used, 'free': usage.free,
                     'percent': round(100 * usage.used / usage.total, 1) if usage.total else 0})
    return rows


def folder_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def queue_report():
    """{'lengths': {queue: waiting jobs}, 'workers': [names]}; empty parts when the broker/workers cannot be reached."""
    report = {'lengths': {}, 'workers': []}
    try:
        import redis
        client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=2)
        report['lengths'] = {queue: client.llen(queue) for queue in QUEUES}
    except Exception:
        pass
    try:
        from .taskapp.celery import app
        inspector = app.control.inspect(timeout=1)
        report['workers'] = sorted((inspector.ping() or {}).keys())
        served = {q['name'] for queues in (inspector.active_queues() or {}).values() for q in queues}
        # queues with waiting jobs that no worker listens to (e.g. a worker started from an older image): those jobs would wait forever
        report['unserved'] = sorted(name for name, waiting in report['lengths'].items() if waiting and name not in served) if report['workers'] else []
    except Exception:
        pass
    return report


def human(num_bytes):
    for unit in ('B', 'kB', 'MB', 'GB', 'TB'):
        if num_bytes < 1000 or unit == 'TB':
            return f'{num_bytes:.0f} {unit}' if unit == 'B' else f'{num_bytes:.1f} {unit}'
        num_bytes /= 1000.0


# ---- live machine load (host values: containers share the kernel, so /proc shows the whole server) ----
def _cpu_times(proc):
    """{'cpu': (busy, total), 'cpu0': ...} from /proc/stat."""
    times = {}
    with open(os.path.join(proc, 'stat')) as handle:
        for line in handle:
            if line.startswith('cpu'):
                name, *fields = line.split()
                values = [int(x) for x in fields[:8]]
                idle = values[3] + values[4]   # idle + iowait
                times[name] = (sum(values) - idle, sum(values))
    return times


def cpu_usage(proc='/proc', interval=0.25):
    """{'percent': total CPU %, 'cores': [per-core %]} measured over `interval` seconds."""
    first = _cpu_times(proc)
    time.sleep(interval)
    second = _cpu_times(proc)

    def percent(name):
        busy = second[name][0] - first[name][0]
        total = second[name][1] - first[name][1]
        return round(100.0 * busy / total, 1) if total > 0 else 0.0

    cores = sorted((n for n in second if n != 'cpu'), key=lambda n: int(n[3:]))
    return {'percent': percent('cpu'), 'cores': [percent(n) for n in cores]}


def memory_usage(proc='/proc'):
    """Bytes: total, available, used, swap total/used."""
    info = {}
    with open(os.path.join(proc, 'meminfo')) as handle:
        for line in handle:
            key, _, value = line.partition(':')
            info[key] = int(value.split()[0]) * 1024
    total, available = info.get('MemTotal', 0), info.get('MemAvailable', info.get('MemFree', 0))
    swap_total, swap_free = info.get('SwapTotal', 0), info.get('SwapFree', 0)
    return {'total': total, 'available': available, 'used': total - available, 'percent': round(100.0 * (total - available) / total, 1) if total else 0,
            'swap_total': swap_total, 'swap_used': swap_total - swap_free}


def load_average(proc='/proc'):
    try:
        with open(os.path.join(proc, 'loadavg')) as handle:
            return [float(x) for x in handle.read().split()[:3]]
    except OSError:
        return []


def gpu_usage():
    """List of GPUs seen by this container (empty when there is none or nvidia-smi is not available there)."""
    binary = shutil.which('nvidia-smi')
    if not binary:
        return []
    fields = 'index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw'
    try:
        out = subprocess.run([binary, f'--query-gpu={fields}', '--format=csv,noheader,nounits'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             universal_newlines=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 7:
            continue

        def number(text):
            try:
                return float(text)
            except ValueError:
                return None
        used, total = number(parts[3]), number(parts[4])
        gpus.append({'index': parts[0], 'name': parts[1], 'utilization': number(parts[2]), 'memory_used': used * 1024 ** 2 if used is not None else None,
                     'memory_total': total * 1024 ** 2 if total is not None else None,
                     'memory_percent': round(100.0 * used / total, 1) if used is not None and total else None,
                     'temperature': number(parts[5]), 'power': number(parts[6])})
    return gpus


def snapshot(include_queue=False, proc='/proc'):
    """Everything the live monitor shows, JSON-ready."""
    from .models import JobRecord
    running = JobRecord.objects.filter(status='running').order_by('started_at')
    data = {
        'time': time.time(), 'cpu': cpu_usage(proc), 'memory': memory_usage(proc), 'load': load_average(proc), 'gpus': gpu_usage(),
        'cpu_count': os.cpu_count(), 'disks': disk_report(),
        'jobs': {'running': [{'job_id': j.job_id, 'tool': j.tool_label, 'since': j.started_at.isoformat() if j.started_at else None} for j in running[:20]],
                 'running_count': running.count(), 'queued_count': JobRecord.objects.filter(status='queued').count()},
    }
    if include_queue:
        data['queue'] = queue_report()
    return data
