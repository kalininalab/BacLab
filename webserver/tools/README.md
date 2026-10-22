# BacLab - Tools and Pipelines Documentation

This directory contains the various bioinformatics tools and pipelines integrated into the microservices platform.

BacLab uses a **unified, monolithic Docker image** that contains all the required conda environments pre-installed. You no longer need to rebuild the Docker image to toggle tools on or off!

The **tools** menu shows one column per category with the enabled tools sorted alphabetically; it is built from the registered tools, so nothing needs to be edited for a new tool.
Administrator documentation: [docs/ADMIN_GUIDE.md](../../docs/ADMIN_GUIDE.md).

## Enabling and Disabling Tools at Runtime
A tool can be switched on or off without rebuilding anything. In order of precedence:

1. an environment variable in `webserver/.envs/.production/.django` (or `.local`), e.g. `ENABLE_TOOL_BLAST=False` - restart with `./baclab restart`;
2. the **Tool switches** in the admin (`/admin/`, section *Tool switches*) - takes effect immediately;
3. the default in `webserver/enabled_tools.csv` (shipped with the code; do not edit it on a server, use 1 or 2).

A tool whose database is not installed stays visible but shows a notice and refuses jobs until `./baclab db install <key>` has been run
(`./baclab db status` lists what is missing; the admin page *System status* shows the same).

---

## Available Pipelines Overview

### 1. Abricate (`abricate`)
**Description:** A pipeline for mass screening of contigs for antimicrobial resistance (AMR) or virulence genes.
**Input Data:** Genome assemblies in FASTA or GenBank format.
**Output:** A tab-separated report detailing found genes, their coverage, and identity.
**How to Edit:** Update the `abricate_script.sh` to change database sources (e.g., NCBI, Resfinder, CARD) or tweak thresholds.

### 2. Annotation Pipeline (`annotationPipeline`)
**Description:** A comprehensive pipeline for annotating genomes and predicting Biosynthetic Gene Clusters (BGCs). It typically integrates tools like Bakta, Prokka, and antiSMASH.
**Input Data:** Raw or assembled genome sequences in FASTA format.
**Output:** Annotated GenBank (.gbk) files, GFF3 files, and antiSMASH BGC region predictions.
**How to Edit:** Modify `bakta_script.sh`, `prokka_script.sh`, or `antismash_script.sh` to change specific command-line arguments (e.g., taxonomy species, translation table). Ensure databases are correctly mounted via the `docker-compose` files.

### 3. BLAST (`blast`)
**Description:** Basic Local Alignment Search Tool pipeline for comparing query sequences against specific databases.
**Input Data:** Protein or Nucleotide query sequences (FASTA) and the target database choice.
**Output:** Alignment results in XML or tabular format.
**How to Edit:** `blast_script.sh` can be altered to support additional parameters.

### 4. cblaster (`cblaster`)
**Description:** A tool for searching co-located genes (e.g., BGCs) using BLAST. It enables rapid discovery of clustered homologous genes.
**Input Data:** Protein sequence queries (FASTA) and target genome assemblies or GenBank files.
**Output:** JSON/binary session files, visualization plots, and tabular summaries of co-localization hits.

### 5. Genome Mining (`genomeMining`)
**Description:** Custom genome mining scripts for specialized extraction and analysis of secondary metabolite pathways.
**Input Data:** Annotated genomes or BGC regions.
**Output:** Extracted sequences, CDS positions, and BigScape clusterings.

### 6. Phylogeny (`phylogeny`)
**Description:** Pipeline for constructing phylogenetic trees from genetic data.
**Input Data:** Multi-FASTA sequences of marker genes or whole genomes.
**Output:** Tree files (e.g., Newick format) and alignment files.

### 7. Taxonomy Finder (`taxonomyFinder`)
**Description:** Pipeline leveraging tools like GTDB-Tk to assign accurate taxonomic classifications to bacterial and archaeal genomes.
**Input Data:** Genome assemblies in FASTA format.
**Output:** Taxonomic lineage assignments and placement data.

### 8. MultiQC (`multiqc`)
**Description:** Aggregates QC logs/reports from other pipelines (fastp, QUAST, CheckM/CheckM2, SPAdes) into a single interactive HTML summary. Uses the `multiqc` binary already bundled in `server_spades`.
**Input Data:** A `.zip`/`.tar.gz` archive of report/log files from previous jobs.
**Output:** `multiqc_report.html`.
**Resource notes:** CPU-only, negligible memory.

### 9. MLST (`mlst`)
**Description:** Sequence-based strain typing against PubMLST schemes.
**Input Data:** Genome assemblies in FASTA format.
**Output:** `mlst_results.tsv` (file, scheme, sequence type, allele calls).
**Resource notes:** BLAST-based, CPU-only, negligible memory.

### 10. AMRFinderPlus (`amrfinderplus`)
**Description:** NCBI's point-mutation-aware AMR/virulence/stress gene detector - complements abricate's presence/absence BLAST approach.
**Input Data:** Genome assemblies in FASTA format; optional organism selection for point-mutation calling.
**Output:** `amrfinderplus_results.tsv`.
**Resource notes:** CPU-only, ~2GB RAM for the reference DB. DB fetched on demand with `./baclab db install amrfinderplus` into `databases/AmrfinderplusDB` (outside the image, so it survives updates).

### 11. CheckM2 (`checkm2`)
**Description:** ML-based (DIAMOND + gradient-boosted trees) genome completeness/contamination estimator - faster than CheckM1, no lineage-placement tree needed. Runs alongside `checkm`, not as a replacement.
**Input Data:** Genome assemblies in FASTA format.
**Output:** `checkm2_results.tsv`.
**Resource notes:** CPU-only, runs comfortably within 64GB RAM. DB fetched on demand with `./baclab db install checkm2` into `/databases/Checkm2DB`. Pinned to `checkm2=1.0.2` with `python<3.9` (see `conda_environments/server_checkm2.yml`) since bioconda's newer `checkm2==1.1.0` requires `python>3.12` and cannot coexist with the older build in one solvable environment; 1.0.2 is also the version whose CLI flags `checkm2_script.sh` targets.

### 12. MOB-suite (`mobsuite`)
**Description:** Plasmid reconstruction, mobility/relaxase typing, and clustering - complements PlasmidFinder's replicon-only typing.
**Input Data:** Genome assemblies in FASTA format.
**Output:** `mobsuite_results.tsv`.
**Resource notes:** BLAST-based, CPU-only, modest memory. DB initialized on demand with `./baclab db install mobsuite` (runs `mob_init` into `databases/MobsuiteDB`).

### 13. GECCO (`gecco`)
**Description:** Machine-learning (CRF) biosynthetic gene cluster detector, complementary to antiSMASH's rule-based HMM approach.
**Input Data:** Genome assemblies in FASTA format.
**Output:** `gecco_results.tsv` (per-cluster predictions).
**Resource notes:** CPU-only (HMMER + a light CRF model), no GPU. First run downloads and caches GECCO's ~1GB HMM model - needs outbound network access at least once.

### 14. Gubbins (`gubbins`)
**Description:** Detects and masks recombinant regions in a bacterial whole-genome alignment before phylogenetic inference - the standard companion step to `snippy`/`phylogeny`.
**Input Data:** A single multi-FASTA whole-genome alignment.
**Output:** A recombination-filtered tree (`*.final_tree.tre`) and a recombination-predictions GFF.
**Resource notes:** CPU-only; memory scales with alignment size but stays well within 64GB for typical bacterial core-genome alignments.

### 15. Kraken2 (`kraken2`)
**Description:** Fast k-mer based taxonomic classification, used as a contamination/species-ID check on an assembly.
**Input Data:** Genome assemblies in FASTA format.
**Output:** `kraken2_results.tsv` (percent, reads covered, reads assigned, rank, taxid, name).
**Resource notes:** CPU-only, but memory equals the size of the loaded database. **Do not use the full NCBI nt database** (100GB+) on a 64GB machine - run `./manage_kraken2_db.sh` (asks for the URL) and paste in a capped-size prebuilt index URL instead (e.g. [Standard-8 or PlusPF-8](https://benlangmead.github.io/aws-indexes/k2), ~8GB); it extracts into `/databases/Kraken2DB`.

### 16. FastANI / ANI (`ani`)
**Description:** Fast, alignment-free whole-genome Average Nucleotide Identity. Runs all-vs-all across every genome in the upload - the standard ~95% ANI threshold is what most modern bacterial species definitions are actually based on.
**Input Data:** 2 or more genome assemblies in FASTA format (all files in the input directory are compared all-vs-all).
**Output:** `ani_results.tsv` (Query, Reference, ANI, Mapped_Fragments, Total_Query_Fragments) + the raw `--matrix` output.
**Resource notes:** CPU-only, negligible memory (MinHash sketches, not alignment).

### 17. FastAAI (`fastaai`)
**Description:** Whole-genome Average Amino Acid Identity, estimated from Jaccard similarity of single-copy-protein tetramer profiles - a genus-level companion to ANI that stays informative well past the point where ANI stops resolving (ANI saturates below ~75-80%; AAI keeps discriminating further out). Runs all-vs-all across every genome in the upload.
**Input Data:** 2 or more genome assemblies in FASTA format.
**Output:** `fastaai_results.tsv` (query, target, avg_jacc_sim, jacc_SD, num_shared_SCPs, poss_shared_SCPs, AAI_estimate).
**Resource notes:** CPU-only (Prodigal gene calling + HMMER domain search under the hood). Pip-installed, not on bioconda - `conda_environments/server_fastaai.yml` pins `pyhmmer==0.8.2`; newer pyhmmer releases return `str` instead of `bytes` from hit/domain accessors, which crashes FastAAI's own (unpatched) exception handler.

### 18. PADLOC (`padloc`) - tool folder
**Description:** Detects anti-phage defence systems. **Input:** 1-20 genome FASTA files. **Output:** one combined table (`padloc_results.csv`) and GFF. **Database:** `PadlocDB` (~1 GB).

### 19. DefenseFinder (`defensefinder`) - tool folder
**Description:** Anti-phage defence systems and CRISPR-Cas (CasFinder models). **Input:** 1-20 genome FASTA files. **Output:** systems and genes tables. **Database:** `DefenseFinderDB` (~350 MB).

### 20. GToTree (`gtotree`) - tool folder
**Description:** Phylogenomic tree from single-copy marker genes. **Input:** 3+ genome FASTA files and a marker gene set. **Output:** tree, genome quality table, marker-gene heatmap. **Database:** `GtotreeDB` (HMM sets, ~200 MB).

### 21. GenoVi (`genovi`) - tool folder
**Description:** Circular genome plots (up to 200 contigs). **Input:** annotated GenBank files. **Output:** SVG/PNG per genome. No database.

### 22. BiG-SCAPE (`bigscape`) - tool folder
**Description:** Groups antiSMASH region GenBank files into gene cluster families, with the interactive BiG-SCAPE viewer. **Input:** 2-1000 `.gbk` files or one zip. **Databases:** `PfamDB` (~4.5 GB); optional MIBiG 4.0 reference clusters (`BigscapeDB`).

### 23. BiG-SLiCE (`bigslice`) - tool folder
**Description:** Fast clustering of antiSMASH regions into gene cluster families. **Input:** 2-200 `.gbk` files. **Database:** `BigsliceDB` (~1.1 GB).

### 24. GATOR-GC (`gatorgc`) - tool folder
**Description:** Targeted, evolution-aware search for a gene cluster in annotated genomes. **Input:** GenBank genomes plus a protein FASTA of the required (and optionally optional) cluster proteins. Has example data. No database.

### 25. RRE-Finder (`rrefinder`) - tool folder
**Description:** RiPP recognition elements in proteins or GenBank files (precision and exploratory modes). **Database:** `RreFinderDB` (~450 MB).

### 26. PanBGC (`panbgc`) - tool folder
**Description:** Pangenome-style analysis of the gene clusters of one gene cluster family: core/accessory/singleton genes, openness. **Input:** 3+ GenBank files. **Database:** `ZolDB` (~11 GB).

### 27. BASALT (`basalt`) - tool folder, **off by default**
**Description:** Metagenome binning from an assembly and paired reads. **Heavy:** its authors recommend 128 GB RAM (the worker needs `WORKER_MEMORY` in `webserver/.env` that large). **Databases:** `BasaltDB` (~1 GB) and the CheckM2 database.

The databases of all tools are listed in [DATABASES.md](DATABASES.md).

---

## Adding a New Tool

There are three ways, from easiest to most flexible.

### A. In the admin, without programming (no rebuild)
Open `/admin/` -> **Custom tools** -> *Add*: give it a name, the file types it accepts, a bash script (it gets `$INPUT_DIR`, `$OUTPUT_DIR`,
`$CORES_PER_JOB`, `$DATABASES_DIR` and a `$PARAM_<NAME>` per option you define), optionally a conda environment (YAML, built from the list
view with *Build the conda environment*, kept on the data volume so it survives updates) and how to show the result (a table, an HTML
report, or just the download). The tool gets its page, menu entry, job queue and results page. Tick *enabled* when the environment is
built. Only give this permission to administrators you trust - the script runs on the server like any other tool.

### B. A tool folder (for tools that belong in the release)
Everything a tool needs lives in `tools/<name>/`; pages, URLs, menus, FAQ, job runner, results and the Docker images are generated from it.

```
tools/new_tool.sh mytool "My Tool" annot      # creates the skeleton below, then edit it
```

| File in `tools/<name>/` | Purpose |
|---|---|
| `tool.py` | **Required.** Defines `tool = Tool(...)`, see `baclab/toolkit/tool.py` for every option |
| `<name>_script.sh` | Runs the tool: `<script> <input dir> <output dir> *args` (args come from `Tool(args=...)`) |
| `install/server_<env>.yml` | Conda environment `server_<env>`, built into the Docker image automatically |
| `install/server_<env>.pre.sh` / `.post.sh` | Optional: sourced before / run after the environment is created (extra installs, configuration) |
| `<name>.html` | Submission page (extends `tool_base.html`) |
| `results_<name>.html` | Only for custom results pages |
| `example_data/` | Optional example files, referenced by `Tool(example=[...])` |
| `download_*_db.sh` | Optional helper that creates the tool's database under `databases/` |

Only `name`, `title` and `category` are required; the defaults suit "run a script on uploaded genomes and show a table". Replaceable
pieces: `form`, `prepare_inputs`, `args`, `outputs`, `run`, `build_job`, `results` (`table_results`, `html_results`, `tabbed_results` or your
own view), `urls`, `databases`. Whitelist anything a user can choose with `choice()`.

For a database: put it under `databases/<Name>/`, add a `download_<name>_db.sh <target>` helper, **add an entry to `baclab/db_catalog.py`**
(how to tell it is installed, how to install it - then `./baclab db install <key>` and the status pages know it) and a row to
[DATABASES.md](DATABASES.md). A tool must never download anything while a job runs.

Test: `python manage.py test baclab.tests.test_toolkit` checks every tool folder against these conventions. Then add a row to
`enabled_tools.csv` and run `./baclab update` (the new conda environment is built; existing environments come from the build cache).

### Tools with their own pages, databases or errors
Every tool - the first-generation ones too (`abricate`, `blast`, `cblaster`, `snippy`, ...) - is a folder. The larger ones use more of the pieces:
`blast`, `cblaster`, `phylogeny` and `genomemining` read `database_options.json`/`strain_options.json` for their page (`page_context=`) and build
the databases administrators add in the admin (`custom_database=`); `cblaster` turns "no hits" and "ValueError" into `JobError` subclasses
(own message and archive name); `annotationPipeline` supplies `build_job` and `run` because it runs Prokka, Bakta and antiSMASH from Python
(`baclab/tools/`: the steps it shares with the processing of in-house strains); `taxonomyfinder` is switched on and off under the key `taxonomy`
(`settings_key=`). `file_only=True` refuses pasted sequences; `requires_databases=False` keeps a tool usable when only some modes need a database;
`exclude=[...]` leaves a tool's working files out of the results.

---

## Citations
Every tool's submission and results page shows a "Please cite" box. Tool folders and admin-added tools carry their own `citation=`
(`webserver/baclab/citations.py` only holds the citation of the platform itself).
