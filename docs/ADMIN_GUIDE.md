# BacLab administrator guide

Everything an administrator does, in one place. The same quick tips are shown on the admin start page (`/admin/`).

## 1. Install, update, look after the server
All of it is one command, run in the BacLab folder on the server:

| Task | Command |
|---|---|
| First installation (asks a few questions, builds, starts) | `./baclab install` |
| Update to a new version (backup, pull, rebuild, migrate, database check) | `./baclab update` |
| Containers, version, databases at a glance | `./baclab status` |
| Logs (`-f` follows) | `./baclab logs [-f] django` (also `celeryworker`, `nginx`, `postgres`) |
| Restart after changing a settings file | `./baclab restart` |
| Database backup / restore | `./baclab backup` / `./baclab restore backups/<file>.sql.gz` |
| Check environments, databases and run the example jobs | `./baclab selftest --run` |

**An update never touches your data**: jobs and results (`data/`), reference databases (`databases/`), users and admin settings (PostgreSQL volume),
uploaded files (media volume), your settings (`webserver/.envs/`, `webserver/.env`) and tools you added in the admin (`data/custom_tools`, `data/custom_envs`).
Before every update a PostgreSQL dump is written to `backups/` (the newest ten are kept). To go back: `git checkout <old version>`, `./baclab update --no-pull`,
and `./baclab restore` if the database must go back too.

Settings live in `webserver/.envs/.production/.django` (site, e-mail, admin account, cores per job, how long results are kept) and `webserver/.env`
(worker CPUs/memory, ports). Edit, then `./baclab restart`. HTTPS: put `fullchain.pem` and `privkey.pem` into `certs/`, set
`DJANGO_SECURE_SSL_REDIRECT=True` and an `https://` `WEBSITE_LINK`, restart. Rootless podman cannot use ports below 1024 - `./baclab install` then picks 8080/8443 by itself.

*Special file systems:* on a network file system (NFS, Lustre, GPFS) the SELinux label option `:z` of the volume mounts is refused; `./baclab install` detects that and writes
`DATA_MODE=rw`, `DB_MODE=ro`, `DB_WRITE_MODE=rw`, `DB_WORKER_MODE=rw` into `webserver/.env` (the defaults, with `,z`, are right for local disks). On SELinux hosts the application
containers share one SELinux level (`security_opt` in `production.yml`) so that the web and worker containers can read each other's files.

## 2. The tools menu
The **tools** menu opens one panel with a column per category (Quality control, AMR, Strain typing, Comparative genomics, Annotation & BGCs, Sequence search);
the tools in each column are sorted alphabetically. Only tools that are switched on appear. The **how to use** link in the top bar (and "How to use the tools" in the panel) opens a page with a short step-by-step guide per tool.

## 3. Switching tools on and off
In order of precedence: environment variable `ENABLE_TOOL_<name>=True/False` in `.envs/.production/.django` -> **Tool switches** in the admin (immediate) ->
default in `webserver/enabled_tools.csv` (shipped with the code; do not edit it on a server). BASALT is off by default (it needs 128 GB RAM).

## 4. Reference databases
Most tools need a database that is not part of the image. `./baclab db status` lists them (also: admin -> **System status**):

* `installed` - ready; `MISSING` - an enabled tool needs it; `not installed` - not needed by anything enabled.
* `./baclab db install` installs everything missing; `./baclab db install padloc gtdbtk` installs chosen ones (keys from `./baclab db list`).
* Installers run in a separate maintenance container (as root, so it can write whatever you own), then every installed file is made readable for the application
  containers - they run as an unprivileged user. If a tool complains about "permission denied" in a database folder, run `./baclab db fix-permissions`.
  The web container sees `/databases` read-only; the main worker may write to it, because it builds the databases and strains you add in the admin
  (*Custom databases*, *Inhouse strains*) - for that, `./baclab install/update` keeps the folders `BlastDB`, `CblasterDB`, `GenomeMiningDB`, `StrainsDB`, `AnnotationDB`,
  `AntismashResults`, `PhylogenyDB` and `PhylogeneticTree` writable. Downloads can be large (GTDB-Tk 56 GB, ZolDB 11 GB, BLAST nr 400 GB).
* **Genome Mining** has no ready-made database: build one from your own genomes (admin -> *Custom databases* -> tool "Genome Mining" -> a zip of FASTA files); it runs Prokka and antiSMASH
  on every genome, so it takes a while. Until one exists the tool page says so.
* A tool whose database is missing shows a notice on its page and refuses jobs until it is installed.
* BLAST and cblaster databases are listed on their pages through `database_options.json` in their folder; `./manage_blast_db.sh` and the admin's *Custom databases* add your own.
* Details per database: `webserver/tools/DATABASES.md`.

## 5. Adding a tool without programming (admin -> Custom tools)
1. **Name** (2-24 lowercase letters/digits, cannot change later), **title**, **category**, one-sentence **description**.
2. **Input**: accepted file extensions, minimum/maximum number of files. Optional **parameters** as JSON, e.g.
   `[{"name": "mode", "label": "Mode", "type": "choice", "choices": ["fast", "accurate"], "default": "fast"}]` (types: `choice`, `int` with `min`/`max`, `bool`).
3. **Script** (bash). It gets `$INPUT_DIR` (uploaded files), `$OUTPUT_DIR` (write results here), `$CORES_PER_JOB`, `$DATABASES_DIR` (`/databases`) and `$PARAM_<NAME>` per parameter. A non-zero exit fails the job.
4. **Environment YAML** (optional, conda). Save, then in the list select the tool and run **Build the conda environment** (minutes; follow the status badge).
   Environments are stored in `data/custom_envs`, so updates do not remove them.
5. **Results**: just the download, one table file (name or pattern like `*.tsv`, separator), or one HTML report.
6. Tick **enabled** (only possible once the environment is ready). The tool now appears in the menu with its own page, queue and results page.

Example script: `for f in "$INPUT_DIR"/*; do echo -e "$(basename $f)\t$(grep -c '>' $f)" >> "$OUTPUT_DIR/counts.tsv"; done` with result type *table* and file `counts.tsv`.
Scripts run on the server with the rights of every other tool: give this permission only to administrators you trust. Tools that belong in the release are better written as
tool folders (`webserver/tools/README.md`).

## 6. User accounts and groups (optional)
Nobody has to log in: every tool works anonymously, exactly as before. Accounts are an extra for people who want to find their old runs.

* **What users get:** a *login* link; once logged in, a **my jobs** page with all their runs (search, filter by status, group by date/tool/status), a detail page per run
  (input files, settings, status, error), the option to **name a run** and to **keep its results longer** (default `MAX_RESULTS_AGE` days, or 90/180). Their e-mail is
  pre-filled for job notifications.
* **Groups:** create groups in admin -> **User groups** (a lab, a class, a department) and put users into one on their user page (*Group*). Members of a group see each
  other's runs on the **Group** tab of my jobs and can open them. Each user belongs to at most one group; a job keeps the group it was submitted under.
  Anonymous jobs are never listed. Anyone who knows a result link can still open that results page (as before) - groups only control who sees the job *lists*.
* **Creating accounts:** admin -> Users -> *Add user* (then choose the group), or set `ALLOW_SIGNUP=True` so visitors can register themselves (they start without a group).
  Users can change their own password from my jobs. Password reset by e-mail is not set up.
* **Switching off:** `ACCOUNTS_ENABLED=False` in `.envs/.production/.django` hides login, my jobs and groups everywhere. Existing data stays.
* In the admin, **Job records** show owner and group and can be filtered by group.

### Limiting notification e-mail addresses (optional)
Users can enter an e-mail address on every tool page (job-finished notification) and store one in their account (my jobs). To restrict which addresses are accepted:
admin -> **E-mail policy** -> one **regular expression per line**, matched against the whole part after the `@` (case-insensitive). Empty = any address.

| Line | Allows |
|---|---|
| `example\.org` | exactly `@example.org` |
| `.*\.example\.org` | every sub-domain, e.g. `@cs.example.org` |
| `(example\.org\|example\.de)` | two domains |
| `.*\.edu` | any `.edu` address |

Write `\.` for a dot (a bare `.` matches any character). The tool pages then show "Only addresses ending in ... are accepted" and refuse others; leaving the address empty is
always fine. Invalid expressions are rejected when you save. As a file-based alternative set `NOTIFICATION_EMAIL_DOMAINS=example\.org,.*\.edu` (comma separated) in
`.envs/.production/.django`; the admin's policy takes precedence.

## 7. Features for labs

**For users (all optional, most need a login):**
* **Key findings** - every finished run gets a one-line headline and a few numbers ("2 defence systems found", "completeness 99.1%, contamination 0.4%") on "my jobs" and the run page.
  Tools without their own summarizer show the number of result files; add one in `baclab/summaries.py` (`SUMMARIZERS`).
* **Projects** - group related runs ("Outbreak 2026"): filter by project, see all key findings side by side (CSV), download all results in one zip.
* **Run again** and **Use results in another tool** (run page): re-run with the same inputs and settings while the inputs are still kept (newer tools only), or feed result
  files (e.g. the genomes an assembler produced) to another tool that takes genome files.
* **Private runs** - a checkbox on the tool page (when logged in) or a button on the run page: only the owner and their group can open the results; everything else stays open by link.
* **NCBI accessions** - on every multi-genome tool page: paste assembly accessions (GCF_/GCA_...) instead of uploading; the worker downloads them (needs internet access from the worker container).
* **Methods text** - a ready paragraph for a paper (tool, installed version, settings, database dates, references) on the run page; the tool version is also shown on the tool page and in `CITATION.txt`.
* **Genome screen** - a pipeline tool: upload genomes once, tick analyses (MLST, resistance genes, CheckM2, DefenseFinder) and get one table with a row per genome.
* **API and command line** - my jobs -> *API keys* creates a key; `./baclab-client submit padloc g1.fasta --wait --download results.zip` or plain HTTP (`/api/v1/...`).
  Switch off with `API_ENABLED=False`. Only the tools built on the toolkit that take genome files are available (`baclab-client tools` lists them); the older single-purpose pages (e.g. MLST, Abricate) are web-only.
* **Warnings before deletion** - owners with an e-mail address in their account get one mail a week before their results are deleted (`EXPIRY_WARNING_DAYS`).

**For administrators:**
* **Job limits** (admin -> Job limits): cap the jobs a user, a group or all anonymous visitors may have waiting/running at once (0 = unlimited).
* **Queues**: heavy tools (`HEAVY_TOOLS`, e.g. GTDB-Tk, annotation, BiG-SCAPE) go to the `heavy` queue, everything else to `fast`. The main worker takes both, `celeryworker_light`
  only `fast`, so quick jobs never wait behind a day-long one. Size them in `webserver/.env` (`LIGHT_WORKER_*`).
* **Live monitor** (admin -> Live monitor): CPU (total, load, every core), memory and swap, GPUs (utilisation, memory, temperature, power), storage and the running jobs,
  refreshed every 2 seconds with a short history graph. Values are for the whole server, because the containers share its kernel.
  *GPU in the live monitor:* the monitor asks `nvidia-smi`, so the **web container** needs to see the GPU. With Docker add to the `django` service in `production.yml`
  `deploy: {resources: {reservations: {devices: [{driver: nvidia, count: all, capabilities: [gpu]}]}}}`; with Podman install the NVIDIA container toolkit, generate the CDI file
  (`sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`) and add `devices: ["nvidia.com/gpu=all"]` to the `django` service. Without it the page says no GPU is visible
  (nothing else is affected; none of the standard tools needs a GPU).
* **System status** (admin): disk use of the data and database volumes, workers answering, jobs waiting per queue. **Usage** (admin): jobs, wall hours and estimated CPU hours per
  user, group and tool for a month, as a table and CSV - for sharing the cost of the server.
* **Alerts** (hourly check): a job running/queued longer than `STUCK_RUNNING_HOURS` / `STUCK_QUEUED_HOURS` (48 h), or a disk above `DISK_ALERT_PERCENT` (90 %), is e-mailed to the
  administrators once. Set `NOTIFY_WEBHOOK_URL` (Slack incoming webhook, Teams, anything accepting `{"text": ...}`) to get the same messages in chat.
* **LDAP login** (optional, untested against a real directory - try it on a test server first): build with `INSTALL_LDAP=1` (in `webserver/.env` or `--build-arg`), then set
  `LDAP_SERVER_URI`, `LDAP_USER_BASE`, `LDAP_USER_FILTER` (default `(uid=%(user)s)`), optionally `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD`, `LDAP_START_TLS=True` and
  `LDAP_GROUP_ATTRIBUTE=department` (the user's group is created/assigned from that attribute) in `.envs/.production/.django`. Local accounts keep working.

## 8. Other admin sections
* **Job records** - every job with status, timing and error log; *Mark selected as failed* clears stuck jobs.
* **Inhouse strains / collections** - your own genomes, annotated and listed under the *strains* menu (bulk upload from a zip).
* **Custom databases** - build BLAST, cblaster, phylogeny or genome-mining databases from uploaded files.
* **Site pages** - Terms and Contact text. **Theme settings** - colours.
* **Server benchmarks** - measure run time and memory of the tools on this server.

## 8b. E-mail notifications
Users who give an address get an e-mail when their job finishes or fails, and a week before results are deleted (account owners). Set the mail server in
`webserver/.envs/.production/.django` (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `SENDER_EMAIL`), then `./baclab restart`.

**Edit the texts:** admin -> *E-mail messages*. The page starts with the default texts; change them as you like (a field you empty falls back to the default, and *Restore the default texts* brings all of them back). Placeholders in curly brackets are replaced
(`{job_id}`, `{job_name}`, `{tool}`, `{results_url}`, `{error}` for failures, `{expires}` for the deletion warning); the page lists them per message and refuses unknown ones.
This works the same in local and production mode.

**Genomes per job:** the multi-genome tools (genome screen, DefenseFinder, PADLOC, GenoVi, RRE-Finder) accept 20 genomes per job by default. Set `MAX_GENOMES_PER_JOB=<n>` in `webserver/.envs/.production/.django` and restart to change it; larger jobs need more time and memory.

**Test it:** type your address under *Send a test to* and save: one sample of each message, with the texts as you wrote them, is sent to it (the page shows an error
if the mail server refuses). The same from the command line: `./baclab shell`, then `python manage.py test_email --to you@example.org [--kind failed]`.
Local mode has no mail server: the messages are written to the log (`./baclab logs django`, look for "Subject:").

## 9. When something goes wrong
| Symptom | Look at |
|---|---|
| Page not reachable | `./baclab status`, `./baclab logs nginx`, ports in `webserver/.env` |
| "502 Bad Gateway" right after start | the web app is still migrating: `./baclab logs django` |
| A tool says its database is missing | `./baclab db install <key>` |
| Jobs stay "queued" | `./baclab logs celeryworker`; all workers busy? raise `CELERY_WORKER_CONCURRENCY` in `webserver/.env` |
| A job failed | admin -> Job records -> error log; the failed-job archive was e-mailed to the administrator |
| A tool fails but others work | `./baclab selftest --tool <name>` |
| Results disappeared | they are deleted after `MAX_RESULTS_AGE` days (default 30) |

## 10. Demo data
To look at all the pages with realistic content (users, groups, projects, finished/failed/running runs with mock result files): inside the web container run
`python manage.py create_demo_data` (`./baclab shell`, then the command). It creates 3 groups, 10 users (`m.schumacher`, `s.hansen`, ... all with password `demo-baclab-1`; set
`ACCOUNTS_ENABLED=True`) and about 50 runs. Everything is marked with the e-mail domain `@demo.baclab.example` and removed again with `python manage.py create_demo_data --remove`.
The results are random numbers, not real analyses.

## 11. Citing
The BacLab paper reference is still a placeholder: see `CITATION.cff` and `PLATFORM_CITATION` in `webserver/baclab/citations.py`.
