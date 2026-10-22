"""Capture the pages of this installation for the clickable static demonstrations (demo/build_demo.py).

The real pages are fetched with the Django test client and written to a folder exactly as the server sends them, plus `manifest.json` (which
URL is which file, the page to start with, a few texts), `theme.json` (the colours of the administrator's theme) and `static/` (the stylesheets,
scripts, fonts and pictures the pages use that are not part of the portal's own static folder, e.g. Django's admin). Three profiles:

  site    an anonymous visitor: home, guides, contact, terms, every tool's page and the results page of its example job
          (run `manage.py prerun_examples` first)
  user    a logged-in laboratory member (--login m.schumacher): the same, plus "my jobs" (own runs and the group's), the pages of some runs
          (key findings, methods, results), projects, API keys - needs accounts (ACCOUNTS_ENABLED=True) and, e.g., `manage.py create_demo_data`
  admin   an administrator (--login admin): the admin site, found by following its links (lists, a few change forms, system status, usage,
          the live monitor with one snapshot of its data)

    python manage.py export_site --profile admin --login admin --out /data/site_admin
    podman cp <container>:/data/site_admin/. demo/data/admin/
"""
import json
import os
import re
from html import escape, unescape
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from baclab.models import JobRecord, Project, ThemeSettings
from baclab.demo_capture import MAX_REPORT_BYTES, demo_tools, fetch_bytes, inline_images, inline_report, result_job_id

FIXED_PAGES = [('/', 'home'), ('/guides/', 'guides'), ('/about/', 'about'), ('/terms/', 'terms'), ('/results/', 'results'), ('/qrcode/', 'qrcode')]
RIBBONS = {
    'site': 'Static demonstration of BacLab: the pages are captured from a real installation and show real example results. Nothing can be submitted here.',
    'user': 'Demonstration: logged in as a laboratory member (accounts, groups, my jobs). Captured from a real installation with demonstration data; nothing can be changed.',
    'admin': 'Demonstration of the administration pages, captured from a real installation with demonstration data; nothing can be changed.',
}

ADMIN_SKIP = re.compile(r'/(logout|password_change|delete|history|autocomplete|jsi18n|r/\d+)/|/export|download')
ADMIN_CAPS = {'change': 2, 'add': 1}   # change forms and add forms kept per model
ADMIN_MAX_PAGES = 140


def slug(url):
    parts = urlsplit(url)
    text = (parts.path.strip('/') + ('-' + parts.query if parts.query else '')) or 'home'
    return re.sub(r'[^a-zA-Z0-9]+', '-', text).strip('-').lower()[:70] or 'page'


class Command(BaseCommand):
    help = 'Writes the pages of a clickable static demonstration.'

    def add_arguments(self, parser):
        parser.add_argument('--out', default=os.path.join(settings.MEDIA_ROOT, 'site_export'))
        parser.add_argument('--profile', choices=['site', 'user', 'admin'], default='site')
        parser.add_argument('--login', help='user name to log in as (profiles user and admin)')
        parser.add_argument('--job', action='append', default=[], help='tool=job id: show this job as the example result of the tool')

    # ---- fetching ----
    def fetch(self, url):
        response = self.client.get(url, follow=True)
        if response.status_code != 200 or 'text/html' not in response.get('Content-Type', ''):
            return None
        return response.content.decode('utf-8', 'replace')

    def inline_reports(self, html):
        """An <iframe src="/report-file/..."> becomes an <iframe srcdoc="..."> that carries the report (scripts, pictures and all)."""
        def swap(match):
            tag = match.group(0)
            src = re.search(r'\bsrc="([^"]+)"', tag)
            if not src or src.group(1).startswith(('http', 'data:')):
                return tag
            url = unescape(src.group(1))
            status, body, _ = fetch_bytes(self.client, url)
            if status != 200:
                return '<p>The interactive report is not part of the demonstration.</p>'
            doc = inline_report(self.client, body.decode('utf-8', 'replace'), url)
            if len(doc) > MAX_REPORT_BYTES:
                return '<p>The interactive report is not part of the demonstration (too large).</p>'
            return re.sub(r'\bsrc="[^"]+"', lambda _: 'srcdoc="' + escape(doc, quote=True) + '"', tag, count=1)
        return inline_images(self.client, re.sub(r'<iframe\b[^>]*>', swap, html))

    def save(self, key, url, html):
        if key in self.manifest['pages']:
            return
        html = self.inline_reports(html)
        with open(os.path.join(self.out, f'{key}.html'), 'w', encoding='utf-8') as handle:
            handle.write(html)
        self.manifest['pages'][key] = url
        self.manifest['aliases'][url] = key

    def capture(self, url, key=None):
        html = self.fetch(url)
        if not html:
            return None
        key = key or slug(url)
        self.save(key, url, html)
        return key

    def fetch_ok(self, url, key):
        html = self.fetch(url)
        if not html or any(text in html for text in ('did not produce any results', 'Job ID not found', 'Job is running', 'Job is queued', 'is private')):
            return False
        self.save(key, url, html)
        return True

    # ---- profiles ----
    def tool_pages(self):
        jobs = dict(item.split('=', 1) for item in self.options['job'])
        for tool in demo_tools():
            if not self.capture(tool.url, f'tool-{tool.name}'):
                continue
            self.manifest['tools'][tool.name] = {'title': tool.title, 'category': tool.category}
            job_id = result_job_id(tool, jobs)
            key = f'results-{tool.name}'
            if self.fetch_ok(f'/results/?job_id={job_id}', key):
                self.manifest['aliases'][f'/example-results/{tool.name}/'] = key
                self.manifest['aliases'][f'/results/?job_id={tool.name}-EXAMPLE'] = key
                self.manifest['tools'][tool.name]['results'] = key

    def profile_site(self):
        for url, key in FIXED_PAGES:
            self.capture(url, key)
        self.tool_pages()

    def profile_user(self):
        user = get_user_model().objects.get(username=self.options['login'])
        for url, key in FIXED_PAGES:
            self.capture(url, key)
        self.capture('/my-jobs/', 'my-jobs')
        self.capture('/my-jobs/?scope=group', 'my-jobs-group')
        self.capture('/my-jobs/api-keys/', 'api-keys')
        for project in Project.objects.filter(owner=user)[:4]:
            self.capture(f'/projects/{project.pk}/', f'project-{project.pk}')
        seen_tools, picked = set(), []
        for job in JobRecord.objects.filter(owner=user).order_by('-queued_at'):
            if job.job_type not in seen_tools or job.status != 'finished':
                seen_tools.add(job.job_type)
                picked.append(job)
            if len(picked) >= 12:
                break
        group_jobs = list(JobRecord.objects.filter(group=user.profile.group, private=False).exclude(owner=user).order_by('-queued_at')[:5])
        for number, job in enumerate(picked + group_jobs, 1):
            self.capture(f'/my-jobs/{job.job_id}/', f'job-{number}')
            if job.status == 'finished':
                self.fetch_ok(f'/results/?job_id={job.job_id}', f'jobresults-{number}')
                self.capture(f'/my-jobs/{job.job_id}/methods/', f'methods-{number}')
                self.capture(f'/my-jobs/{job.job_id}/send/', f'send-{number}')
        self.tool_pages()
        self.manifest['user'] = {'username': user.username, 'group': str(user.profile.group)}

    def profile_admin(self):
        self.manifest['start'] = 'admin'
        queue, seen, counts = ['/admin/', '/admin/system-status/', '/admin/usage/', '/admin/monitor/'], set(), {}
        while queue and len(self.manifest['pages']) < ADMIN_MAX_PAGES:
            url = queue.pop(0)
            parts = urlsplit(url)
            path = parts.path
            if path in seen or ADMIN_SKIP.search(path) or parts.query:
                continue
            seen.add(path)
            model = re.match(r'/admin/([^/]+/[^/]+)/', path)
            kind = 'change' if path.endswith('/change/') else 'add' if path.endswith('/add/') else None
            if kind and model:
                counts[(model.group(1), kind)] = counts.get((model.group(1), kind), 0) + 1
                if counts[(model.group(1), kind)] > ADMIN_CAPS[kind]:
                    continue
            html = self.fetch(url)
            if not html:
                continue
            self.save('admin' if path == '/admin/' else slug(url), path, html)
            for link in re.findall(r'href="(/admin/[^"#]*)"', html):
                queue.append(unescape(link))
        data = self.client.get('/admin/monitor/data/?queue=1')
        if data.status_code == 200:
            self.manifest['files']['/admin/monitor/data/'] = data.content.decode('utf-8')
        self.manifest['aliases']['/admin'] = 'admin'

    # ---- static files that are not in the portal's own folder ----
    def collect_static(self):
        refs = set()
        for key in self.manifest['pages']:
            with open(os.path.join(self.out, f'{key}.html'), encoding='utf-8') as handle:
                refs.update(re.findall(r'(?:href|src)="/static/([^"?#]+)', handle.read()))
        done = set()
        while refs:
            rel = refs.pop()
            if rel in done:
                continue
            done.add(rel)
            found = finders.find(rel)
            if not found or not os.path.isfile(found):
                continue
            target = os.path.join(self.out, 'static', rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(found, 'rb') as source:
                data = source.read()
            with open(target, 'wb') as sink:
                sink.write(data)
            if rel.endswith('.css'):   # fonts and pictures a stylesheet points to
                for ref in re.findall(r'url\(["\']?([^)"\']+)', data.decode('utf-8', 'replace')):
                    ref = ref.split('?')[0].split('#')[0]
                    if not ref.startswith(('data:', 'http', '/')):
                        refs.add(os.path.normpath(os.path.join(os.path.dirname(rel), ref)))

    def handle(self, *args, **options):
        self.options, self.out = options, options['out']
        os.makedirs(self.out, exist_ok=True)
        for name in os.listdir(self.out):   # a capture replaces the one before it (pages that are gone must not linger)
            if name.endswith(('.html', '.json')):
                os.remove(os.path.join(self.out, name))
        self.client = Client(SERVER_NAME='localhost')
        profile = options['profile']
        if profile != 'site':
            if not options['login']:
                raise CommandError('--login <user name> is needed for this profile')
            self.client.force_login(get_user_model().objects.get(username=options['login']))
        self.manifest = {'profile': profile, 'ribbon': RIBBONS[profile], 'start': 'home', 'pages': {}, 'aliases': {}, 'tools': {}, 'files': {}}
        getattr(self, f'profile_{profile}')()
        self.collect_static()
        theme = ThemeSettings.objects.filter(pk=1).first()
        fields = (('primary', 'primary_color'), ('secondary', 'secondary_color'), ('background', 'background_color'), ('button', 'button_color'), ('text', 'text_color'))
        with open(os.path.join(self.out, 'theme.json'), 'w') as handle:
            json.dump({name: getattr(theme, field) for name, field in fields if theme and getattr(theme, field, None)}, handle)
        with open(os.path.join(self.out, 'manifest.json'), 'w') as handle:
            json.dump(self.manifest, handle, indent=2)
        self.stdout.write(self.style.SUCCESS(f"{len(self.manifest['pages'])} page(s) of profile {profile} written to {self.out}"))
