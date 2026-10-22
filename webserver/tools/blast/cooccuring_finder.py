import csv
import sys
from collections import defaultdict

if __name__ == "__main__":

    input_file_path = sys.argv[1]

    blast_output_path = sys.argv[2]

    output_file_path = sys.argv[3]

    MIN_PIDENT = float(sys.argv[4])

    MIN_QCOVS = float(sys.argv[5])

    columns = ["qseqid", "sseqid", "pident", "length", "mismatch", "gapopen", "qstart", "qend", "sstart", "send", "evalue", "bitscore", "qcovs"]

    genes_to_check = []

    with open(input_file_path, 'r') as input_fasta:
        lines = input_fasta.readlines()
        for line in lines:
            if line.startswith('>'):
                gene_name = line[1:].strip()
                genes_to_check.append(gene_name)
        
    # Group by sseqid manually
    grouped = defaultdict(list)
    
    with open(blast_output_path, 'r') as f:
        reader = csv.DictReader(f, fieldnames=columns, delimiter='\t')
        for row in reader:
            if ':' in row['sseqid']:
                grouped[row['sseqid'].split(':')[1]].append(row)
            else:
                grouped[row['sseqid']].append(row)

    required_genes = set(genes_to_check)
    required_genes_dict = {gene: 0 for gene in genes_to_check}

    with open(output_file_path, 'w') as output_file:
        output_file.write("Subject_ID\tFound_Genes\tLocations\n")

        sseqid_dict = {}

        for subject_id in grouped:
            temp_required_genes_dict = required_genes_dict.copy()
            for hit in grouped[subject_id]:
                query_gene = hit['qseqid']
                pident = float(hit['pident'])
                qcov = float(hit['qcovs'])
                sseqid = hit['sseqid']
                if pident >= MIN_PIDENT and query_gene in required_genes:
                    if qcov >= MIN_QCOVS:
                        if subject_id not in sseqid_dict:
                            sseqid_dict[subject_id] = [hit['sseqid']]
                        else:
                            sseqid_dict[subject_id].append(hit['sseqid'])
                        temp_required_genes_dict[query_gene] = 1

            how_many_found = 0
            for key in temp_required_genes_dict:
                if temp_required_genes_dict[key] == 1:
                    how_many_found += 1
            if how_many_found >= 2:
                found_genes = [gene for gene, found in temp_required_genes_dict.items() if found == 1]
                output_file.write(f"{subject_id}\t{';'.join(found_genes)}\t{';'.join(sseqid_dict[subject_id])}\n")