"""Guards for deployment files: mistakes here lose data silently."""
import os
import re

from django.conf import settings
from django.test import SimpleTestCase


class ComposeFilesTest(SimpleTestCase):
    def read(self, name):
        with open(os.path.join(str(settings.ROOT_DIR), name)) as handle:
            return handle.read()

    def test_postgres_data_volume_is_mounted_where_postgres_keeps_its_data(self):
        """A volume mounted anywhere else leaves the database in the container, and recreating the container deletes every user and job record."""
        for name in ('local.yml', 'production.yml'):
            targets = re.findall(r'-\s+\w*postgres_data:(\S+)', self.read(name))
            self.assertEqual(targets, ['/var/lib/postgresql/data'], name)

    def test_restart_never_recreates_the_database(self):
        with open(os.path.join(str(settings.ROOT_DIR), '..', 'baclab')) as handle:
            source = handle.read()
        restart = source[source.index("elif args.command == 'restart':"):source.index("elif args.command == 'logs':")]
        self.assertIn('--no-deps', restart)
        self.assertNotIn("'postgres'", restart)
