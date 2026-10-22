import ckeditor.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('baclab', '0015_inhousestraincollection'),
    ]

    operations = [
        migrations.CreateModel(
            name='SitePage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('page_key', models.CharField(choices=[('terms', 'Terms and Conditions'), ('contact', 'Contact Us')], max_length=32, unique=True)),
                ('title', models.CharField(max_length=200)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Site Page',
                'verbose_name_plural': 'Site Pages (Terms & Contact)',
            },
        ),
        migrations.CreateModel(
            name='PageSection',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('heading', models.CharField(blank=True, help_text='Optional heading shown above this section.', max_length=200)),
                ('body', ckeditor.fields.RichTextField(help_text='Section content. Use the toolbar for formatting, links, and lists.')),
                ('is_published', models.BooleanField(default=True, help_text='Uncheck to hide this section from the live site without deleting it.')),
                ('order', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('page', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='baclab.sitepage')),
            ],
            options={
                'verbose_name': 'Page Section',
                'ordering': ['order'],
            },
        ),
    ]
