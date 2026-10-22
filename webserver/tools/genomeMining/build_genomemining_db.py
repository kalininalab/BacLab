import os
import sys
import subprocess
import shutil
import re
from Bio import SeqIO

def standardize_contig_name(line):
    pattern = re.compile(r"contig_?(\d+)", re.IGNORECASE)
    match = pattern.search(line)
    if match:
        contig_number = match.group(1)
        return f"contig_{contig_number}"
    return line

def run_prokka_and_antismash(fasta_dir, db_dir, cores=4):
    prokka_out = os.path.join(db_dir, "prokka_output")
    antismash_out = os.path.join(db_dir, "antismash_output")
    os.makedirs(prokka_out, exist_ok=True)
    os.makedirs(antismash_out, exist_ok=True)

    fasta_files = [f for f in os.listdir(fasta_dir) if f.endswith(('.fasta', '.fa', '.fna', '.faa')) and not f.startswith('._')]
    
    clean_dir = os.path.join(db_dir, "clean_fasta")
    os.makedirs(clean_dir, exist_ok=True)

    for fasta_file in fasta_files:
        strain_name = os.path.splitext(fasta_file)[0]
        # Prokka/GenBank files cannot carry contig names longer than 20 characters (the LOCUS line breaks, Biopython then refuses the file),
        # and the later steps expect "contig_<number>" names anyway: work on a copy with sequential names.
        input_fasta = os.path.join(clean_dir, f"{strain_name}.fasta")
        with open(os.path.join(fasta_dir, fasta_file)) as source, open(input_fasta, "w") as target:
            contig_number = 0
            for line in source:
                if line.startswith(">"):
                    contig_number += 1
                    target.write(f">contig_{contig_number}\n")
                else:
                    target.write(line)

        # 1. Run Prokka
        prokka_strain_dir = os.path.join(prokka_out, strain_name)
        if not os.path.exists(prokka_strain_dir):
            cmd_prokka = f"source /opt/conda/etc/profile.d/conda.sh && conda activate server_prokka && prokka --outdir '{prokka_strain_dir}' --prefix '{strain_name}' '{input_fasta}' --force --cpus {cores}"
            print(f"Running Prokka for {strain_name}...")
            subprocess.run(cmd_prokka, shell=True, executable="/bin/bash", check=True)
        
        # 2. Run antiSMASH
        antismash_strain_dir = os.path.join(antismash_out, strain_name)
        if not os.path.exists(antismash_strain_dir):
            cmd_antismash = f"source /opt/conda/etc/profile.d/conda.sh && conda activate server_antismash && export OMPI_MCA_plm_rsh_agent=sh && antismash --databases /databases/AntismashDB --output-dir '{antismash_strain_dir}' --genefinding-tool prodigal --cpus {cores} '{input_fasta}'"
            print(f"Running antiSMASH for {strain_name}...")
            subprocess.run(cmd_antismash, shell=True, executable="/bin/bash", check=True)

def extract_prokka_info(db_dir):
    prokka_out = os.path.join(db_dir, "prokka_output")
    prokka_info_dir = os.path.join(db_dir, "prokka_info")
    os.makedirs(prokka_info_dir, exist_ok=True)

    cds_fasta_path = os.path.join(db_dir, "cds_positions.fasta")
    
    with open(cds_fasta_path, "w") as cds_outfile:
        if os.path.exists(prokka_out):
            for strain_name in os.listdir(prokka_out):
                strain_dir = os.path.join(prokka_out, strain_name)
                gbk_file = os.path.join(strain_dir, f"{strain_name}.gbk")
                
                if os.path.exists(gbk_file):
                    # Write prokka info CSV
                    with open(os.path.join(prokka_info_dir, f"{strain_name}.csv"), "w") as csv_outfile:
                        for record in SeqIO.parse(gbk_file, "genbank"):
                            contig = record.id
                            pattern = re.compile(r"contig_?(\d+)", re.IGNORECASE)
                            match = pattern.search(contig)
                            if match:
                                contig_number = match.group(1)
                                standardized_name = f"contig_{contig_number}"
                            else:
                                standardized_name = contig
                                
                            for feature in record.features:
                                if feature.type == "CDS":
                                    qualifiers = feature.qualifiers
                                    locus_tag = qualifiers.get('locus_tag', ["NA"])[0]
                                    start = int(feature.location.start)
                                    end = int(feature.location.end)
                                    product = qualifiers.get("product", ["NA"])[0]
                                    
                                    csv_outfile.write(f"{locus_tag},{standardized_name},{start},{end},{product}\n")
                                    
                                    # Extract CDS for CDS_POSITIONS_FASTA
                                    protein_seq = qualifiers.get("translation", ["NA"])[0]
                                    if protein_seq != "NA":
                                        contig_part = standardized_name.split('_')[1] if '_' in standardized_name else standardized_name
                                        cds_outfile.write(f">{strain_name}:{contig_part}:{locus_tag}:{start}:{end}\n{protein_seq}\n")

def extract_antismash_info(db_dir):
    antismash_out = os.path.join(db_dir, "antismash_output")
    bgc_info_dir = os.path.join(db_dir, "bgc_info")
    bgc_info_core_dir = os.path.join(db_dir, "bgc_info_core")
    bgc_info_core_biosynthetic_dir = os.path.join(db_dir, "bgc_info_core_biosynthetic")
    
    os.makedirs(bgc_info_dir, exist_ok=True)
    os.makedirs(bgc_info_core_dir, exist_ok=True)
    os.makedirs(bgc_info_core_biosynthetic_dir, exist_ok=True)

    if os.path.exists(antismash_out):
        for strain_name in os.listdir(antismash_out):
            strain_dir = os.path.join(antismash_out, strain_name)
            
            output_set_core = set()
            output_set_biosynthetic = set()
            
            with open(os.path.join(bgc_info_dir, f"{strain_name}.csv"), "w") as bgc_csv, \
                 open(os.path.join(bgc_info_core_dir, f"{strain_name}.csv"), "w") as core_csv, \
                 open(os.path.join(bgc_info_core_biosynthetic_dir, f"{strain_name}.csv"), "w") as biosynthetic_csv:
                
                if os.path.isdir(strain_dir):
                    for file in os.listdir(strain_dir):
                        if file.endswith(".gbk") and "region" in file:
                            region_file_path = os.path.join(strain_dir, file)
                            bgc_name = file[:-4]
                            standardized_bgc_name = standardize_contig_name(bgc_name)
                            
                            orig_start = 0
                            orig_end = 0
                            with open(region_file_path, 'r') as reg_file:
                                for line in reg_file:
                                    if "Orig. start" in line:
                                        try:
                                            orig_start = int(line.split("::")[1].strip())
                                        except: pass
                                    if "Orig. end" in line:
                                        try:
                                            orig_end = int(line.split("::")[1].strip())
                                        except: pass
                                    if orig_start != 0 and orig_end != 0:
                                        break
                            
                            # Write bgc_info
                            bgc_csv.write(f"{standardized_bgc_name},{orig_start},{orig_end}\n")
                            
                            # Parse genbank for core and biosynthetic
                            for record in SeqIO.parse(region_file_path, "genbank"):
                                for feature in record.features:
                                    if feature.type == "proto_core":
                                        start_pos = int(feature.location.start) + orig_start + 1
                                        end_pos = int(feature.location.end) + orig_start
                                        output_set_core.add(f"{standardized_bgc_name},{start_pos},{end_pos},{file}")
                                        
                                    elif feature.type == "CDS":
                                        qualifiers = feature.qualifiers
                                        if "gene_functions" in qualifiers:
                                            if qualifiers["gene_functions"][0].startswith("biosynthetic (rule-based-clusters)"):
                                                start_pos = int(feature.location.start) + orig_start + 1
                                                end_pos = int(feature.location.end) + orig_start
                                                output_set_biosynthetic.add(f"{standardized_bgc_name},{start_pos},{end_pos},{file}")
                                                
                for elem in output_set_core:
                    core_csv.write(f"{elem}\n")
                for elem in output_set_biosynthetic:
                    biosynthetic_csv.write(f"{elem}\n")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python build_genomemining_db.py <fasta_dir> <db_dir>")
        sys.exit(1)
        
    fasta_dir = sys.argv[1]
    db_dir = sys.argv[2]
    
    print("Running Prokka and antiSMASH...")
    run_prokka_and_antismash(fasta_dir, db_dir, cores=8)
    
    print("Extracting Prokka info and generating CDS FASTA...")
    extract_prokka_info(db_dir)
    
    print("Extracting antiSMASH info...")
    extract_antismash_info(db_dir)
    
    print("Genome Mining database build complete.")
