# Databases and models of the tools

Nothing is downloaded while jobs run: in production `/databases` is mounted read-only, and downloads from
Zenodo and similar servers are slow and fail now and then. Whatever a tool needs besides the job's own input lives
in the folders below, filled once with `./baclab db install` (or copied from another machine). The only tools that
use the network while running are those that ask an online service by nature: Snippy (reference genome from NCBI
by TaxID), Genome Mining (EBI InterPro and UniProt) and cblaster in remote mode.

All databases/models live in the `databases/` folder next to `webserver/` (mounted at `/databases`
inside the containers, read-only in production). That folder is not in git. To bring a new
environment up, **copy the folders below** (e.g. with `rsync -a`) instead of downloading again, or install them with
`./baclab db install <key>` (`./baclab db status` shows what is missing; the keys and markers are in `baclab/db_catalog.py`).

| Folder (`databases/…`) | Used by | Size | Created by (run with the tool's conda env active) |
|---|---|---|---|
| `PadlocDB` | PADLOC | ~1 GB | `tools/padloc/download_padloc_db.sh <target>` (`server_padloc`) |
| `DefenseFinderDB` | DefenseFinder | ~350 MB | `tools/defensefinder/download_defensefinder_db.sh <target>` (`server_defensefinder`) |
| `PfamDB` | BiG-SCAPE | ~4.5 GB | `tools/bigscape/download_pfam_db.sh <target>` (needs `hmmpress`, e.g. `server_panbgc`) |
| `BigsliceDB` | BiG-SLiCE | ~1.1 GB | `tools/bigslice/download_bigslice_db.sh <target>` |
| `RreFinderDB` | RRE-Finder (exploratory mode) | ~450 MB | `tools/rrefinder/download_rrefinder_db.sh <target>` (RRE-Finder installed at `~/rrefinder`) |
| `ZolDB` | PanBGC (zol annotation) | ~11 GB | `tools/panbgc/download_zol_db.sh <target>` (`server_panbgc`) |
| `BasaltDB` | BASALT (`BASALT_WEIGHT` models) | ~1 GB | `tools/basalt/download_basalt_db.sh <target>` (`server_basalt`) |
| `Checkm2DB` | BASALT (shared with the CheckM2 tool) | ~3 GB | `databases/Checkm2DB/download_checkm2_db.sh` |
| `GtotreeDB` | GToTree | ~0.2 GB | `tools/gtotree/download_gtotree_db.sh <target>` (`server_gtotree`) |
| `BigscapeDB` | BiG-SCAPE (MIBiG 4.0 option) | ~0.5 GB | `tools/bigscape/download_mibig_db.sh <target>` (`server_bigscape`) |
| `BlastDB` | BLAST, Taxonomy Finder (16S) | large (nt, nr) | BLAST databases (`makeblastdb`, or `update_blastdb.pl --decompress <name>` for NCBI ones) plus `database_options.json`, see below |
| `CblasterDB` | cblaster (local mode) | | `cblaster makedb <genomes> -n <name>` plus `database_options.json`, see below |

Notes:

* `ZolDB` contains its own copy of Pfam, so it overlaps with `PfamDB`; they are kept separate
  because zol's setup script wants to create (and deletes an existing) target folder. That only
  concerns downloading: at run time the folder is only read (PanBGC has been run with `/databases`
  mounted read-only, as in production).
* PADLOC's `--db-update` always installs into the conda env, so the download script copies the env's
  data folder out; at run time `padloc --data /databases/PadlocDB` is used and nothing is fetched.
* zol records absolute file paths in `ZolDB/database_location_paths.txt`. The download script rewrites
  them to `/databases/ZolDB/...` (the in-container path), so the folder works when copied as-is;
  if you ever download it by hand, do the same `sed`.
* zol's own `setup_annotation_dbs.py` aborts on a dead upstream URL (V-Score file); the helper
  script patches that out. Only the minimal set (Pfam + PGAP) is downloaded.
* BiG-SCAPE needs Pfam pre-pressed (`hmmpress`) because the folder is read-only in production.
* `BlastDB` and `CblasterDB` list what the submission pages offer in a `database_options.json`:

  ```json
  {"database_options": [
    {"value": "swissprot", "label": "swissprot", "db_type": "prot", "show_warning": false}
  ]}
  ```

  `value` is the database name inside the folder (BLAST: `db_type` is `nucl` or `prot`); for cblaster each
  option has a `mode` instead of `db_type`: `remote` (searched at NCBI, nothing in the folder) or `local`
  (`<value>.dmnd`, `<value>.fasta` and `<value>.sqlite3` in the folder). `show_warning` adds the in-house
  data notice to the page. To add a database, put its files in the folder and add an entry; the web
  containers read the file when they start.
