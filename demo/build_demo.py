#!/usr/bin/env python3
"""Builds self-contained HTML files that demonstrate BacLab without any server (standard library only):
  dist/baclab-demo-site.html   the real pages of an installation, clickable like the site itself (menus, tool pages, example results)
  dist/baclab-demo-user.html   the same, as a logged-in laboratory member (my jobs, groups, projects, API keys)
  dist/baclab-demo-admin.html  the administration pages
They use the same colours (the theme of the installation the pages were captured from, or --theme file.json).

Input: data/<site|user|admin>/*.html + manifest.json + theme.json, written by `manage.py export_site --profile ...`.
"""
import argparse
import base64
import glob
import gzip
import json
import mimetypes
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def pack(payload):
    """The data of a demonstration as gzip + base64 text: the browser unpacks it (DecompressionStream) - the files are 4-5 times smaller."""
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    return base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode('ascii')


def read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    with open(path, 'rb') as handle:
        return f"data:{mime};base64,{base64.b64encode(handle.read()).decode()}"


def embed_images(html):
    def swap(match):
        path = os.path.join(HERE, 'assets', 'img', match.group(1))
        if not os.path.exists(path):
            sys.exit(f'image not found: {path}')
        return data_uri(path)
    return re.sub(r'\{\{img:([^}]+)\}\}', swap, html)


def load_modules(folder):
    modules = []
    for path in sorted(glob.glob(os.path.join(HERE, folder, '*.json'))):
        module = json.loads(read(path))
        module.setdefault('id', module.get('name') or os.path.splitext(os.path.basename(path))[0])
        if 'html' in module:
            module['html'] = embed_images(module['html'])
        modules.append(module)
    return modules



STATIC = os.path.join(REPO, 'webserver', 'baclab', 'static')
MAX_INLINE_ASSET = 400 * 1024
THEME_VARS = {'primary': '--primary-color', 'secondary': '--secondary-color', 'background': '--bg-color', 'button': '--button-color', 'text': '--text-color'}


def load_theme(path=None):
    """{primary, secondary, background, button, text} - from --theme, else from the captured installation."""
    for candidate in (path, os.path.join(HERE, 'theme.json'), os.path.join(HERE, 'data', 'site', 'theme.json')):
        if candidate and os.path.exists(candidate):
            return json.loads(read(candidate))
    return {}


def theme_css(theme):
    if not theme:
        return ''
    return ':root { ' + ' '.join(f'{THEME_VARS[k]}: {v};' for k, v in theme.items() if k in THEME_VARS) + ' }'


def static_file(url_path, extra_root=None):
    """File behind /static/...: the portal's own static folder, or what the capture brought along (Django's admin files)."""
    rel = url_path[len('/static/'):]
    for root in (STATIC, extra_root):
        if root and os.path.isfile(os.path.join(root, rel)):
            return os.path.join(root, rel)
    return None


def inline_css_urls(css, css_url_path, extra_root=None):
    """url(...) of a stylesheet -> data URIs (fonts, images) when the file is there and not huge."""
    base = os.path.dirname(static_file(css_url_path, extra_root) or '')

    def swap(match):
        ref = match.group(2).split('?')[0].split('#')[0]
        if ref.startswith(('data:', 'http')) or not base:
            return match.group(0)
        target = os.path.normpath(os.path.join(base, ref))
        if os.path.isfile(target) and os.path.getsize(target) <= MAX_INLINE_ASSET:
            return f"url({data_uri(target)})"
        return match.group(0)
    return re.sub(r'url\((["\']?)([^)"\']+)\1\)', swap, css)


def cut_tables(html, limit=300):
    """Long result tables are cut (a page with 27,000 rows would be 10 MB): the first `limit` rows and a note."""
    def shorten(match):
        table = match.group(0)
        rows = re.findall(r'<tr\b.*?</tr>', table, re.S)
        body = [r for r in rows if '<td' in r]
        if len(body) <= limit:
            return table
        head = table[:table.find('<tbody')] if '<tbody' in table else table[:table.find(body[0])]
        return head + '<tbody>' + ''.join(body[:limit]) + f'</tbody></table><p style="color:#777">Demonstration: the first {limit} of {len(body)} rows.</p>'
    return re.sub(r'<table\b.*?</table>', shorten, html, flags=re.S)


# Things of the installation the pages were captured from that mean nothing in a demonstration: page key -> [(regex, replacement)]
PAGE_FILTERS = {
    'home': [(r'<p>\s*<h5>\s*Server status:.*?(?=<p style="margin-top: 1\.5rem;">)', '')],   # job counters of the test server
}


def build_profile(name, out, theme, links):
    """One clickable site from the pages captured in data/<name>/ (profiles: site = visitor, user = logged-in member, admin)."""
    folder = os.path.join(HERE, 'data', name)
    extra_static = os.path.join(folder, 'static')
    manifest = json.loads(read(os.path.join(folder, 'manifest.json')))
    css, js, pages = {}, {}, {}

    def stylesheet(match):
        path = match.group(1)
        if static_file(path, extra_static) is None:
            return ''
        if path not in css:
            css[path] = inline_css_urls(read(static_file(path, extra_static)), path, extra_static)
        return f'<!--css:{path}-->'

    def script(match):
        path = match.group(1)
        if static_file(path, extra_static) is None:
            return ''
        js.setdefault(path, read(static_file(path, extra_static)))
        return f'<!--js:{path}-->'

    def image(match):
        path = match.group(2)
        found = static_file(path, extra_static)
        return f'{match.group(1)}"{data_uri(found)}"' if found else match.group(0)

    for key in manifest['pages']:
        html = read(os.path.join(folder, f'{key}.html'))
        for pattern, replacement in PAGE_FILTERS.get(key, []):
            html = re.sub(pattern, replacement, html, flags=re.S)
        html = cut_tables(html)
        if key.startswith('tool-') and 'View Example Results' not in html and f"/example-results/{key[5:]}/" in manifest['aliases']:
            # a tool without example data of its own (added in the admin) still shows the results of its latest run
            button = (f'<div style="margin: 30px 50px 24px; display: flex; gap: 10px;"><a href="/example-results/{key[5:]}/" class="btn btn-small">View Example Results</a></div>')
            html = re.sub(r'(<div[^>]*id="email-input-container")', lambda m: button + m.group(1), html, count=1)
        html = re.sub(r'<link[^>]*rel="icon"[^>]*>', '', html)
        html = re.sub(r'<link[^>]*rel="stylesheet"[^>]*href="(/static/[^"]+)"[^>]*>', stylesheet, html)
        html = re.sub(r'<link[^>]*href="(/static/[^"]+\.css)"[^>]*rel="stylesheet"[^>]*>', stylesheet, html)
        html = re.sub(r'<script\b[^>]*\bsrc="(/static/[^"]+)"[^>]*>\s*</script>', script, html)
        html = re.sub(r'(\bsrc=)"(/static/[^"]+)"', image, html)
        pages[key] = html
    data = {
        'pages': pages, 'urls': manifest['pages'], 'aliases': manifest['aliases'], 'css': css, 'js': js, 'start': manifest.get('start', 'home'),
        'files': manifest.get('files', {}), 'theme_css': theme_css(theme), 'bridge': read(os.path.join(HERE, 'assets', 'site_bridge.js')),
    }
    html_links = ''.join(f' <a href="{href}">{label}</a>' for label, href in links)
    html = read(os.path.join(HERE, 'assets', 'site_template.html'))
    payload = pack(data)
    html = (html.replace('/*RIBBON*/', escape_html(manifest.get('ribbon', ''))).replace('/*LINKS*/', html_links)
            .replace('/*JS*/', read(os.path.join(HERE, 'assets', 'site.js'))).replace('/*DATA*/', payload))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as handle:
        handle.write(html)
    print(f"{out}: {len(html) / 1e6:.1f} MB, {len(pages)} pages, {len(css)} stylesheets, {len(js)} scripts")


def escape_html(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dist', default=os.path.join(HERE, 'dist'), help='folder for the finished files')
    parser.add_argument('--only', choices=['site', 'user', 'admin'], help='build only this one')
    parser.add_argument('--theme', help='JSON with primary, secondary, background, button, text colours for all files (default: the theme of the captured installation)')
    args = parser.parse_args()

    theme = load_theme(args.theme)
    profiles = [(name, os.path.join(args.dist, f'baclab-demo-{name}.html')) for name in ('site', 'user', 'admin')
                if os.path.exists(os.path.join(HERE, 'data', name, 'manifest.json')) and args.only in (None, name)]
    if not profiles:
        sys.exit('No captured pages in demo/data/site, user or admin: run `manage.py export_site` first.')
    names = {'site': 'Clickable site', 'user': 'Logged-in user', 'admin': 'Administration'}
    for name, out in profiles:
        links = [(names[n], os.path.relpath(f, args.dist)) for n, f in profiles if n != name]
        build_profile(name, out, theme, links)


if __name__ == '__main__':
    main()
