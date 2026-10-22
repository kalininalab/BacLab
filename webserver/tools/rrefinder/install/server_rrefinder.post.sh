#!/bin/bash

# Installs RRE-Finder from source (it is not on bioconda) into ~/rrefinder, pinned to a commit.
# Exploratory-mode databases are NOT downloaded here: data/database is a symlink to the shared
# /databases/RreFinderDB folder (see download_rrefinder_db.sh).
set -e

eval "$(conda shell.bash hook)"
conda activate server_rrefinder
cd
git clone https://github.com/Alexamk/RREFinder.git rrefinder
cd rrefinder
git checkout 1be526f1566036c461d24b7149cae1449480be79

rm -rf data/database
ln -s /databases/RreFinderDB data/database

# setup_RRE_exploratory.py also downloads the databases at its end - skip that part, they come from
# the shared folder. The rest (HHsuite env vars + HHPaths.pm patching for addss.pl) is still needed.
sed -i 's/^download_RRE_databases.main()/pass/' setup_RRE_exploratory.py
python setup_RRE_exploratory.py
