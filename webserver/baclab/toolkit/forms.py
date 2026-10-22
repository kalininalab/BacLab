from django import forms
from django.core.exceptions import ValidationError

from .files import ZipRejected, zip_members

# Pre-packaged single-copy-gene sets shipped with GToTree (see `gtt-hmms`).
class UploadFileForm(forms.Form):
    file = forms.FileField(required=False)
    fasta = forms.CharField(label='fasta', max_length=100000, required=False)

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get('file')
        fasta = cleaned_data.get('fasta')

        provided_fields = sum([bool(file), bool(fasta)])

        if provided_fields > 1:
            raise ValidationError("You can only provide one of file or fastasequence")
        elif provided_fields == 0:
            raise ValidationError("You must provide one of file or fastasequence")

class PairedReadsUploadFileForm(forms.Form):
    """Used by fastp/spades: one required read file, one optional mate for paired-end reads."""
    read1 = forms.FileField(required=True)
    read2 = forms.FileField(required=False)

class MultiGenomeUploadFileForm(forms.Form):
    """Used by ani/fastaai/panaroo: 2+ genome files under one "genomes" multi-file input. A zip archive
    (the "archive" input, instead of the files) is only accepted when ALLOW_ZIP is set. FileField only ever validates the first value for a given key, so
    the real "how many/what kind" check reads the raw MultiValueDict via self.files."""
    MAX_GENOMES = 50
    MIN_GENOMES = 2
    ALLOWED_EXTENSIONS = ('.fasta', '.fa', '.fna')
    ALLOW_ZIP = False

    genomes = forms.FileField(required=False)
    archive = forms.FileField(required=False)

    def __init__(self, *args, allowed_extensions=None, **kwargs):
        self.allowed_extensions = allowed_extensions or self.ALLOWED_EXTENSIONS
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()

        uploaded = self.files.getlist('genomes')
        archive = self.files.get('archive')
        if archive:
            if not self.ALLOW_ZIP:
                raise ValidationError("Zip archives are not accepted by this tool.")
            if uploaded:
                raise ValidationError("Upload either a zip archive or separate files, not both.")
            try:
                zip_members(archive, self.allowed_extensions, self.MIN_GENOMES, self.MAX_GENOMES)
            except ZipRejected as error:
                raise ValidationError(str(error))
            archive.seek(0)   # checking read through the file; the job saves it from the start
            return cleaned_data
        if len(uploaded) < self.MIN_GENOMES:
            raise ValidationError(f"You must upload at least {self.MIN_GENOMES} genome files.")
        if len(uploaded) > self.MAX_GENOMES:
            raise ValidationError(f"You can upload at most {self.MAX_GENOMES} genome files at once.")

        for f in uploaded:
            if not f.name.lower().endswith(self.allowed_extensions):
                raise ValidationError(
                    f"\"{f.name}\" has an unsupported extension. Allowed extensions: {', '.join(self.allowed_extensions)}."
                )

        return cleaned_data

def genome_form(extensions, min_files=2, max_files=50, allow_zip=False):
    """Upload form for tools that take several genome files (under the "genomes" input), or, with
    allow_zip, one zip archive of them (under "archive"; unpack it with toolkit.unpack_archive)."""
    return type('GenomeUploadFileForm', (MultiGenomeUploadFileForm,),
                {'ALLOWED_EXTENSIONS': tuple(extensions), 'MIN_GENOMES': min_files, 'MAX_GENOMES': max_files, 'ALLOW_ZIP': allow_zip})

class BatchGenomeUploadFileForm(MultiGenomeUploadFileForm):
    """Used by tools that simply run once per uploaded genome (padloc/defensefinder/genovi): one
    or more files. Capped lower than the comparison tools since each genome is a separate run."""
    MAX_GENOMES = 20
    MIN_GENOMES = 1

class UploadJobIDForm(forms.Form):
    job_id = forms.CharField(label='job_id', max_length=100)

class TableSelection(forms.Form):
    featuresTable = forms.CharField(widget=forms.TextInput(attrs={'disabled': 'disabled'}))
    classificationTable = forms.CharField(widget=forms.TextInput(attrs={'disabled': 'disabled'}))

class DownloadResultsForm(forms.Form):
    download_results = forms.BooleanField(required=False)

class ContactForm(forms.Form):
    name = forms.CharField(max_length=1000)
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea)