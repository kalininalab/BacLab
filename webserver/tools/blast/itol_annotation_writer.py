import os
import csv
import sys

def itol_annotation_writer(blast_tsv, output_dir):
    output_dir = os.path.abspath(output_dir)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(os.path.join(output_dir, "itol_annotation.txt"), "w") as ofile:
        ofile.write(f"TREE_COLORS\nSEPARATOR SPACE\nDATA\n")
        with open(blast_tsv, 'r') as infile:
            reader = csv.reader(infile, delimiter='\t')

            for row in reader:
                if not row or len(row) < 2:
                    continue

                # Subject ID from BLAST column 2
                hit_id = row[1].split(";")[0]
                strain_name = hit_id.split(".")[0].split("_")[-1]
                ofile.write(f"{strain_name.lower()} branch #ff0000 normal 3\n")
                ofile.write(f"{strain_name.lower()} label #ff0000 normal 1\n")


if __name__ == "__main__":
    blast_tsv_path = sys.argv[1]
    output_folder_path = sys.argv[2]

    itol_annotation_writer(blast_tsv_path, output_folder_path)

