"""Which version of a tool is installed, read from its conda environment (no tool is started)."""
import glob
import os
import re
from functools import lru_cache

CONDA_ENVS = '/opt/conda/envs'

# tool key (job type) -> (conda environment, package name)
TOOL_PACKAGES = {
    'abricate': ('server_abricate', 'abricate'), 'amrfinderplus': ('server_amrfinderplus', 'ncbi-amrfinderplus'),
    'annotationPipeline': ('server_bakta', 'bakta'), 'blast': ('server_blast', 'blast'), 'cblaster': ('server_cblaster', 'cblaster'),
    'checkm': ('server_spades', 'checkm-genome'), 'checkm2': ('server_checkm2', 'checkm2'), 'fastaai': ('server_fastaai', 'fastaai'),
    'fastp': ('server_spades', 'fastp'), 'gecco': ('server_gecco', 'gecco'), 'gubbins': ('server_gubbins', 'gubbins'),
    'kraken2': ('server_kraken2', 'kraken2'), 'ani': ('server_ani', 'fastani'), 'mlst': ('server_mlst', 'mlst'),
    'mobsuite': ('server_mobsuite', 'mob_suite'), 'multiqc': ('server_spades', 'multiqc'), 'panaroo': ('server_panaroo', 'panaroo'),
    'plasmidfinder': ('server_plasmidfinder', 'plasmidfinder'), 'quast': ('server_spades', 'quast'), 'snippy': ('server_snippy', 'snippy'),
    'spades': ('server_spades', 'spades'), 'taxonomyfinder': ('server_taxonomy', 'gtdbtk'), 'phylogeny': ('server_phylogeny', 'iqtree'),
    'padloc': ('server_padloc', 'padloc'), 'defensefinder': ('server_defensefinder', 'mdmparis-defense-finder'),
    'gtotree': ('server_gtotree', 'gtotree'), 'genovi': ('server_genovi', 'genovi'), 'bigscape': ('server_bigscape', 'bigscape'),
    'bigslice': ('server_bigslice', 'bigslice'), 'gatorgc': ('server_gatorgc', 'gator-gc'), 'panbgc': ('server_panbgc', 'zol'),
    'basalt': ('server_basalt', 'basalt'),
}


@lru_cache(maxsize=None)
def version_of(tool_key, envs_dir=CONDA_ENVS):
    """The installed version string, or '' when it cannot be found (e.g. outside the containers)."""
    entry = TOOL_PACKAGES.get(tool_key)
    if not entry:
        return ''
    env, package = entry
    base = os.path.join(envs_dir, env)
    # conda packages: conda-meta/<name>-<version>-<build>.json
    for path in sorted(glob.glob(os.path.join(base, 'conda-meta', f'{package}-[0-9]*.json'))):
        match = re.match(rf'^{re.escape(package)}-([0-9][^-]*)-', os.path.basename(path))
        if match:
            return match.group(1)
    # pip packages: site-packages/<name>-<version>.dist-info
    normalised = re.sub(r'[-_.]+', '_', package)
    for path in sorted(glob.glob(os.path.join(base, 'lib', 'python*', 'site-packages', '*.dist-info'))):
        match = re.match(r'^(.+?)-([0-9][^-]*)\.dist-info$', os.path.basename(path))
        if match and re.sub(r'[-_.]+', '_', match.group(1)).lower() == normalised.lower():
            return match.group(2)
    return ''
