from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('baclab', '0013_jobrecord_email'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobrecord',
            name='job_type',
            field=models.CharField(blank=True, help_text="Identifies which pipeline created this record (e.g. 'blast', 'snippy').", max_length=64),
        ),
        migrations.AlterField(
            model_name='jobrecord',
            name='status',
            field=models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('finished', 'Finished'), ('failed', 'Failed')], default='queued', help_text='Current lifecycle state of the job.', max_length=16),
        ),
        migrations.AlterField(
            model_name='jobrecord',
            name='email',
            field=models.EmailField(blank=True, help_text='Optional email address to notify when the job finishes.', max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name='inhousestrain',
            name='genome_fasta',
            field=models.FileField(help_text="FASTA file for the strain's genome assembly.", upload_to='inhouse_uploads/'),
        ),
        migrations.AlterField(
            model_name='inhousestrain',
            name='run_prokka',
            field=models.BooleanField(default=True, help_text='Annotate the genome with Prokka.'),
        ),
        migrations.AlterField(
            model_name='inhousestrain',
            name='run_antismash',
            field=models.BooleanField(default=True, help_text='Scan for biosynthetic gene clusters with antiSMASH.'),
        ),
        migrations.AlterField(
            model_name='inhousestrain',
            name='run_gtdbtk',
            field=models.BooleanField(default=True, help_text='Classify taxonomy with GTDB-Tk.'),
        ),
    ]
