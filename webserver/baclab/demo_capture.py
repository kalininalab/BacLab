"""Helpers of the capture of pages for the static demonstrations (see admin_commands/management/commands/export_site.py): fetching pages and
files of this installation with the Django test client, putting their pictures, scripts and databases into the page, choosing which job's results to show."""
import base64
import json
import re
from html import unescape
from urllib.parse import urljoin

from . import tool_catalog
from .toolkit import registry

MAX_RESOURCE_BYTES = 8 * 1024 * 1024
MAX_REPORT_BYTES = 14 * 1024 * 1024


def fetch_bytes(client, url):
    """(status, body, content type) of a page or file of this installation."""
    response = client.get(url, follow=True)
    body = b''.join(response.streaming_content) if getattr(response, 'streaming', False) else response.content
    return response.status_code, body, response.get('Content-Type', '').split(';')[0] or 'application/octet-stream'


def data_uri(client, url):
    status, body, ctype = fetch_bytes(client, url)
    if status != 200 or len(body) > MAX_RESOURCE_BYTES:
        return None
    return f"data:{ctype};base64,{base64.b64encode(body).decode()}"


def inline_images(client, html, base='/'):
    """Pictures and PDFs a page shows from the installation's report files become part of the page; links to such pictures are unwrapped."""
    def local(ref):
        return ref and not ref.startswith(('data:', 'http:', 'https:', '//', '#', '/static/'))

    def image(match):
        tag = match.group(0)
        src = re.search(r'\bsrc="([^"]+)"', tag)
        if not src or not local(unescape(src.group(1))):
            return tag
        uri = data_uri(client, urljoin(base, unescape(src.group(1))))
        return tag.replace(src.group(0), f'src="{uri}"') if uri else tag

    def embedded(match):
        tag = match.group(0)
        ref = re.search(r'\b(data|src)="([^"#]+)(#[^"]*)?"', tag)
        if not ref or not local(unescape(ref.group(2))):
            return tag
        uri = data_uri(client, urljoin(base, unescape(ref.group(2))))
        return tag.replace(ref.group(0), f'{ref.group(1)}="{uri}{ref.group(3) or ""}"') if uri else tag

    html = re.sub(r'<img\b[^>]*>', image, html)
    html = re.sub(r'<(?:object|embed)\b[^>]*>', embedded, html)
    return re.sub(r'<a\b[^>]*href="[^"]*\.(?:svg|png|jpe?g|gif|pdf)(?:#[^"]*)?"[^>]*>(.*?)</a>', r'\1', html, flags=re.S)


def inline_report(client, doc, base):
    """A report that is a small web page of its own (BiG-SCAPE's viewer, GenoVi's plots...) becomes one self-contained document: its scripts,
    stylesheets and pictures are put into it, and a database it loads with XMLHttpRequest is embedded and handed out by a small shim."""
    def script(match):
        ref = match.group(1)
        if ref.startswith(('http:', 'https:', '//', 'data:')):
            return match.group(0)
        status, body, _ = fetch_bytes(client, urljoin(base, ref))
        if status != 200:
            return match.group(0)
        # as a data URL: no escaping problems ('<!--', '</script' inside the code), and the scripts still run in order
        return '<script src="data:text/javascript;base64,' + base64.b64encode(body).decode() + '"></script>'

    def style(match):
        ref = re.search(r'href="([^"]+)"', match.group(0))
        if not ref or ref.group(1).startswith(('http:', 'https:', '//', 'data:')):
            return match.group(0)
        status, body, _ = fetch_bytes(client, urljoin(base, ref.group(1)))
        return '<style>' + body.decode('utf-8', 'replace') + '</style>' if status == 200 else match.group(0)

    doc = re.sub(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*>\s*</script>', script, doc)
    doc = re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*>', style, doc)
    databases = {}
    for ref in set(re.findall(r"""\.open\(\s*['"]GET['"]\s*,\s*['"](\.?/?[^'"]+\.db)['"]""", doc)):
        status, body, _ = fetch_bytes(client, urljoin(base, ref))
        if status == 200 and len(body) <= MAX_RESOURCE_BYTES:
            databases[ref.lstrip('./')] = base64.b64encode(body).decode()
    if databases:
        shim = ('<script>(function(){var files=' + json.dumps(databases) + ';var open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send;'
                'XMLHttpRequest.prototype.open=function(m,u){this.__bundled=files[String(u).replace(/^\\.?\\//,"")]||null;return open.apply(this,arguments);};'
                'XMLHttpRequest.prototype.send=function(){if(this.__bundled){var b=atob(this.__bundled),a=new Uint8Array(b.length),self=this;'
                'for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i);Object.defineProperty(self,"response",{value:a.buffer});'
                'var fire=function(){setTimeout(function(){if(self.onload)self.onload({});},0);};'
                'if(document.readyState==="complete")fire();else window.addEventListener("load",fire);return;}return send.apply(this,arguments);};})();</script>')
        doc = doc.replace('<head>', '<head>' + shim, 1) if '<head>' in doc else shim + doc
    return inline_images(client, doc, base)


def demo_tools():
    """Every tool that is switched on: the tool folders and the tools an administrator added in the browser."""
    enabled = tool_catalog.enabled_map()
    return [tool for tool in registry.all_tools()
            if (getattr(tool, 'admin_enabled', False) if tool.source == 'custom' else tool_catalog.is_enabled(tool.settings_key, enabled))]


def result_job_id(tool, overrides):
    """The job whose results the demonstration shows: the one named on the command line, the tool's example job (<name>-EXAMPLE) or - for
    tools without example data, such as those added in the admin - the latest finished public job of the tool."""
    from baclab.models import JobRecord
    if tool.name in overrides:
        return overrides[tool.name]
    example = f'{tool.name}-EXAMPLE'
    if tool.example or JobRecord.objects.filter(job_id=example, status='finished').exists():
        return example
    latest = JobRecord.objects.filter(job_type=tool.name, status='finished', private=False).order_by('-queued_at').first()
    return latest.job_id if latest else example
