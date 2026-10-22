#!/bin/bash

eval "$(conda shell.bash hook)"
conda activate server_cblaster
email=$(cat /app/tools/admin_email.txt)
cblaster config --email "$email"