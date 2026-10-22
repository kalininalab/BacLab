from django.db import migrations


def fill_defaults(apps, schema_editor):
    """One row with the shipped texts, so the admin page shows what users get now and the administrator edits from there."""
    from baclab.email_templates import default_texts
    EmailMessages = apps.get_model('baclab', 'EmailMessages')
    if not EmailMessages.objects.exists():
        EmailMessages.objects.create(pk=1, **default_texts())


class Migration(migrations.Migration):

    dependencies = [
        ('baclab', '0022_email_messages'),
    ]

    operations = [
        migrations.RunPython(fill_defaults, migrations.RunPython.noop),
    ]
