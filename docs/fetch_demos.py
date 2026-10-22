#!/usr/bin/env python3
"""Makes sure the static demonstration files are in docs/_demos/demos/ for the documentation build (published as /demos/<file>).
Files that are missing are fetched from the base URL in BACLAB_DEMO_URL if that is set; a missing demonstration never fails the build."""
import os
import shutil
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, '_demos', 'demos')
DIST = os.path.join(os.path.dirname(HERE), 'demo', 'dist')
NAMES = ['baclab-demo-site.html', 'baclab-demo-user.html', 'baclab-demo-admin.html']


def main():
    base = os.environ.get('BACLAB_DEMO_URL', '').rstrip('/')
    os.makedirs(TARGET, exist_ok=True)
    found = 0   # files that are in place afterwards
    for name in NAMES:
        target = os.path.join(TARGET, name)
        source = os.path.join(DIST, name)
        if os.path.isfile(source):
            shutil.copyfile(source, target)
            found += 1
        elif base:
            try:
                with urllib.request.urlopen(f'{base}/{name}', timeout=120) as response, open(target, 'wb') as handle:
                    shutil.copyfileobj(response, handle)
                found += 1
            except Exception as error:   # noqa: BLE001 - a missing demo must not break the documentation
                print(f'  {name}: not fetched ({error})')
        if os.path.isfile(target) and not (os.path.isfile(source) or base):
            found += 1
    print(f'{found} of {len(NAMES)} demonstration file(s) in {TARGET}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
