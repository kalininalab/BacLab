#!/bin/bash

# Installs BASALT (copies its programs into the server_basalt env), pinned to release V1.2.2's
# commit; the models are NOT downloaded here, they come from the shared /databases/BasaltDB.
# Its install.sh only copies the programs into the env, so the checkout is deleted afterwards.
set -e

eval "$(conda shell.bash hook)"
conda activate server_basalt
cd
git clone --branch V1.2.2 --depth 1 https://github.com/PKU-EMBL/BASALT.git basalt
cd basalt
bash install.sh
cd
rm -rf basalt
