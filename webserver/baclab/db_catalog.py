"""Every reference database / model the platform can use, how to tell whether it is installed and how to install it.

Deliberately plain Python 3.6 without Django imports: the host-side `baclab` command (which runs on the server's own
python3, outside the containers) loads this very file, and so do the admin status page and `manage.py check_databases`.

A database lives in a folder under databases/ (mounted at /databases in the containers). `markers_all` are glob patterns
(relative to databases/) that must all match something, `markers_any` need at least one match. `install` says how to
fill the folder; installers run in the `dbtools` container, which has /databases writable and all conda environments:

    {'kind': 'shell', 'command': ...}        bash commands (conda is set up; `baclab-fetch URL FILE` (webserver/tools/_bin) downloads with retries)
    {'kind': 'tool-script', 'script': ...}   tools/<script> <target folder>, a helper shipped with the tool
    {'kind': 'host-script', 'script': ...}   an interactive script of the repository root (asks questions)
    {'kind': 'manual', 'note': ...}          nothing to automate; the note tells the administrator what to do
"""
import glob
import os

CONDA = 'source /opt/conda/etc/profile.d/conda.sh && '

DATABASES = [
    # ---- tools with hand-written pages ----
    {'key': 'blast', 'title': 'BLAST databases', 'tools': ['blast'], 'size': '1 GB - 600 GB',
     'markers_any': ['BlastDB/*.nin', 'BlastDB/*.pin', 'BlastDB/*.ndb', 'BlastDB/*.pdb', 'BlastDB/*.nal', 'BlastDB/*.pal'],
     'install': {'kind': 'host-script', 'script': 'manage_blast_db.sh'},
     'note': 'Public NCBI databases (swissprot, nr, nt, ...) or your own FASTA files; listed on the BLAST page through BlastDB/database_options.json.'},
    {'key': 'taxonomy16s', 'title': 'Taxonomy Finder: NCBI taxonomy + 16S rRNA BLAST database', 'tools': ['taxonomyfinder'], 'size': '2 GB',
     'markers_all': ['NCBI_Taxa/taxa.sqlite', 'BlastDB/16S_ribosomal_RNA.n*'],
     'install': {'kind': 'shell', 'command': 'mkdir -p /databases/BlastDB /databases/NCBI_Taxa && cd /databases/BlastDB && '
                 'baclab-fetch https://ftp.ncbi.nlm.nih.gov/blast/db/16S_ribosomal_RNA.tar.gz 16S_ribosomal_RNA.tar.gz && '
                 'tar --no-same-owner -xzf 16S_ribosomal_RNA.tar.gz && rm 16S_ribosomal_RNA.tar.gz && ' + CONDA + 'conda activate server_taxonomy && '
                 'python -c "from ete3 import NCBITaxa; NCBITaxa(dbfile=\'/databases/NCBI_Taxa/taxa.sqlite\').update_taxonomy_database()"'}},
    {'key': 'gtdbtk', 'title': 'GTDB-Tk reference data (release 232)', 'tools': ['taxonomyfinder'], 'size': '56 GB',
     'markers_all': ['GtdbtkDB/release232/taxonomy'],
     'install': {'kind': 'shell', 'command': 'mkdir -p /databases/GtdbtkDB/release232 && cd /databases/GtdbtkDB && '
                 'baclab-fetch https://data.gtdb.aau.ecogenomic.org/releases/release232/232.0/auxillary_files/gtdbtk_package/full_package/gtdbtk_r232_data.tar.gz gtdbtk_data.tar.gz && '
                 'tar --no-same-owner -xzf gtdbtk_data.tar.gz -C release232 --strip-components=1 && rm gtdbtk_data.tar.gz'}},
    {'key': 'antismash', 'title': 'antiSMASH databases', 'tools': ['annotationPipeline'], 'size': '5-10 GB',
     'markers_all': ['AntismashDB/pfam'],
     'install': {'kind': 'shell', 'command': 'mkdir -p /databases/AntismashDB && ' + CONDA + 'conda activate server_antismash && download-antismash-databases --database-dir /databases/AntismashDB'}},
    {'key': 'bakta', 'title': 'Bakta database (light)', 'tools': ['annotationPipeline'], 'size': '1.5 GB',
     'markers_any': ['BaktaDB/amrfinderplus', 'BaktaDB/db/version.json', 'BaktaDB/db-light/version.json'],
     'install': {'kind': 'shell', 'command': 'mkdir -p /databases/BaktaDB && ' + CONDA + 'conda activate server_bakta && bakta_db download --output /databases/BaktaDB --type light'}},
    {'key': 'cblaster', 'title': 'cblaster: MIBiG 4.0 local database', 'tools': ['cblaster'], 'size': '0.2 GB',
     'markers_all': ['CblasterDB/mibig_4.0.sqlite3'],
     'install': {'kind': 'host-script', 'script': 'manage_cblaster_db.sh'}},
    {'key': 'plasmidfinder', 'title': 'PlasmidFinder database', 'tools': ['plasmidfinder'], 'size': '0.1 GB',
     'markers_all': ['PlasmidFinderDB/config'],
     'install': {'kind': 'shell', 'command': 'rm -rf /databases/PlasmidFinderDB && mkdir -p /databases/PlasmidFinderDB && cd /databases/PlasmidFinderDB && '
                 'baclab-fetch https://bitbucket.org/genomicepidemiology/plasmidfinder_db/get/master.tar.gz db.tar.gz && '
                 'tar --no-same-owner -xzf db.tar.gz --strip-components=1 && rm db.tar.gz && ' + CONDA + 'conda activate server_plasmidfinder && python INSTALL.py'}},
    {'key': 'amrfinderplus', 'title': 'AMRFinderPlus reference database', 'tools': ['amrfinderplus'], 'size': '0.5 GB',
     'markers_all': ['AmrfinderplusDB/*/AMRProt*'],
     'install': {'kind': 'shell', 'command': 'mkdir -p /databases/AmrfinderplusDB && ' + CONDA + 'conda activate server_amrfinderplus && amrfinder_update -d /databases/AmrfinderplusDB'}},
    {'key': 'checkm2', 'title': 'CheckM2 DIAMOND database', 'tools': ['checkm2', 'basalt'], 'size': '3 GB',
     'markers_all': ['Checkm2DB/**/*.dmnd'],
     'install': {'kind': 'shell', 'command': 'mkdir -p /databases/Checkm2DB && ' + CONDA + 'conda activate server_checkm2 && checkm2 database --download --path /databases/Checkm2DB'}},
    {'key': 'mobsuite', 'title': 'MOB-suite plasmid reference database', 'tools': ['mobsuite'], 'size': '0.5 GB',
     'markers_all': ['MobsuiteDB/ncbi_plasmid_full_seqs.fas'],
     'install': {'kind': 'shell', 'command': 'mkdir -p /databases/MobsuiteDB && ' + CONDA + 'conda activate server_mobsuite && mob_init -d /databases/MobsuiteDB'}},
    {'key': 'kraken2', 'title': 'Kraken2 index', 'tools': ['kraken2'], 'size': '8 GB (capped indexes)',
     'markers_all': ['Kraken2DB/hash.k2d'],
     'install': {'kind': 'host-script', 'script': 'manage_kraken2_db.sh'},
     'note': 'Kraken2 loads the whole index into RAM: use a memory-capped prebuilt index (Standard-8, PlusPF-8), not the full NCBI index.'},
    {'key': 'genomemining', 'title': 'Genome Mining reference database (built from your own genomes)', 'tools': ['genomemining'], 'size': 'depends on your genomes',
     'markers_any': ['GenomeMiningDB/*/cds_positions.fasta', 'GenomeMining/668_cds_positions.fasta'],
     'install': {'kind': 'manual', 'note': 'In the admin open "Custom databases" -> Add, choose the tool "Genome Mining" and upload protein or genome FASTA files '
                                           '(or a zip of them) of the strains to search in. It is built in the background and then offered on the Genome Mining page.'}},
    # ---- tools with their own folder (tools/<name>/), see tools/DATABASES.md ----
    {'key': 'padloc', 'title': 'PADLOC-DB', 'tools': ['padloc'], 'size': '1 GB',
     'markers_all': ['PadlocDB/hmm', 'PadlocDB/sys'],
     'install': {'kind': 'tool-script', 'script': 'padloc/download_padloc_db.sh', 'target': 'PadlocDB'}},
    {'key': 'defensefinder', 'title': 'DefenseFinder / CasFinder models', 'tools': ['defensefinder'], 'size': '0.35 GB',
     'markers_any': ['DefenseFinderDB/*/*', 'DefenseFinderDB/defense-finder-models'],
     'install': {'kind': 'tool-script', 'script': 'defensefinder/download_defensefinder_db.sh', 'target': 'DefenseFinderDB'}},
    {'key': 'gtotree', 'title': 'GToTree single-copy-gene HMM sets', 'tools': ['gtotree'], 'size': '0.2 GB',
     'markers_all': ['GtotreeDB/hmm-sources-and-info.tsv', 'GtotreeDB/Bacteria.hmm'],
     'install': {'kind': 'tool-script', 'script': 'gtotree/download_gtotree_db.sh', 'target': 'GtotreeDB'}},
    {'key': 'pfam', 'title': 'Pfam-A (pressed), for BiG-SCAPE', 'tools': ['bigscape'], 'size': '4.5 GB',
     'markers_all': ['PfamDB/Pfam-A.hmm', 'PfamDB/Pfam-A.hmm.h3m'],
     'install': {'kind': 'tool-script', 'script': 'bigscape/download_pfam_db.sh', 'target': 'PfamDB', 'env': 'server_panbgc'}},
    {'key': 'mibig', 'title': 'MIBiG 4.0 reference clusters, for BiG-SCAPE', 'tools': ['bigscape'], 'size': '0.5 GB',
     'markers_all': ['BigscapeDB/MIBiG/mibig_antismash_4.0_gbk'], 'optional': True,
     'install': {'kind': 'tool-script', 'script': 'bigscape/download_mibig_db.sh', 'target': 'BigscapeDB'}},
    {'key': 'bigslice', 'title': 'BiG-SLiCE models', 'tools': ['bigslice'], 'size': '1.1 GB',
     'markers_all': ['BigsliceDB/bigslice-models'],
     'install': {'kind': 'tool-script', 'script': 'bigslice/download_bigslice_db.sh', 'target': 'BigsliceDB'}},
    {'key': 'rrefinder', 'title': 'RRE-Finder exploratory-mode databases', 'tools': ['rrefinder'], 'size': '0.45 GB',
     'markers_all': ['RreFinderDB/RRE_v7_3_hhm.ffdata', 'RreFinderDB/RRE_short.fasta'],
     'install': {'kind': 'tool-script', 'script': 'rrefinder/download_rrefinder_db.sh', 'target': 'RreFinderDB'}},
    {'key': 'zol', 'title': 'zol annotation databases, for PanBGC', 'tools': ['panbgc'], 'size': '11 GB',
     'markers_all': ['ZolDB/database_location_paths.txt'],
     'install': {'kind': 'tool-script', 'script': 'panbgc/download_zol_db.sh', 'target': 'ZolDB'}},
    {'key': 'basalt', 'title': 'BASALT trained models', 'tools': ['basalt'], 'size': '1 GB',
     'markers_all': ['BasaltDB/BASALT_WEIGHT'],
     'install': {'kind': 'tool-script', 'script': 'basalt/download_basalt_db.sh', 'target': 'BasaltDB'}},
]

BY_KEY = {entry['key']: entry for entry in DATABASES}


def _matches(databases_dir, pattern):
    return glob.glob(os.path.join(databases_dir, pattern), recursive=True)


def is_installed(entry, databases_dir):
    all_ok = all(_matches(databases_dir, pattern) for pattern in entry.get('markers_all', []))
    any_ok = (not entry.get('markers_any')) or any(_matches(databases_dir, pattern) for pattern in entry['markers_any'])
    return bool(all_ok and any_ok and (entry.get('markers_all') or entry.get('markers_any')))


def status(databases_dir):
    """[(entry, installed)] for every database."""
    return [(entry, is_installed(entry, databases_dir)) for entry in DATABASES]


def entries_for_tool(tool_key):
    return [entry for entry in DATABASES if tool_key in entry['tools']]


def missing_for_tool(tool_key, databases_dir, ignore_optional=True):
    """Required databases of a tool that are not installed."""
    return [entry for entry in entries_for_tool(tool_key)
            if not (ignore_optional and entry.get('optional')) and not is_installed(entry, databases_dir)]


def folder_size(path):
    """Size in bytes of a folder (can take a while on huge databases)."""
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def human_size(num_bytes):
    for unit in ('B', 'kB', 'MB', 'GB', 'TB'):
        if num_bytes < 1000 or unit == 'TB':
            return f'{num_bytes:.0f} {unit}' if unit == 'B' else f'{num_bytes:.1f} {unit}'
        num_bytes /= 1000.0
