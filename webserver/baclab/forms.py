from django import forms
from django.core.exceptions import ValidationError

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

class InhouseStrainBulkUploadForm(forms.Form):
    zip_file = forms.FileField(label="ZIP of genome FASTA files")
    run_prokka = forms.BooleanField(required=False, initial=True, label="Run Prokka")
    run_antismash = forms.BooleanField(required=False, initial=True, label="Run antiSMASH")
    run_gtdbtk = forms.BooleanField(required=False, initial=True, label="Run GTDB-Tk")

    def clean_zip_file(self):
        f = self.cleaned_data['zip_file']
        if not f.name.lower().endswith('.zip'):
            raise ValidationError("Please upload a .zip archive.")
        return f