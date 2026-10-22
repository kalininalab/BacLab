import os
from ete3 import NCBITaxa
import sys
import subprocess

if __name__ == "__main__":

    input_query = sys.argv[1]
    output_dir = sys.argv[2]
    database_dir = sys.argv[3]
    ncbi_tax_db_dir = sys.argv[4]

    blast_script = ["blastn", "-query", input_query, "-db", database_dir, "-out", f"{output_dir}/16s_results_raw.tsv", "-outfmt", "6 qseqid sseqid pident length evalue bitscore staxids", "-max_target_seqs", "5"]

    subprocess.run(blast_script)

    data = {}
    with open(f'{output_dir}/16s_results_raw.tsv', 'r') as infile:
        for line in infile:
            parts = line.strip().split('\t')
            if len(parts) >= 3:
                key = parts[0]
                try:
                    value = float(parts[2])
                    if key not in data or value > float(data[key][2]):
                        data[key] = parts
                except ValueError:
                    value = parts[2]
                    if key not in data:
                        data[key] = parts
    # Write the best results
    with open(f'{output_dir}/16s_results_best.tsv', 'w') as outfile:
        for row in data.values():
            outfile.write('\t'.join(row) + '\n')

    with open(f"{output_dir}/16s_results_best.tsv") as infile:
        with open(f"{output_dir}/16s_taxonomy_results.tsv", 'w') as outfile:
            lines = infile.readlines()
            outfile.write("Strain\tDomain\tPhylum\tClass\tOrder\tFamily\tGenus\tSpecies\n")
            for line in lines:
                splitted = line.strip().split("\t")
                if "|" in splitted[0]:
                    name_of_strain = splitted[0].split("|")[1].split(".")[0]
                else:
                    name_of_strain = splitted[0]
                # a database sequence can belong to several taxa ("41;83460;394097"): the first one names the hit
                taxid_field = splitted[6].split(';')[0].strip() if len(splitted) > 6 else ''
                if not taxid_field.isdigit():
                    outfile.write(f"{name_of_strain}\tUnclassified\tNA\tNA\tNA\tNA\tNA\tNA\n")
                    continue
                taxid = int(taxid_field)

                # Update taxonomy db command = python > from ete3 import NCBITaxa > NCBITaxa(dbfile="/databases/NCBI_Taxa/taxa.sqlite").update_taxonomy_database()
                ncbi = NCBITaxa(dbfile = f"{ncbi_tax_db_dir}/taxa.sqlite", update=False)

                lineage = ncbi.get_lineage(taxid)
                ranks = ncbi.get_rank(lineage)
                names = ncbi.get_taxid_translator(lineage)

                wanted = {"phylum": None, "domain":None, "class":None, "order":None, "family": None, "genus": None, "species": None}
                for tid in lineage:
                    rank = {'superkingdom': 'domain'}.get(ranks[tid], ranks[tid])
                    if rank in wanted:
                        wanted[rank] = names[tid]

                outfile.write(f"{name_of_strain}\t{wanted['domain']}\t{wanted['phylum']}\t{wanted['class']}\t{wanted['order']}\t{wanted['family']}\t{wanted['genus']}\t{wanted['species']}\n")

    os.remove(f'{output_dir}/16s_results_raw.tsv')
    os.remove(f'{output_dir}/16s_results_best.tsv')