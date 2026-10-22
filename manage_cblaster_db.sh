#!/bin/bash
# Downloads MIBiG 4.0 and builds the cblaster database (databases/CblasterDB), also callable as: ./baclab db install cblaster
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "=========================================="
echo "    BacLab cblaster Database Downloader"
echo "=========================================="
echo "Estimated Storage: ~100-200 MB (MIBiG 4.0)"
echo "Estimated Time: ~2-5 minutes"
echo "=========================================="

./baclab dbtools '
set -e
source /opt/conda/etc/profile.d/conda.sh
mkdir -p /databases/CblasterDB && cd /databases/CblasterDB
echo "Downloading MIBiG 4.0 GenBank files..."
baclab-fetch https://dl.secondarymetabolites.org/mibig/mibig_gbk_4.0.tar.gz mibig_gbk_4.0.tar.gz
rm -rf mibig_4.0_gbk && mkdir -p mibig_4.0_gbk
tar --no-same-owner -xzf mibig_gbk_4.0.tar.gz -C mibig_4.0_gbk --strip-components=1
rm mibig_gbk_4.0.tar.gz
echo "Building the cblaster sqlite and diamond databases for MIBiG 4.0..."
conda activate server_cblaster
cblaster config --email "${ADMIN_EMAIL:-admin@example.com}"
cblaster makedb mibig_4.0_gbk/*.gbk -n mibig_4.0 -f
python - <<PY
import json, os
path = "/databases/CblasterDB/database_options.json"
options = {"database_options": []}
if os.path.exists(path):
    try:
        options = json.load(open(path))
    except ValueError:
        pass
entries = options.setdefault("database_options", [])
entry = next((e for e in entries if e.get("value") == "mibig_4.0"), None)
if entry is None:
    entry = {"value": "mibig_4.0", "show_warning": False}
    entries.append(entry)
entry.update(label="MIBiG 4.0", mode="local")
json.dump(options, open(path, "w"), indent=4)
PY
'
echo "Done! MIBiG 4.0 database for cblaster is ready."
