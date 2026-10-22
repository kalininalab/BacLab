from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('baclab', '0014_add_admin_help_text'),
    ]

    operations = [
        migrations.CreateModel(
            name='InhouseStrainCollection',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Display name shown in the Strains nav dropdown.', max_length=128, unique=True)),
                ('slug', models.SlugField(blank=True, help_text='Auto-generated from the name; used in the URL.', max_length=140, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('strains', models.ManyToManyField(blank=True, related_name='collections', to='baclab.inhousestrain')),
            ],
            options={
                'verbose_name': 'Inhouse Strain Collection',
                'verbose_name_plural': 'Inhouse Strain Collections',
                'ordering': ['name'],
            },
        ),
    ]
