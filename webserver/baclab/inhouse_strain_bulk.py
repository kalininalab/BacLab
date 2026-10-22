import os
import re
import tempfile

from django.core.files import File
from django.db import transaction

from .file_manager import FileManager
from .models import InhouseStrain
from .tasks import process_inhouse_strain

FASTA_EXTENSIONS = ('.fasta', '.fa', '.fna')
STRAIN_ID_RE = re.compile(r'^[A-Za-z0-9_.-]+$')


def _is_valid_fasta(path):
    with open(path, 'r', errors='ignore') as f:
        lines = [line.rstrip('\n') for line in f]

    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return False, "file is empty"
    if not non_empty[0].startswith('>'):
        return False, "no header line found"

    for i, line in enumerate(non_empty):
        if line.startswith('>'):
            if i + 1 >= len(non_empty) or non_empty[i + 1].startswith('>'):
                return False, "header with no sequence"

    return True, None


def bulk_create_inhouse_strains(zip_path, run_prokka, run_antismash, run_gtdbtk):
    """
    Extracts zip_path, validates each candidate FASTA file, creates an
    InhouseStrain and queues process_inhouse_strain for each valid one.
    """
    results = {
        'created': [],
        'skipped_exists': [],
        'skipped_duplicate': [],
        'invalid': [],
        'ignored': [],
    }

    with tempfile.TemporaryDirectory() as extract_dir:
        FileManager.extract_archive(zip_path, extract_dir)

        seen = set()
        for root, _, files in os.walk(extract_dir):
            for filename in sorted(files):
                ext = os.path.splitext(filename)[1].lower()
                if ext not in FASTA_EXTENSIONS:
                    results['ignored'].append(filename)
                    continue

                strain_id = os.path.splitext(filename)[0]
                if not STRAIN_ID_RE.match(strain_id):
                    results['invalid'].append((filename, "invalid strain name"))
                    continue

                if strain_id in seen:
                    results['skipped_duplicate'].append(strain_id)
                    continue

                if InhouseStrain.objects.filter(pk=strain_id).exists():
                    results['skipped_exists'].append(strain_id)
                    continue

                file_path = os.path.join(root, filename)
                valid, reason = _is_valid_fasta(file_path)
                if not valid:
                    results['invalid'].append((filename, reason))
                    continue

                seen.add(strain_id)
                strain = InhouseStrain(
                    strain_id=strain_id,
                    status="pending",
                    run_prokka=run_prokka,
                    run_antismash=run_antismash,
                    run_gtdbtk=run_gtdbtk,
                )
                with open(file_path, 'rb') as fh:
                    strain.genome_fasta.save(f"{strain_id}.fasta", File(fh), save=False)
                strain.save()

                transaction.on_commit(lambda s_id=strain_id: process_inhouse_strain.delay(s_id))
                results['created'].append(strain_id)

    return results
