#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
DB_DIR="$PROJECT_DIR/databases/Kraken2DB"

echo "=========================================="
echo "     BacLab Kraken2 Database Downloader"
echo "=========================================="
echo "IMPORTANT: Kraken2 loads its whole database into RAM. On a 64GB-RAM"
echo "deployment, use one of the memory-capped prebuilt indexes (NOT the full"
echo "NCBI nt/nr index, which is 100GB+):"
echo "  - Standard-8  (~8GB)  - general bacteria/archaea/virus/human, capped"
echo "  - PlusPF-8    (~8GB)  - Standard-8 + protozoa/fungi/plasmid, capped"
echo ""
echo "Browse current builds and copy a .tar.gz download link from:"
echo "  https://benlangmead.github.io/aws-indexes/k2"
echo "=========================================="

read -p "Paste the .tar.gz URL for the index you want to install: " KRAKEN2_INDEX_URL

if [ -z "$KRAKEN2_INDEX_URL" ]; then
    echo "No URL provided. Aborting."
    exit 1
fi

mkdir -p "$DB_DIR"
cd "$DB_DIR"

echo "Downloading Kraken2 index..."
curl -L -o kraken2_index.tar.gz "$KRAKEN2_INDEX_URL"

echo "Extracting into databases/Kraken2DB..."
tar -xvzf kraken2_index.tar.gz
rm kraken2_index.tar.gz

echo "Kraken2 database installed successfully."
