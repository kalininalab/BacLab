import os
import csv
import sys

def collect_antismash_gbks(blast_csv, db_path, output_dir):
    db_path = os.path.abspath(db_path)
    output_dir = os.path.abspath(output_dir)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    found_clusters = set()

    with open(blast_csv, 'r') as f:
        reader = csv.reader(f, delimiter='\t')

        for row in reader:
            if not row or len(row) < 2:
                continue

            # Subject ID from BLAST column 2
            hit_id = row[1].split(";")[0]
            strain_name = hit_id.split(".")[0].split("_")[-1]
            hit_folder = os.path.join(db_path, strain_name)
            source_path = os.path.join(hit_folder, f"{hit_id}.gbk")

            dest_path = os.path.join(output_dir, f"{hit_id}.gbk")

            if hit_id not in found_clusters:
                try:
                    os.symlink(source_path, dest_path)
                    found_clusters.add(hit_id)
                except FileExistsError:
                    pass
                except OSError as e:
                    print(f"Error linking {hit_id}: {e}")

    print(f"\nCreated {len(found_clusters)} symlinks in '{output_dir}'")
    print(f"Run: clinker {output_dir} -p plot.html")

if __name__ == "__main__":
    blast_output_path = sys.argv[1]
    output_folder_path = sys.argv[2]
    antismash_db = sys.argv[3]

    collect_antismash_gbks(blast_output_path, antismash_db, output_folder_path)


