# Getting started

## Prerequisites
A Linux server with [Docker](https://docs.docker.com/get-docker/) (with the compose plugin) or Podman + `podman-compose`, `git` and `python3` (3.6+), and disk space:
the image with all conda environments is about 40 GB; the reference databases need from a few GB (only the tools you use) up to several hundred GB (BLAST nr/nt,
GTDB-Tk 56 GB). Memory: 16 GB is enough for most tools; GTDB-Tk and Kraken2 need more, BASALT 128 GB (off by default).

## Install
```bash
git clone https://github.com/kalininalab/BacLab.git BacLab && cd BacLab
./baclab install
```
It asks a few questions (production or local test, administrator account and e-mail, host name), writes the settings files (with generated secrets) under
`webserver/.envs/`, sizes the worker to the machine, builds the images (the first build takes 1-3 hours) and starts everything. Then install the reference
databases the tools need:

```bash
./baclab db status                 # what is installed / missing
./baclab db install                # install all that enabled tools need, or:  ./baclab db install padloc gtdbtk
./baclab selftest                  # checks conda environments + databases inside the containers (--run also runs every tool on its example)
```

Open `http://<your-host>/` (rootless Podman: port 8080; local mode: `http://localhost:8000`). HTTPS: put `fullchain.pem` and `privkey.pem` into `certs/` and run
`./baclab restart`. The **administrator user name** is the one you gave the installer (suggested: `admin`); the password you chose, or the generated one the
installer printed once - both are in `webserver/.envs/.production/.django` (`ADMIN_USER`, `ADMIN_PASS`).

## Update - without losing anything
```bash
./baclab update
```
It makes a PostgreSQL backup (`backups/`), pulls the new version, rebuilds the images (unchanged conda environments come from the cache, so only new tools take
long), restarts, applies database migrations and lists databases that new tools need. Your **jobs and results (`data/`), reference databases (`databases/`), users and
admin settings (PostgreSQL volume), uploaded files (media volume), settings (`webserver/.envs/`, `webserver/.env`) and tools you added in the admin** are never
touched. Roll back with `git checkout <old tag>` + `./baclab update --no-pull`, and `./baclab restore backups/<file>.sql.gz` for the database.

## Everyday
`./baclab status` - `./baclab logs [-f] [service]` - `./baclab restart` - `./baclab backup` - `./baclab shell`.

## Try the examples
Every tool page has **Download Example Data** and **View Example Results** (BASALT excepted). `./baclab selftest --run` runs all of them. To prepare the
results of all examples at once (so nobody waits for them), open `./baclab shell` and run `python manage.py prerun_examples`.
