"""Fetch genome assemblies from NCBI by accession (GCF_/GCA_), so users need not download and re-upload them."""
import io
import os
import re
import shutil
import urllib.parse
import urllib.request
import zipfile

ACCESSION = re.compile(r'^GC[AF]_\d{9}\.\d+$')
API = 'https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{accession}/download'
MAX_ACCESSIONS = 50


def parse_accessions(text):
    """(valid accessions, invalid entries) from a free-text list separated by whitespace, commas or semicolons."""
    entries = [e for e in re.split(r'[\s,;]+', text or '') if e]
    seen, valid, invalid = set(), [], []
    for entry in entries:
        entry = entry.strip()
        if ACCESSION.match(entry):
            if entry not in seen:
                seen.add(entry)
                valid.append(entry)
        else:
            invalid.append(entry)
    return valid, invalid


def wanted_kind(extensions):
    """'fasta' for tools that read nucleotide FASTA, 'gbff' for GenBank-only tools."""
    lowered = {e.lower() for e in extensions}
    return 'fasta' if lowered & {'.fasta', '.fa', '.fna'} or not lowered else 'gbff'


def fetch_one(accession, target_dir, kind='fasta', timeout=300):
    """Download one assembly into target_dir as <accession>.fna / .gbff; returns the file name. Raises RuntimeError with a readable message."""
    annotation = 'GENOME_FASTA' if kind == 'fasta' else 'GENOME_GBFF'
    url = API.format(accession=accession) + '?' + urllib.parse.urlencode({'include_annotation_type': annotation, 'filename': f'{accession}.zip'})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'BacLab'}), timeout=timeout) as response:
            payload = response.read()
    except Exception as error:
        raise RuntimeError(f'Could not download {accession} from NCBI: {error}')
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        raise RuntimeError(f'NCBI returned no genome for {accession} (is the accession correct?)')
    suffixes = ('.fna', '.fa', '.fasta') if kind == 'fasta' else ('.gbff', '.gbk', '.gb')
    members = [m for m in archive.namelist() if m.lower().endswith(suffixes) and not m.endswith('/')]
    if not members:
        raise RuntimeError(f'NCBI has no {"FASTA" if kind == "fasta" else "GenBank"} file for {accession}.')
    name = f'{accession}{os.path.splitext(members[0])[1].lower()}'
    with archive.open(members[0]) as source, open(os.path.join(target_dir, name), 'wb') as out:
        shutil.copyfileobj(source, out)
    return name


def fetch_into(accessions, target_dir, extensions=()):
    """Download all accessions into target_dir; returns the file names."""
    os.makedirs(target_dir, exist_ok=True)
    kind = wanted_kind(extensions)
    return [fetch_one(accession, target_dir, kind) for accession in accessions]
