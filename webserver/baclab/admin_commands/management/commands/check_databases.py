import json

from django.core.management.base import BaseCommand

from baclab import db_status, tool_catalog


class Command(BaseCommand):
    help = "Reports which reference databases are installed under databases/ and which enabled tools are missing one."

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='machine readable output')
        parser.add_argument('--size', action='store_true', help='also compute the size of the installed databases (slow on big ones)')
        parser.add_argument('--strict', action='store_true', help='exit with status 1 when an enabled tool lacks a required database')

    def handle(self, *args, **options):
        enabled = tool_catalog.enabled_map()
        rows = db_status.overview(with_size=options['size'])
        report = []
        for row in rows:
            entry = row['entry']
            needed = any(tool_catalog.is_enabled(name, enabled) for name in entry['tools'])
            report.append({'key': entry['key'], 'title': entry['title'], 'installed': row['installed'], 'needed_by_enabled_tool': needed,
                           'optional': bool(entry.get('optional')), 'tools': entry['tools'], 'size': row['size'], 'approx_size': entry['size']})
        problems = [r for r in report if r['needed_by_enabled_tool'] and not r['installed'] and not r['optional']]

        if options['json']:
            self.stdout.write(json.dumps({'databases': report, 'missing_required': [r['key'] for r in problems]}, indent=2))
        else:
            for r in report:
                mark = 'OK     ' if r['installed'] else ('MISSING' if r['needed_by_enabled_tool'] and not r['optional'] else 'absent ')
                style = self.style.SUCCESS if r['installed'] else (self.style.ERROR if mark == 'MISSING' else self.style.WARNING)
                size = r['size'] or r['approx_size']
                self.stdout.write(f"{style(mark)}  {r['key']:<14} {r['title']}  [{size}]  used by: {', '.join(r['tools'])}")
            if problems:
                self.stdout.write(self.style.ERROR(f"\n{len(problems)} database(s) needed by enabled tools are not installed: {', '.join(r['key'] for r in problems)}"))
                self.stdout.write("Install with:  ./baclab db install " + ' '.join(r['key'] for r in problems))
            else:
                self.stdout.write(self.style.SUCCESS('\nAll databases needed by the enabled tools are installed.'))
        if options['strict'] and problems:
            raise SystemExit(1)
