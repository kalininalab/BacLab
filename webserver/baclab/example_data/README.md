# Example data

Real sequences, so that "Load Example Data" / "View Example Results" / `./baclab selftest --run` show what a tool does on data it was made for.
Files a tool needs only for itself are in its folder: `webserver/tools/<name>/example_data/`.

| File | What it is | Used by |
|---|---|---|
| `klebsiella_pneumoniae_HS11286.fna` | *K. pneumoniae* HS11286, complete genome (chromosome + 6 plasmids; KPC-2 carbapenemase, ST11); NCBI GCF_000240185.1 | AMRFinderPlus, Abricate, PlasmidFinder, MOB-suite, CheckM2, Kraken2, GToTree, ANI/FastAAI |
| `klebsiella_pneumoniae_NTUH_K2044.fna` | *K. pneumoniae* NTUH-K2044, hypervirulent capsule type K1, ST23 (chromosome + plasmid pK2044); NC_012731.1, NC_006625.1 | MLST, Genome screen, Snippy (variants against the *K. pneumoniae* RefSeq reference, which differs from it in thousands of positions) |
| `bacillus_subtilis_168.fna` | *B. subtilis* 168, complete genome (surfactin, bacillaene, subtilosin ... clusters); NC_000964.3 | GECCO |
| `chlamydia_trachomatis_D_UW3.fna` | *C. trachomatis* D/UW-3/CX, complete genome (1 Mb); NC_000117.1 | Annotation pipeline |
| `quast_example.fasta`, `ani_example/` | draft assemblies (502 contigs) and a *E. coli* K-12 genome | QUAST, CheckM, ANI, FastAAI |
| `phylogeny_example.fasta` (also the Taxonomy Finder example, in 16S mode) | 16S rRNA genes of 12 type strains (RefSeq `NR_` records: *E. coli*, *K. pneumoniae*, *P. aeruginosa*, *B. subtilis*, *S. aureus*, *S. coelicolor*, *M. xanthus*, *Allostigmatella aurantiaca*, *C. coralloides*, *S. cellulosum*, *C. trachomatis*, *V. cholerae*) | Phylogeny, Taxonomy Finder |
| `blast_example.fasta`, `cblaster_example.fasta` | a 16S query for BLAST, abyssomicin cluster proteins (AEK75490 ...) | BLAST, cblaster |
| `ecoli_1K_1.fq.gz`, `ecoli_1K_2.fq.gz` | the SPAdes test reads (*E. coli*, paired) | fastp, SPAdes |
| `multiqc_example.zip` | a real `fastp.json` (the reads above) and two QUAST `report.tsv` (*C. trachomatis* D/UW-3, the draft assembly) | MultiQC |
| `tools/panaroo/example_data/*.gff` | Prokka annotations of four *C. trachomatis* genomes (D/UW-3, L2/434, L2b/UCH-1, A/HAR-13; NC_000117.1, NC_010287.1, NC_010280.1, NC_007429.1) | Panaroo |
| `tools/gubbins/example_data/chlamydia_trachomatis_core.aln` | `snippy-core` alignment of the same four genomes (1 Mb, a species with well-documented recombination) | Gubbins |
| `tools/genomeMining/example_data/genomemining_example.fasta` | the surfactin phosphopantetheinyl transferase Sfp (UniProt P39135) | Genome Mining (needs the database `bacillus_example`, built in the admin from `tools/genomeMining/example_data/example_genomes.zip`: *B. subtilis* 168 and *B. velezensis* FZB42, about half an hour) |
| `bacillus_antismash_regions/` | 27 antiSMASH regions (`--minimal` run) of *B. subtilis* 168 and *B. velezensis* FZB42 | BiG-SCAPE, BiG-SLiCE |
| `tools/genovi/example_data/klebsiella_pneumoniae_pKPHS2.gb` | the 111 kb plasmid pKPHS2 of HS11286 (GenBank); NC_016846.1 | GenoVi |

Every tool has example data and so a **View Example Results** button, except BASALT (metagenome binning; it needs 128 GB RAM and is off by default). The button runs the example once (`<tool>-EXAMPLE`) and then just shows its results.

Several tool names are symbolic links to the genome above (`abricate_example.fasta` -> `klebsiella_pneumoniae_HS11286.fna`, ...): one real genome serves
many tools, so the repository stays small.
