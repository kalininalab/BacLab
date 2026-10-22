#!/bin/bash

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
DB_DIR="$PROJECT_DIR/databases"
BLAST_DB_DIR="$DB_DIR/BlastDB"
USER_FASTA_DIR="$DB_DIR/user_specific_blast_db_fasta"
JSON_PATH="$BLAST_DB_DIR/database_options.json"

# Ensure directories exist
mkdir -p "$BLAST_DB_DIR"
mkdir -p "$USER_FASTA_DIR"

# Runs a command in the maintenance container (the app image, with databases/ writable)
BACLAB="$PROJECT_DIR/baclab"
CONTAINER_EXEC() { "$BACLAB" dbtools "$1"; }

# Python inline script to update JSON
update_json() {
    local db_val="$1"
    local db_label="$2"
    local db_type="$3"
    
    python3 -c "
import json, os
json_path = '$JSON_PATH'
options = {'database_options': []}
if os.path.exists(json_path):
    try:
        with open(json_path, 'r') as f:
            options = json.load(f)
    except Exception:
        pass
found = False
for opt in options.get('database_options', []):
    if opt.get('value') == '$db_val':
        opt['label'] = '$db_label'
        opt['db_type'] = '$db_type'
        found = True
        break
if not found:
    if 'database_options' not in options:
        options['database_options'] = []
    options['database_options'].append({'value': '$db_val', 'label': '$db_label', 'db_type': '$db_type'})
with open(json_path, 'w') as f:
    json.dump(options, f, indent=4)
"
}

while true; do
    echo "=========================================="
    echo "    BacLab BLAST Database Manager"
    echo "=========================================="
    echo "1) Download a public BLAST database (nr, swissprot, pdbnt, etc.)"
    echo "2) Create a single custom BLAST database from FASTA files"
    echo "3) Exit"
    echo "=========================================="
    read -p "Select an option [1-3]: " option

    case $option in
    1)
        echo ""
        echo "=== Public BLAST Databases ==="
        echo "Estimated Storage:"
        echo " - swissprot, pdbaa, pdbnt: ~0.5 - 2 GB"
        echo " - nt (Nucleotide): ~150 - 200 GB"
        echo " - nr (Protein): ~350 - 450 GB"
        echo " - all: >600 GB"
        echo "Estimated Time: Varies heavily by network and size (minutes to days)"
        echo "Note: update_blastdb.pl outputs the status of each archive downloaded."
        echo "=============================="
        echo "Available public databases include: nr, nt, swissprot, pdbnt, pdbaa, refseq_protein, refseq_rna, all"
        read -p "Enter the name of the database to download (e.g., swissprot) or 'all' to download standard ones: " pub_db
        
        if [ -z "$pub_db" ]; then
            echo "Database name cannot be empty. Returning to menu."
            continue
        fi
        
        # Function to process public db download and json update
        process_pub_db() {
            local db="$1"
            echo "Downloading $db..."
            CONTAINER_EXEC "source /opt/conda/etc/profile.d/conda.sh && conda activate server_blast && cd /databases/BlastDB && update_blastdb.pl --decompress $db 2> >(grep -v 'Could not set uid/gid' >&2)"
            # Guess type for known public dbs
            local t="nucl"
            if [[ "$db" == "nr" || "$db" == "swissprot" || "$db" == "pdbaa" || "$db" == "refseq_protein" || "$db" == "pataa" || "$db" == "env_nr" ]]; then
                t="prot"
            fi
            update_json "$db" "$db (Public)" "$t"
        }

        if [ "$pub_db" == "all" ]; then
            echo "Downloading all standard public databases into databases/BlastDB..."
            for db in nr nt swissprot pdbnt pdbaa refseq_protein refseq_rna; do
                process_pub_db "$db"
            done
        else
            echo "Downloading $pub_db into databases/BlastDB..."
            process_pub_db "$pub_db"
        fi
        
        echo "Done!"
        ;;
        
    2)
        echo ""
        echo "Checking databases/user_specific_blast_db_fasta/..."
        
        shopt -s nullglob
        fasta_files=("$USER_FASTA_DIR"/*.fasta "$USER_FASTA_DIR"/*.fa "$USER_FASTA_DIR"/*.fna "$USER_FASTA_DIR"/*.faa)
        shopt -u nullglob
        
        while [ ${#fasta_files[@]} -eq 0 ]; do
            echo "The directory is currently empty or has no FASTA files!"
            read -p "Please copy your FASTA files into: $USER_FASTA_DIR and then press Enter to continue..."
            shopt -s nullglob
            fasta_files=("$USER_FASTA_DIR"/*.fasta "$USER_FASTA_DIR"/*.fa "$USER_FASTA_DIR"/*.fna "$USER_FASTA_DIR"/*.faa)
            shopt -u nullglob
        done
        
        echo "Found ${#fasta_files[@]} FASTA file(s) in that directory."
        read -p "Enter the desired name for your combined BLAST Database (e.g., MyCombinedDB): " custom_db_name
        
        if [ -z "$custom_db_name" ]; then
            echo "Database name cannot be empty. Returning to menu."
            continue
        fi
        
        echo "Combining FASTA files into one..."
        combined_fasta="$USER_FASTA_DIR/combined_custom_$custom_db_name.fasta"
        cat "${fasta_files[@]}" > "$combined_fasta"
        
        # Guess DB type based on first sequence line
        seq_line=$(grep -v "^>" "$combined_fasta" | grep -v "^$" | head -n 1)
        if echo "$seq_line" | grep -q -i '[EFILPQU]'; then
            db_type="prot"
        else
            db_type="nucl"
        fi
        
        echo "Detected database type based on sequences: $db_type"
        read -p "Is this correct? (Y/n): " confirm_type
        if [[ "$confirm_type" == "n" || "$confirm_type" == "N" ]]; then
            if [ "$db_type" == "prot" ]; then
                db_type="nucl"
            else
                db_type="prot"
            fi
            echo "Switched to: $db_type"
        fi
        
        # Check if exists
        if ls "$BLAST_DB_DIR/$custom_db_name."* 1> /dev/null 2>&1; then
            read -p "Warning: Database '$custom_db_name' already exists in databases/BlastDB. Overwrite? (y/N): " overwrite
            if [[ "$overwrite" == "y" || "$overwrite" == "Y" ]]; then
                echo "Overwriting existing database..."
            else
                echo "Aborting custom database creation."
                rm -f "$combined_fasta"
                continue
            fi
        fi
        
        echo "Running makeblastdb on combined FASTA..."
        CONTAINER_FASTA_PATH="/databases/user_specific_blast_db_fasta/combined_custom_$custom_db_name.fasta"
        CONTAINER_OUT_PATH="/databases/BlastDB/$custom_db_name"
        
        CONTAINER_EXEC "source /opt/conda/etc/profile.d/conda.sh && conda activate server_blast && makeblastdb -in \"$CONTAINER_FASTA_PATH\" -dbtype \"$db_type\" -out \"$CONTAINER_OUT_PATH\" -title \"$custom_db_name\""
        
        echo "Database $custom_db_name created successfully in databases/BlastDB/"
        
        # Update JSON
        update_json "$custom_db_name" "$custom_db_name (Custom)" "$db_type"
        echo "Updated database_options.json for the Web UI!"
        
        # Cleanup
        rm -f "$combined_fasta"
        ;;
        
    3)
        echo "Exiting."
        exit 0
        ;;
    *)
        echo "Invalid option."
        exit 1
        ;;
    esac
    echo ""
done
