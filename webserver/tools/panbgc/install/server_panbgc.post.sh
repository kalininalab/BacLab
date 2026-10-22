#!/bin/bash

# Installs the PanBGC pipeline scripts (not packaged anywhere) into ~/panbgc, pinned to a commit.
set -e

eval "$(conda shell.bash hook)"
conda activate server_panbgc
cd
git clone https://github.com/ZiemertLab/PanBGC-DB.git panbgc
cd panbgc
git checkout cdb0898d64d47ba183867b292f85f490dcde5baf
