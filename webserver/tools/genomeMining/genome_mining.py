import os
import subprocess
from Bio import SeqIO
import sys
import pandas as pd
import csv
import requests
import time

INPUT_PATH = sys.argv[1]

OUTPUT_PATH = sys.argv[2]

log_file_path = os.path.join(OUTPUT_PATH, "genome_mining.log")
log_file = open(log_file_path, "w", buffering=1)
os.dup2(log_file.fileno(), 1)
os.dup2(log_file.fileno(), 2)
sys.stdout = log_file
sys.stderr = log_file

CDS_POSITIONS_FASTA = sys.argv[3]

BGC_INFO_CORE_PATH = sys.argv[4]

BGC_INFO_PATH = sys.argv[5]

PROKKA_INFO_PATH = sys.argv[6]

HOMOLOG_SEARCH = sys.argv[7]

try:
    with open("/app/tools/admin_email.txt", "r") as f:
        EMAIL = f.read().strip()
except Exception:
    EMAIL = "admin@example.com"

CPU = sys.argv[8]

def search_interpro_family(sequence, email):
    base_url = "https://www.ebi.ac.uk/Tools/services/rest/iprscan5"
    
    submit_payload = {
        "email": email,
        "title": "Python_API_Search",
        "sequence": sequence
    }
    
    submit_response = requests.post(f"{base_url}/run", data=submit_payload)
    if not submit_response.ok:
        print(f"Error submitting job: {submit_response.text}")
        sys.exit(1)
        
    job_id = submit_response.text
    
    status_url = f"{base_url}/status/{job_id}"
    
    while True:
        status_response = requests.get(status_url)
        status = status_response.text
        
        if status == "FINISHED":
            print("\nJob complete! Retrieving results...")
            break
        elif status in ["ERROR", "FAILURE", "NOT_FOUND"]:
            print(f"\nJob failed with status: {status}")
            sys.exit(1)
            
        time.sleep(30) 
        
    result_url = f"{base_url}/result/{job_id}/tsv"
    result_response = requests.get(result_url)
    
    if not result_response.ok:
        print("Failed to download results.")
        sys.exit(1)
        
    interpro_families = set()
    
    for line in result_response.text.strip().split("\n"):
        columns = line.split("\t")
        if len(columns) > 12:
            ipr_id = columns[11]
            ipr_desc = columns[12]
            
            if ipr_id.startswith("IPR"):
                interpro_families.add((ipr_id, ipr_desc))
                
    return interpro_families

def get_bgc_distance_and_direction(gene_start, gene_end, bgc_start, bgc_end):
    """
    Calculates distance and determines if the BGC is upstream, downstream, or overlapping.
    Assumes standard 5' to 3' coordinate progression.
    """
    if bgc_end < gene_start:
        # BGC is strictly before the gene (Upstream)
        distance = gene_start - bgc_end
        return distance, "upstream"
    
    elif bgc_start > gene_end:
        # BGC is strictly after the gene (Downstream)
        distance = bgc_start - gene_end
        return distance, "downstream"
    
    else:
        # The coordinates overlap
        return 0, "overlapping"

def extract_neighborhood(filepath, target_gene, target_gene_contig_id, distance_bp):
    target_start = None
    target_end = None
    all_genes = []

    # 1. Read the file into memory and find the target gene's coordinates
    with open(filepath, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue # Skip empty or malformed lines
            
            gene_id = row[0]
            contig_id = row[1]
            start = int(row[2])
            end = int(row[3])
            
            # Store the data so we only read the file from the disk once
            all_genes.append({
                'id': gene_id,
                'contig_id': contig_id,
                'start': start,
                'end': end,
                'raw_row': row
            })
            
            # Capture the target coordinates when we hit them
            if gene_id == target_gene:
                target_start = start
                target_end = end

    if target_start is None:
        print(f"Error: {target_gene} not found.")
        return []

    # 2. Define your coordinate window
    window_start = target_start - distance_bp
    window_end = target_end + distance_bp
    
    # 3. Extract everything that overlaps the window
    neighborhood = []
    for gene in all_genes:
        if gene['end'] >= window_start and gene['start'] <= window_end and gene[f'contig_id'] == f"contig_{target_gene_contig_id}":
            # Rejoin the row as a comma-separated string for easy viewing/saving
            neighborhood.append(",".join(gene['raw_row']))
            
    return neighborhood

if __name__ == "__main__":

    input_fasta = f""

    for file in os.listdir(INPUT_PATH):
        if file.endswith(".fasta"):
            input_fasta_file = file
        
    with open(f"{INPUT_PATH}/{input_fasta_file}") as infile:
        lines = infile.readlines()
        input_fasta = "\n".join(lines) 

    if HOMOLOG_SEARCH == "yes":

        results = search_interpro_family(input_fasta, EMAIL)

        family_id = ""
        
        if results:
            for ipr_id, desc in results:
                if family_id == "":
                    family_id = ipr_id
        else:
            sys.exit(1)

        download_cmd = [
            "curl", "-L",
            f"https://rest.uniprot.org/uniprotkb/stream?query=xref:interpro-{family_id}&format=fasta",
            "-o", f"{OUTPUT_PATH}/{family_id}_proteins.fasta"
        ]

        ret = subprocess.run(download_cmd).returncode
        if ret != 0:
            print(f"Error: Failed to download InterPro family fasta with command: {' '.join(download_cmd)}", file=sys.stderr)
            sys.exit(10)

        # check if downloaded file is fasta
        with open(f"{OUTPUT_PATH}/{family_id}_proteins.fasta") as protein_family_fasta_file:
            protein_family_fasta_file_lines = protein_family_fasta_file.readlines()
            if len(protein_family_fasta_file_lines) > 1:
                if protein_family_fasta_file_lines[0].startswith('>') and not protein_family_fasta_file_lines[1].startswith('>'):
                    pass
                else:
                    print("Downloaded protein fasta file is not fasta format")
                    sys.exit(1)
            else:
                print("Downloaded protein fasta file is empty")
                sys.exit(1)

        phmmer_cmd = [
            "phmmer", "--cpu", str(CPU), "--tblout",
            f"{OUTPUT_PATH}/output_pfam.tbl",
            f"{INPUT_PATH}/{input_fasta_file}",
            f"{OUTPUT_PATH}/{family_id}_proteins.fasta"
        ]

        ret = subprocess.run(phmmer_cmd).returncode
        if ret != 0:
            print(f"Error: phmmer command failed: {' '.join(phmmer_cmd)}", file=sys.stderr)
            sys.exit(11)

        fasta_file = f"{OUTPUT_PATH}/{family_id}_proteins.fasta"
        hmm_output_table = f"{OUTPUT_PATH}/output_pfam.tbl"
        output_file_name = f"{OUTPUT_PATH}/SELECTED_PROTEINS.fasta"
        pfam_output_file = f"{OUTPUT_PATH}/SELECTED_PROTEINS_PFAM.txt"

        user_seq = ""

        user_fasta_id = ""

        for record in SeqIO.parse(f"{INPUT_PATH}/{input_fasta_file}", "fasta"):
            user_fasta_id = record.id.strip()
            user_seq = record.seq.strip()
            break

        fasta_seqs = {}

        already_added = []

        # Use SeqIO.parse to iterate through records
        for record in SeqIO.parse(fasta_file, "fasta"):
            fasta_seqs[record.id] = record.seq

        limit = 0.0

        homolog_amount_limit = 10
        isolated_homologs = 0

        """
        check uniqueness of seqs and add user seq on top of the generated file: SELECTED_PROTEINS.fasta
        """

        with open(hmm_output_table, "r") as hmm_file:
            with open(f"{output_file_name}", "w") as outfile:
                outfile.write(f">{user_fasta_id}\n{user_seq}\n")
                already_added.append(user_seq)
                lines = hmm_file.readlines()

                highest_hmm_score = -99999

                with open(pfam_output_file, "w") as pfam_of:
                    pfam_of_header = False
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("#"):
                            if not pfam_of_header:
                                pfam_of.write(f"{line}\n")
                            continue
                        
                        splitted2 = line.split()

                        hmm_score = float(splitted2[5])
                        if highest_hmm_score == -99999:
                            highest_hmm_score = hmm_score
                            limit = float(highest_hmm_score/2)

                        if homolog_amount_limit >= isolated_homologs:
                            if hmm_score >= limit:
                                pfam_of.write(f"{line}\n")
                                pfam_of_header = True
                                if fasta_seqs[splitted2[0]] not in already_added:
                                    outfile.write(f">{splitted2[0]}\n{fasta_seqs[splitted2[0]]}\n")
                                    already_added.append(fasta_seqs[splitted2[0]])
                                isolated_homologs += 1

        mafft_cmd = [
            "mafft", "--thread", str(CPU), "--auto",
            f"{OUTPUT_PATH}/SELECTED_PROTEINS.fasta"
        ]

        with open(f"{OUTPUT_PATH}/SELECTED_PROTEINS.aln", "w") as mafft_out:
            ret = subprocess.run(mafft_cmd, stdout=mafft_out).returncode
        if ret != 0:
            print(f"Error: mafft alignment command failed: {' '.join(mafft_cmd)}", file=sys.stderr)
            sys.exit(12)
    
    if HOMOLOG_SEARCH == "no" and input_fasta.count(">") > 1:
        mafft_cmd = [
            "mafft", "--thread", str(CPU), "--auto",
            f"{INPUT_PATH}/{input_fasta_file}"
        ]
        with open(f"{OUTPUT_PATH}/SELECTED_PROTEINS.aln", "w") as mafft_out:
            ret = subprocess.run(mafft_cmd, stdout=mafft_out).returncode
        if ret != 0:
            print(f"Error: mafft alignment command failed: {' '.join(mafft_cmd)}", file=sys.stderr)
            sys.exit(12)
    
    if os.path.exists(f"{OUTPUT_PATH}/SELECTED_PROTEINS.aln"):

        hmmbuild_cmd = [
            "hmmbuild",
            f"{OUTPUT_PATH}/SELECTED_PROTEIN.hmm",
            f"{OUTPUT_PATH}/SELECTED_PROTEINS.aln"
        ]

        ret = subprocess.run(hmmbuild_cmd).returncode
        if ret != 0:
            print(f"Error: hmmbuild command failed: {' '.join(hmmbuild_cmd)}", file=sys.stderr)
            sys.exit(13)

        hmmsearch_cmd = [
            "hmmsearch", "-E", "1e-10", "--cpu", str(CPU),
            "--domtblout", f"{OUTPUT_PATH}/SELECTED_PROTEIN_hmm_out.txt",
            "--tblout", f"{OUTPUT_PATH}/SELECTED_PROTEIN_summary.txt",
            f"{OUTPUT_PATH}/SELECTED_PROTEIN.hmm",
            f"{CDS_POSITIONS_FASTA}"
        ]

        ret = subprocess.run(hmmsearch_cmd).returncode
        if ret != 0:
            print(f"Error: hmmsearch command failed: {' '.join(hmmsearch_cmd)}", file=sys.stderr)
            sys.exit(14)

    if HOMOLOG_SEARCH == "no" and input_fasta.count(">") <= 1:
        phmmer_cmd = [
            "phmmer", "--cpu", str(CPU), "--tblout",
            f"{OUTPUT_PATH}/SELECTED_PROTEIN_summary.txt",
            f"{INPUT_PATH}/{input_fasta_file}",
            f"{CDS_POSITIONS_FASTA}"
        ]

        ret = subprocess.run(phmmer_cmd).returncode
        if ret != 0:
            print(f"Error: phmmer command failed: {' '.join(phmmer_cmd)}", file=sys.stderr)
            sys.exit(11)

    hmmserach_min_limit = 200

    if os.path.exists(f"{OUTPUT_PATH}/SELECTED_PROTEIN_summary.txt"):
        with open(f"{OUTPUT_PATH}/SELECTED_PROTEIN_summary.txt") as infile:
            header_lines_finished = False
            lines = infile.readlines()
            with open(f"{OUTPUT_PATH}/SELECTED_PROTEIN_summary.txt", "w") as ofile:
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("#"):
                        if not header_lines_finished:
                            ofile.write(f"{line}\n")
                    else:
                        header_lines_finished = True
                        splitted2 = line.split()

                        hmm_score = float(splitted2[5])
                        if hmm_score >= hmmserach_min_limit:
                            ofile.write(f"{line}\n")

    hmm_output_table = f"{OUTPUT_PATH}/SELECTED_PROTEIN_summary.txt"
    bgc_info_folder_path = f"{BGC_INFO_CORE_PATH}"
    output_path = f"{OUTPUT_PATH}"

    output_occurences = {}

    with open(hmm_output_table, "r") as hmm_file:
        with open(f"{output_path}/SELECTED_PROTEIN_closest_bgc_results_core_prot.tsv", "w") as outfile:
            # Write an optional header for your output file

            lines = hmm_file.readlines()

            best_hmm_score = -99999
            worst_hmm_score = 999999

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue

                splitted = line.split()[0].split(":")
                strain_id = splitted[0]
                if strain_id in output_occurences.keys():
                    output_occurences[strain_id] += 1
                else:
                    output_occurences[strain_id] = 1
                
                splitted2 = line.split()
                if float(splitted2[5]) > best_hmm_score:
                    best_hmm_score = float(splitted2[5])
                
                if float(splitted2[5]) < worst_hmm_score:
                    worst_hmm_score = float(splitted2[5])
            
            outfile.write(f"strain\tgene_start\tgene_end\thmm_score({best_hmm_score}-{worst_hmm_score})\tup_start_and_end\tup_dist\tup_bgc\tdown_start_and_end\tdown_dist\tdown_bgc\tclosest_distance\tneighboring_gene_products\tstrain_occurence_in_hmm_results\tis_hit_in_bgc\n")

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                
                splitted = line.split()[0].split(":")

                strain_id = splitted[0]
                contig_id = splitted[1]
                locus_id = splitted[2]
                genestart = int(splitted[3])
                geneend = int(splitted[4])

                splitted2 = line.split()
                hmm_score = splitted2[5]

                strain_name = strain_id
                gene_contig_id = "contig_" + contig_id
                gene_name = locus_id
                gene_start = genestart
                gene_end = geneend
                
                csv_path = os.path.join(bgc_info_folder_path, f"{strain_name}.csv")

                # Trackers for our closest BGCs
                closest_overall = None
                closest_upstream = None
                closest_downstream = None

                neighborhood_results = extract_neighborhood(f"{PROKKA_INFO_PATH}/{strain_id}.csv", f"{locus_id}", f"{contig_id}", 1000)    
                neighborhood_results_str = ""
                for elem in neighborhood_results:
                    temp_str = str(elem.split(',')[-1].strip())
                    if 'OS=' in temp_str:
                        temp2_str = temp_str.split('OS=')[0]
                    else:
                        temp2_str = temp_str
                    neighborhood_results_str += temp2_str
                    neighborhood_results_str += ";"
                neighborhood_results_str = neighborhood_results_str[:-1]

                # Add a check to ensure the CSV exists before trying to open it
                if os.path.exists(csv_path):
                    with open(csv_path, "r") as csv_file: # Renamed to csv_file
                        for csv_line in csv_file: 
                            csv_line = csv_line.strip()
                            if not csv_line:
                                continue
                            
                            parts = csv_line.split(",")
                            bgc_contig_id = parts[0].split('_')[1]
                            contig = parts[0]
                            bgc_start = int(parts[1])
                            bgc_end = int(parts[2])
                            region_name = parts[3][:-4]
                            strain_name = strain_name

                            #print(parts)
                            #sys.exit()

                            #print(parts)

                            if gene_contig_id != contig:
                                continue
                                
                            # Calculate distance and direction (removed contig_id argument)
                            distance, direction = get_bgc_distance_and_direction(gene_start, gene_end, bgc_start, bgc_end)
                            
                            bgc_data = {
                                "contig": contig, 
                                "start": bgc_start, 
                                "end": bgc_end, 
                                "distance": distance,
                                "direction": direction,
                                "strain_name":strain_name,
                                "region_name":region_name
                            }

                            # 1. Update Closest Overall
                            if closest_overall is None or distance < closest_overall["distance"]:
                                closest_overall = bgc_data

                            # 2. Update Closest Upstream
                            if direction == "upstream":
                                if closest_upstream is None or distance < closest_upstream["distance"]:
                                    closest_upstream = bgc_data

                            # 3. Update Closest Downstream
                            elif direction == "downstream":
                                if closest_downstream is None or distance < closest_downstream["distance"]:
                                    closest_downstream = bgc_data


                # Extract data safely for printing/writing in case nothing was found
                overall_id = closest_overall["contig"] if closest_overall else "None"
                overall_dist = closest_overall["distance"] if closest_overall else "NA"

                overall_start = closest_overall["start"] if closest_overall else "NA"
                overall_end = closest_overall["end"] if closest_overall else "NA"
                
                up_id = closest_upstream["contig"] if closest_upstream else "None"
                up_dist = closest_upstream["distance"] if closest_upstream else "NA"
                up_bgc = closest_upstream["region_name"] if closest_upstream else "NA"

                up_start = closest_upstream["start"] if closest_upstream else "NA"
                up_end = closest_upstream["end"] if closest_upstream else "NA"
                
                down_id = closest_downstream["contig"] if closest_downstream else "None"
                down_dist = closest_downstream["distance"] if closest_downstream else "NA"

                down_start = closest_downstream["start"] if closest_downstream else "NA"
                down_end = closest_downstream["end"] if closest_downstream else "NA"
                down_bgc = closest_downstream["region_name"] if closest_downstream else "NA"

                if overall_dist == "NA":
                    neighborhood_results_str = ""

                # Keep only valid numeric distances
                valid_dists = [d for d in (up_dist, down_dist) if d != "NA"]
                closest_one = min(valid_dists) if valid_dists else "NA"

                in_bgc = "No"

                if os.path.exists(BGC_INFO_PATH):
                    with open(f"{BGC_INFO_PATH}/{strain_name}.csv") as bgc_positions_file:
                        bgc_positions_file_lines = bgc_positions_file.readlines()
                        for bgc_line in bgc_positions_file_lines:
                            splitted_bgc = bgc_line.split(",")
                            bgc_contig = splitted_bgc[0].strip()
                            bgc_start = int(splitted_bgc[1].strip())
                            bgc_end = int(splitted_bgc[2].strip())
                            if contig == bgc_contig:
                                if bgc_start <= genestart and bgc_end >= geneend:
                                    in_bgc = "Yes"
                                    break

                # Write to output file
                outfile.write(f"{strain_name}\t{gene_start}\t{gene_end}\t{hmm_score}\t{up_start}-{up_end}\t{up_dist}\t{up_bgc}\t{down_start}-{down_end}\t{down_dist}\t{down_bgc}\t{closest_one}\t{neighborhood_results_str}\t{output_occurences[strain_id]}\t{in_bgc}\n")
