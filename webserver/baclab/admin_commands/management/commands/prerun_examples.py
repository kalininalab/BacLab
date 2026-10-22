from django.core.management.base import BaseCommand

from baclab import tool_catalog
from baclab.tool_views import example_exists, start_example
from baclab.toolkit import registry


class Command(BaseCommand):
    help = ('Queues the example job of every tool that has example data (the results behind "View Example Results"), so that all of them are '
            'ready before anyone clicks. Examples that exist already are left alone.')

    def add_arguments(self, parser):
        parser.add_argument('--tool', action='append', default=[], help='only this tool (repeatable)')

    def handle(self, *args, **options):
        enabled = tool_catalog.enabled_map()
        queued = 0
        for tool in registry.builtin_tools():
            if options['tool'] and tool.name not in options['tool']:
                continue
            if not tool.example or not tool_catalog.is_enabled(tool.settings_key, enabled):
                continue
            if example_exists(tool):
                self.stdout.write(f'{tool.name}: already there')
                continue
            job_id, started = start_example(tool)
            queued += started
            self.stdout.write(f'{tool.name}: queued as {job_id}')
        self.stdout.write(self.style.SUCCESS(f'{queued} example job(s) queued. Follow them with ./baclab logs -f celeryworker.'))
