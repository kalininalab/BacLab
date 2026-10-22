# BacLab: A Self-Hosted, Containerized Web Platform for Integrated Bacterial Genomics and Genome Mining

BacLab is a comprehensive, Docker-compose based microservices platform designed for bioinformatics and computational biology pipelines. It provides a easy-to-use web interface and a robust Celery-backed task queues to run heavy bioinformatics tools seamlessly.

## Key Features

* **Docker Image**: BacLab is distributed as a unified monolithic Docker image containing all bioinformatics dependencies pre-installed (via isolated Conda environments). You only build it once.
* **Runtime Tool Configuration**: Switch pipelines on or off from the admin (or with environment variables such as `ENABLE_TOOL_BLAST=False`) without rebuilding anything.
* **Add tools without programming**: define a bash script, input types and result view in the admin; or drop a `tools/<name>/` folder into the code base (see `webserver/tools/README.md`).
* **Database management**: `./baclab db status|install` automatically fetches every required reference database, installs it into a persistent folder and tells you which tool is waiting for which one.
* **Updates that keep your data**: `./baclab update` backs up, pulls, rebuilds and migrates; jobs, databases and users live outside the images.
* **Asynchronous Task Queue**: Uses Celery and Redis to automatically handle heavy jobs seperately from light jobs in the background.
* **Optional user accounts and groups**: Users can use every tool anonymously; with a login they get a "my jobs" page, can name runs and keep results longer, and see the runs of their group.
* **Made for labs**: Safe to use system that can work only on intranet without requirement of constant internet access (except build time)
* **Administrative Dashboard**: A built-in, secure Django admin panel allows administrators to manage various settings, tools and databases.
* **Local and Production Ready**: Comes with configurations for both local testing (`local.yml`) and production deployments (`production.yml`), backed by NGINX and PostgreSQL.

## Screenshots and Pipelines

### 1. Unified Dashboard
![BacLab Dashboard](docs/images/dashboard.png)

### 2. Genome Annotation
![Genome Annotation Tool](docs/images/annotation.png)

### 3. Homology Searching (BLAST)
**Input Interface:**
![BLAST Interface](docs/images/blast_interface.png)
**Results View:**
![BLAST Results](docs/images/blast_results.png)

### 4. Biosynthetic Gene Cluster Mining (cblaster)
**Input Interface:**
![cblaster Interface](docs/images/cblaster_interface.png)
**Results View:**
![cblaster Results](docs/images/cblaster_results.png)

### 5. Phylogeny and Taxonomy (GTDB-Tk & 16S)
![Phylogeny Tool](docs/images/phylogeny.png)

### 6. AMR Profiling (Abricate)
![Abricate Tool](docs/images/abricate.png)

### 7. Genome Assembly & Quality Control (SPAdes, fastp, QUAST, CheckM)
![SPAdes Pipeline](docs/images/spades.png)

### 8. Pan-Genome Analysis (Panaroo)
![Panaroo Tool](docs/images/panaroo.png)

### 9. Core-Genome Variant Calling (Snippy)
![Snippy Tool](docs/images/snippy.png)

### 10. Plasmid Replicon Identification (PlasmidFinder)
![PlasmidFinder Tool](docs/images/plasmidfinder.png)

### 11. User Space (optional accounts and groups)
**My jobs** - the member's own runs and those of the group, with status, key result and many more information:
![My jobs](docs/images/user_my_jobs.png)
**A single run** - key findings, methods text, re-run, reuse in another tool (if available/possible), project and sharing settings:
![Job details](docs/images/user_job.png)

### 12. Administrative Dashboard
![Admin Dashboard](docs/images/admin.png)

## Quick Start

### 1. Prerequisites
A Linux server with [Docker](https://docs.docker.com/get-docker/) (with the compose plugin) or Podman + `podman-compose`, `git`, `python3` (3.6+), and disk space:
the image with all conda environments is ~40 GB, the reference databases from a few GB (only the tools you use) up to several hundred GB (BLAST nr/nt, GTDB-Tk 56 GB).
Memory: 16 GB is enough for most tools; GTDB-Tk and Kraken2 need more (~32 GB), BASALT 128 GB (off by default).

### 2. Install
```bash
git clone https://github.com/kalininalab/BacLab.git BacLab && cd BacLab
./baclab install
```
It asks a few questions (production or local test, administrator account and e-mail, host name), writes the settings files (with generated secrets) under
`webserver/.envs/`, sizes the worker to the machine, builds the images (the first build takes 1-3 hours) and starts everything. Then install the
reference databases the tools need:

```bash
./baclab db status                 # what is installed / missing
./baclab db install                # install all that enabled tools need, or:  ./baclab db install padloc gtdbtk
./baclab selftest                  # checks conda environments + databases inside the containers
```

Open `http://<your-host>/` (local mode: `http://localhost:8000`). HTTPS: put `fullchain.pem` and `privkey.pem` into `certs/` and run `./baclab restart`.

### 3. Update (new version, new tools) - without losing anything
```bash
./baclab update
```
It makes a PostgreSQL backup (`backups/`), pulls the new version, rebuilds the images (unchanged conda environments come from the cache,
so only new tools take long), restarts, applies database migrations and lists databases that new tools need. Your **jobs and results (`data/`),
reference databases (`databases/`), users and admin settings (PostgreSQL volume), uploaded files (media volume), settings (`webserver/.envs/`,
`webserver/.env`) and tools you added in the admin (`data/custom_tools`, `data/custom_envs`) are never touched** - they live outside the images and
outside git. Roll back a bad update with `git checkout <old tag>` + `./baclab update --no-pull`, and `./baclab restore backups/<file>.sql.gz` for the database.

### 4. Everyday
`./baclab status` - `./baclab logs [-f] [service]` - `./baclab restart` - `./baclab backup` - `./baclab shell`.
In the admin (`/admin/`): **System status** (tools and databases at a glance), **Tool switches**, **Custom tools** (add a tool without programming),
custom BLAST/cblaster/... databases, strain collections, theme and the Terms/Contact pages.

For everything an administrator does (tools menu, databases, adding tools in the admin, troubleshooting) see **[docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md)**.

## Citing BacLab
> *Yurtseven A, et al. BacLab: a self-hosted, containerized web platform for integrated bacterial genomics and genome mining. [Journal, year, DOI].*
>
> Please also cite the tools you used; each tool page and result archive lists them.

## Documentation

The documentation is built with Sphinx for Read the Docs (`docs/`, `.readthedocs.yaml`): getting started, the administrator guide, the tools reference, development notes and the **demonstrations** - three single HTML files without a server: the clickable site, the site seen by a logged-in lab member, and the administration pages. Build locally: `pip install -r docs/requirements.txt && sphinx-build -b html docs docs/_build/html`.

For a detailed breakdown of all available bioinformatics pipelines, what inputs they require, what outputs they produce, and how to configure their specific databases, please refer to the [Tools and Pipelines Documentation](webserver/tools/README.md).

## Project Structure

* `baclab` - the install/update/database/backup command (this is what you run on the server).

* `webserver/baclab/` - The core Django application containing views, API endpoints, models, and UI templates.
* `webserver/tools/` - The directory containing all the shell scripts and configurations for the bioinformatics tools.
* `webserver/conda_environments/` - The YAML files defining the Conda dependencies for each tool.
* `webserver/compose/` - Dockerfiles and startup scripts for Django, Celery, NGINX, and Postgres.

## License
[MIT License](LICENSE)
