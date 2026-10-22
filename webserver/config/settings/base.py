"""
Base settings to build other settings files upon.
"""

import glob
import os

import environ

ROOT_DIR = environ.Path(__file__) - 3  # (baclab/config/settings/base.py - 3 = baclab/)
APPS_DIR = ROOT_DIR.path('baclab')

try:
    with open(str(ROOT_DIR.path('VERSION'))) as _version_file:
        BACLAB_VERSION = _version_file.read().strip()
except OSError:
    BACLAB_VERSION = 'unknown'

# Every newer tool lives in its own folder here (tools/<name>/tool.py, scripts, templates, ...), see tools/README.md
TOOLS_DIR = str(ROOT_DIR.path('tools'))

env = environ.Env()

READ_DOT_ENV_FILE = env.bool('DJANGO_READ_DOT_ENV_FILE', default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(ROOT_DIR.path('.env')))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool('DJANGO_DEBUG', False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = 'CET'
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = 'en-us'
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {
    'default': env.db('DATABASE_URL'),
}
DATABASES['default']['ATOMIC_REQUESTS'] = True
DATABASES['default']['ENGINE'] = 'django.db.backends.postgresql'

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = 'config.urls'
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = 'config.wsgi.application'

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'baclab'
]
THIRD_PARTY_APPS = [
    'adminsortable2',
    'ckeditor',
]
LOCAL_APPS = [
    # Your stuff: custom apps go here
    'baclab.admin_commands.apps.AdminConfig',
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(ROOT_DIR('staticfiles'))
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = '/static/'
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [
    str(APPS_DIR.path('static')),
]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR('media'))
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = '/media/'

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        'DIRS': [
            str(APPS_DIR.path('templates')),
            *sorted(glob.glob(os.path.join(TOOLS_DIR, '*/'))),   # a tool keeps its own templates next to its code
        ],
        'OPTIONS': {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-debug
            'debug': DEBUG,
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'baclab.context_processors.theme_settings',
                'baclab.context_processors.strain_collections',
                'baclab.context_processors.dynamic_tools',
                'baclab.context_processors.accounts',
            ],
        },
    },
]

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (
    str(APPS_DIR.path('fixtures')),
)

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env('DJANGO_EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = 'admin/'
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
# Where failure reports go and what users are told to write to. Set ADMIN_EMAIL in .envs/.production/.django
# (the old tools/admin_email.txt is still read when the variable is missing).
ADMIN_EMAIL = env('ADMIN_EMAIL', default='')
if not ADMIN_EMAIL:
    try:
        with open("/app/tools/admin_email.txt", "r") as f:
            ADMIN_EMAIL = f.read().strip()
    except Exception:
        ADMIN_EMAIL = "admin@example.com"

ADMINS = (
    ("BacLab Admin", ADMIN_EMAIL),
)
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# Celery
# ------------------------------------------------------------------------------
INSTALLED_APPS += ['baclab.taskapp.celery.CeleryAppConfig']
if USE_TZ:
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = env('CELERY_BROKER_URL')
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ['json']
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = 'json'
# http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = 'json'

# CKEDITOR
# ------------------------------------------------------------------------------
# https://django-ckeditor.readthedocs.io/en/latest/#optional-customizing-ckeditor-editor
CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'Custom',
        'toolbar_Custom': [
            ['Format', 'Bold', 'Italic', 'Underline'],
            ['NumberedList', 'BulletedList', 'Blockquote'],
            ['Link', 'Unlink'],
            ['Undo', 'Redo'],
            ['Source'],
        ],
        'height': 200,
        'width': 'auto',
    },
}

# Your stuff...
# ------------------------------------------------------------------------------
# Outgoing mail (job notifications, failure reports to the admins). Set EMAIL_HOST & co. in .envs/.production/.django
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=25)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)

SENDER_EMAIL = env("SENDER_EMAIL", default="no-reply@example.com")
SENDER_EMAIL_PASSWORD = env("SENDER_EMAIL_PASSWORD", default="")
# What users see as sender and subject prefix of the notifications (the same in local and production mode)
DEFAULT_FROM_EMAIL = env('DJANGO_DEFAULT_FROM_EMAIL', default=f'BacLab <{SENDER_EMAIL}>')
SERVER_EMAIL = env('DJANGO_SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
EMAIL_SUBJECT_PREFIX = env('DJANGO_EMAIL_SUBJECT_PREFIX', default='[BacLab] ')

UPLOAD_DIR = "/data/uploads"
DOWNLOAD_DIR = "/data/downloads"
RESULTS_DIR = "/data/results"

# Shared, read-only (in production) databases and models used by the tools (mounted into the containers)
DATABASES_DIR = env('DATABASES_DIR', default='/databases')
# Tools added in the admin keep their scripts and conda environments on the persistent data volume
CUSTOM_TOOLS_DIR = env('CUSTOM_TOOLS_DIR', default='/data/custom_tools')
CUSTOM_ENVS_DIR = env('CUSTOM_ENVS_DIR', default='/data/custom_envs')

# Django refuses requests with more than 100 files unless told otherwise; the tools enforce their own limits
DATA_UPLOAD_MAX_NUMBER_FILES = 1000

BLAST_SCRIPT = "/app/tools/blast/blast_script.sh"
CBLASTER_SCRIPT = "/app/tools/cblaster/cblaster_script.sh"
BAKTA_SCRIPT = "/app/tools/annotationPipeline/bakta_script.sh"
ANTISMASH_SCRIPT = "/app/tools/annotationPipeline/antismash_script.sh"
PROKKA_SCRIPT = "/app/tools/annotationPipeline/prokka_script.sh"
GBK_CONVERTER_SCRIPT = "/app/tools/annotationPipeline/gbk_converter_script.sh"
TAXONOMY_SCRIPT = "/app/tools/taxonomyFinder/taxonomyfinder_script.sh"
ABRICATE_SCRIPT = "/app/tools/abricate/abricate_script.sh"
PHYLOGENY_SCRIPT = "/app/tools/phylogeny/phylogeny_script.sh"
GENOMEMINING_SCRIPT = "/app/tools/genomeMining/genome_mining_script.sh"
PLASMIDFINDER_SCRIPT = "/app/tools/plasmidfinder/plasmidfinder_script.sh"
MULTIQC_SCRIPT = "/app/tools/multiqc/multiqc_script.sh"
MLST_SCRIPT = "/app/tools/mlst/mlst_script.sh"
AMRFINDERPLUS_SCRIPT = "/app/tools/amrfinderplus/amrfinderplus_script.sh"
CHECKM2_SCRIPT = "/app/tools/checkm2/checkm2_script.sh"
MOBSUITE_SCRIPT = "/app/tools/mobsuite/mobsuite_script.sh"
GECCO_SCRIPT = "/app/tools/gecco/gecco_script.sh"
GUBBINS_SCRIPT = "/app/tools/gubbins/gubbins_script.sh"
KRAKEN2_SCRIPT = "/app/tools/kraken2/kraken2_script.sh"
ANI_SCRIPT = "/app/tools/ani/ani_script.sh"
FASTAAI_SCRIPT = "/app/tools/fastaai/fastaai_script.sh"


BLAST_DATABASE_PATH = "/databases/BlastDB"
CBLASTER_DATABASE_PATH = "/databases/CblasterDB"

BAKTA_DB_PATH = "/databases/BaktaDB"
ANTISMASH_DB_PATH = "/databases/AntismashDB"
PROKKA_DB_PATH = "/databases/ProkkaDB"
ANNOTATION_DB_PATH = "/databases/AnnotationDB"
CHECKM2_DB_PATH = "/databases/Checkm2DB"
KRAKEN2_DB_PATH = "/databases/Kraken2DB"

INHOUSE_STRAINS_LIST = "/databases/StrainsDB/Inhouse_strains.tsv"
INHOUSE_TAXONOMY_PATH = "/databases/StrainsDB/Inhouse_taxonomy.tsv"

GTDBTK_DB_PATH = "/databases/GtdbtkDB/release232"
NCBI_TAXA_DB_PATH = "/databases/NCBI_Taxa"

PHYLOGENY_DATABASE = "/databases/PhylogenyDB"

PHYLOGENETIC_TREES_PATH = "/databases/PhylogeneticTree"

CDS_POSITIONS_FASTA = "/databases/GenomeMining/668_cds_positions.fasta"
BGC_INFO_CORE_PATH = "/databases/GenomeMining/bgc_info_core"
BGC_INFO_PATH = "/databases/GenomeMining/bgc_info"
PROKKA_INFO_PATH = "/databases/GenomeMining/prokka_info"



CORES_PER_JOB = env.int('CORES_PER_JOB', default=8)

# The address of the site as text without a trailing slash (links in e-mails and results pages are WEBSITE_LINK + "/path/")
WEBSITE_LINK = env.url('WEBSITE_LINK', default="http://localhost:8000/").geturl().rstrip('/')

# Days after which a query result is removed
MAX_RESULTS_AGE = env.int('MAX_RESULTS_AGE', default=30)
# Genomes (files and NCBI accessions together) one job may contain in the tools that take several: genome screen, DefenseFinder, PADLOC, GenoVi, RRE-Finder
MAX_GENOMES_PER_JOB = env.int('MAX_GENOMES_PER_JOB', default=20)
# Periods an account owner can choose to keep the results of a job (the default one first)
RETENTION_CHOICES = sorted({MAX_RESULTS_AGE, 90, 180})

# Optional restriction of notification e-mail addresses: comma separated regular expressions for the part after the @
# (the admin's "E-mail policy" takes precedence). Empty = any address.
NOTIFICATION_EMAIL_DOMAINS = env('NOTIFICATION_EMAIL_DOMAINS', default='')

# Monitoring (see tasks.check_system): the administrators are told once about jobs that run/wait longer than this, and about full disks.
# NOTIFY_WEBHOOK_URL (Slack / Teams / any endpoint taking {"text": ...}) gets the same messages as the e-mail.
STUCK_RUNNING_HOURS = env.int('STUCK_RUNNING_HOURS', default=48)
STUCK_QUEUED_HOURS = env.int('STUCK_QUEUED_HOURS', default=48)
DISK_ALERT_PERCENT = env.int('DISK_ALERT_PERCENT', default=90)
NOTIFY_WEBHOOK_URL = env('NOTIFY_WEBHOOK_URL', default='')
# Owners of jobs (with an e-mail address in their account) are warned this many days before the results are deleted
EXPIRY_WARNING_DAYS = env.int('EXPIRY_WARNING_DAYS', default=7)

# Job queues: heavy tools (hours, lots of memory) go to the "heavy" queue, everything else to "fast". The main worker takes both;
# the extra `celeryworker_light` container only takes "fast", so a quick MLST never waits behind a day-long GTDB-Tk.
HEAVY_TOOLS = env.list('HEAVY_TOOLS', default=[
    'taxonomyfinder', 'annotationPipeline', 'genomemining', 'spades', 'phylogeny', 'checkm', 'bigscape', 'bigslice', 'panbgc',
    'basalt', 'gtotree', 'gatorgc', 'screen'])

# User accounts are optional for the people using the site: anyone can still submit jobs without logging in.
# ACCOUNTS_ENABLED=False removes login, "my jobs" and groups from the site altogether.
# ALLOW_SIGNUP=True lets visitors create their own account; otherwise an administrator creates accounts in the admin.
ACCOUNTS_ENABLED = env.bool('ACCOUNTS_ENABLED', default=True)
ALLOW_SIGNUP = env.bool('ALLOW_SIGNUP', default=False)
# The JSON API (with per-user API keys) needs accounts; set API_ENABLED=False to switch it off
API_ENABLED = env.bool('API_ENABLED', default=True)
LOGIN_URL = 'baclab:login'
LOGIN_REDIRECT_URL = 'baclab:index'
LOGOUT_REDIRECT_URL = 'baclab:index'

# IDs of results to be kept regardless of age
KEEP_RESULTS = ["EXAMPLE"]



ANTISMASH_DATA_PATH = "/databases/AntismashResults"

LOCAL_DEBUG_MODE = False

EXAMPLE_DATA_DIR = str(APPS_DIR.path('example_data'))

CBLASTER_SPECIFIC_SANITIZATION = {
    "allowed_dmnd_sensitivity": ['fast', 'mid', 'sensitive', 'more', 'very', 'ultra'],
    "input_value_pattern": r"\d*\.?\d+([eE][\-+]?\d+)?",
    "allowed_key_value_functions": ["len", "sum", "max"],
    "allowed_hit_attributes": ["identity", "coverage", "bitscore", "evalue"]
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'


# Optional LDAP login (e.g. an institute directory). Off unless LDAP_SERVER_URI is set. Needs the image built with INSTALL_LDAP=1
# (see docs/ADMIN_GUIDE.md). Users are created on first login; their group is taken from LDAP_GROUP_ATTRIBUTE (e.g. department).
LDAP_SERVER_URI = env('LDAP_SERVER_URI', default='')
LDAP_GROUP_ATTRIBUTE = env('LDAP_GROUP_ATTRIBUTE', default='')
if LDAP_SERVER_URI:
    try:
        import ldap
        from django_auth_ldap.config import LDAPSearch
    except ImportError:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured('LDAP_SERVER_URI is set but the LDAP libraries are not in the image: build with INSTALL_LDAP=1 (docs/ADMIN_GUIDE.md).')
    AUTH_LDAP_SERVER_URI = LDAP_SERVER_URI
    AUTH_LDAP_BIND_DN = env('LDAP_BIND_DN', default='')
    AUTH_LDAP_BIND_PASSWORD = env('LDAP_BIND_PASSWORD', default='')
    AUTH_LDAP_USER_SEARCH = LDAPSearch(env('LDAP_USER_BASE'), ldap.SCOPE_SUBTREE, env('LDAP_USER_FILTER', default='(uid=%(user)s)'))
    AUTH_LDAP_USER_ATTR_MAP = {'first_name': env('LDAP_ATTR_FIRST_NAME', default='givenName'), 'last_name': env('LDAP_ATTR_LAST_NAME', default='sn'),
                               'email': env('LDAP_ATTR_EMAIL', default='mail')}
    AUTH_LDAP_ALWAYS_UPDATE_USER = True
    if env.bool('LDAP_START_TLS', default=False):
        AUTH_LDAP_START_TLS = True
    AUTHENTICATION_BACKENDS = ['django_auth_ldap.backend.LDAPBackend', 'django.contrib.auth.backends.ModelBackend']
