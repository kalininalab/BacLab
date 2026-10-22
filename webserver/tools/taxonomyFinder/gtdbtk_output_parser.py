import os
import sys

if __name__ == "__main__":

    gtdbtk_output_path = sys.argv[1]

    gtdbtk_output_file = os.path.join(gtdbtk_output_path, "gtdbtk.bac120.summary.tsv")

    with open(gtdbtk_output_file, "r") as infile:
        lines = infile.readlines()
    header = lines[0].strip().split("\t")
    strain_name_idx = header.index("user_genome")
    classification_idx = header.index("classification")
    strain_classification = {}
    for line in lines[1:]:
        parts = line.strip().split("\t")
        strain_name = parts[strain_name_idx]
        classification = parts[classification_idx]
        splitted_classification = classification.split(";")
        b_domain = "NA"
        b_phylum = "NA"
        b_class = "NA"
        b_order = "NA"
        b_family = "NA"
        b_genus = "NA"
        b_species = "NA"

        if len(splitted_classification) > 0:
            b_domain = splitted_classification[0].replace("d__", "")
            if b_domain == "":
                b_domain = "NA"

        if len(splitted_classification) > 1:
            b_phylum = splitted_classification[1].replace("p__", "")
            if b_phylum == "":
                b_phylum = "NA"

        if len(splitted_classification) > 2:
            b_class = splitted_classification[2].replace("c__", "")
            if b_class == "":
                b_class = "NA"

        if len(splitted_classification) > 3:
            b_order = splitted_classification[3].replace("o__", "")
            if b_order == "":
                b_order = "NA"

        if len(splitted_classification) > 4:
            b_family = splitted_classification[4].replace("f__", "")
            if b_family == "":
                b_family = "NA"

        if len(splitted_classification) > 5:    
            b_genus = splitted_classification[5].replace("g__", "")
            if b_genus == "":
                b_genus = "NA"

        if len(splitted_classification) > 6:
            b_species = splitted_classification[6].replace("s__", "")
            if b_species == "":
                b_species = "NA"

        strain_classification[strain_name] = (b_domain, b_phylum, b_class, b_order, b_family, b_genus, b_species)
    with open(f"{gtdbtk_output_path}/parsed_taxonomy.tsv", "w") as outfile:
        outfile.write("Strain\tDomain\tPhylum\tClass\tOrder\tFamily\tGenus\tSpecies\n")
        for strain, (b_domain, b_phylum, b_class, b_order, b_family, b_genus, b_species) in strain_classification.items():
            outfile.write(f"{strain}\t{b_domain}\t{b_phylum}\t{b_class}\t{b_order}\t{b_family}\t{b_genus}\t{b_species}\n")