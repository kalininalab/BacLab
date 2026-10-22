from datetime import timedelta

from ckeditor.fields import RichTextField
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify


class LabGroup(models.Model):
    """A group of users (a lab, department, class) whose members can see each other's jobs on the "My jobs" page.
    Optional: nothing requires users or groups to exist."""
    name = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "User group"
        verbose_name_plural = "User groups"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Extra per-user data: the group the user belongs to (assigned by an administrator in the admin)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    group = models.ForeignKey(LabGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="members",
                              help_text="Members of the same group can see each other's jobs.")

    def __str__(self):
        return f"{self.user} ({self.group or 'no group'})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


def get_user_group(user):
    """The LabGroup of `user`, or None for anonymous users and users without a group."""
    if user is None or not user.is_authenticated:
        return None
    profile = UserProfile.objects.filter(user=user).select_related("group").first()
    return profile.group if profile else None


class Project(models.Model):
    """A user's folder for related runs ("E. coli outbreak 2026"): filter by it, compare its runs, download everything at once."""
    name = models.CharField(max_length=100)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("owner", "name")]

    def __str__(self):
        return f"{self.name} ({self.owner})"


class JobRecord(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("finished", "Finished"),
        ("failed", "Failed"),
    ]

    job_id = models.CharField(max_length=128, primary_key=True)
    job_type = models.CharField(max_length=64, blank=True, help_text="Identifies which pipeline created this record (e.g. 'blast', 'snippy').")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued", help_text="Current lifecycle state of the job.")
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    error_log = models.JSONField(default=dict, blank=True, null=True)
    email = models.EmailField(blank=True, null=True, help_text="Optional email address to notify when the job finishes.")
    # Empty for anonymous submissions (logging in is optional). `group` is the owner's group at submission time,
    # so a job stays with its group when the user later moves.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    group = models.ForeignKey(LabGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    # Days the results are kept; NULL = the default (settings.MAX_RESULTS_AGE). The owner can pick one of settings.RETENTION_CHOICES.
    retention_days = models.PositiveSmallIntegerField(null=True, blank=True)
    label = models.CharField(max_length=100, blank=True, help_text="Name the owner gave the run.")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    # Only the owner and the members of the owner's group may open the results of a private job (needs a login)
    private = models.BooleanField(default=False)
    # Key findings built by summaries.summarize() when the job finished. NULL = not computed yet; {} = nothing to show for this tool.
    summary = models.JSONField(null=True, blank=True)
    stuck_alert_sent = models.BooleanField(default=False)
    expiry_warned = models.BooleanField(default=False)
    # What was submitted: {"inputs": [file names], "settings": {name: value}}
    parameters = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-queued_at"]

    def __str__(self):
        return f"{self.job_id} ({self.status})"

    @property
    def tool_label(self):
        from .toolkit import registry
        tool = registry.get(self.job_type)
        if tool is not None:
            return tool.title
        return self.job_type or "unknown"

    @property
    def is_active(self):
        return self.status in ("queued", "running")

    @property
    def effective_retention_days(self):
        return self.retention_days or settings.MAX_RESULTS_AGE

    @property
    def expires_at(self):
        """Approximate deletion time (the clean-up goes by the job folder's age, roughly when the job finished)."""
        return (self.finished_at or self.queued_at) + timedelta(days=self.effective_retention_days)

    @property
    def days_left(self):
        return (self.expires_at - timezone.now()).days

    @property
    def expires_soon(self):
        return self.days_left < 7

    @property
    def duration_display(self):
        duration = self.duration
        if duration is None:
            return ""
        seconds = int(duration.total_seconds())
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    @property
    def duration(self):
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None


class InhouseStrain(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    strain_id = models.CharField(max_length=128, primary_key=True)
    genome_fasta = models.FileField(upload_to='inhouse_uploads/', help_text="FASTA file for the strain's genome assembly.")
    run_prokka = models.BooleanField(default=True, help_text="Annotate the genome with Prokka.")
    run_antismash = models.BooleanField(default=True, help_text="Scan for biosynthetic gene clusters with antiSMASH.")
    run_gtdbtk = models.BooleanField(default=True, help_text="Classify taxonomy with GTDB-Tk.")
    
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    taxonomy = models.CharField(max_length=512, blank=True)
    error_message = models.TextField(blank=True)
    error_log = models.JSONField(default=dict, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.strain_id

class InhouseStrainCollection(models.Model):
    name = models.CharField(max_length=128, unique=True, help_text="Display name shown in the Strains nav dropdown.")
    slug = models.SlugField(max_length=140, unique=True, blank=True, help_text="Auto-generated from the name; used in the URL.")
    strains = models.ManyToManyField(InhouseStrain, related_name='collections', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Inhouse Strain Collection"
        verbose_name_plural = "Inhouse Strain Collections"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            i = 1
            while InhouseStrainCollection.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                i += 1
                slug = f"{base_slug}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)


class GlobalStrainResource(models.Model):
    phylogenetic_tree = models.FileField(
        upload_to='resources/trees/', 
        blank=True, 
        null=True, 
        help_text="Upload a Phylogenetic Tree file. Expected format: Newick (.nwk). This file will be available for users to download on the Strains page."
    )
    taxonomy_db = models.FileField(
        upload_to='resources/taxonomy/', 
        blank=True, 
        null=True, 
        help_text="Upload a Taxonomy Database file. Expected format: Tab-separated values (.tsv). This file will populate the 'View Taxonomy DB' page. Note: GTDB-Tk automatically appends to a separate file, but this upload will override the Strains page link if provided."
    )
    
    class Meta:
        verbose_name = "Global Strain Resource"
        verbose_name_plural = "Global Strain Resources (Singleton)"

    def __str__(self):
        return "Global Strain Resources (Edit this to update files)"
    
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

class CustomDatabase(models.Model):
    TOOL_CHOICES = [
        ("blast", "BLAST"),
        ("cblaster", "cblaster"),
        ("phylogeny", "Phylogeny"),
        ("genomemining", "Genome Mining"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("building", "Building"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]
    
    db_name = models.CharField(max_length=128, unique=True, help_text="Alphanumeric name for the database (no spaces), e.g., MyCustomDB")
    tool = models.CharField(max_length=32, choices=TOOL_CHOICES, default="blast")
    input_files = models.FileField(upload_to='custom_db_uploads/', help_text="In order to create a BLAST db, please upload a FASTA file or a zip archive containing only FASTA files. For creating a cblaster db, please upload a GBK file or a zip archive containing only GBK files. For phylogeny or genome mining, please upload a FASTA file or zip archive of FASTA files.")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.db_name} ({self.get_tool_display()}) - {self.status}"

class ThemeSettings(models.Model):
    primary_color = models.CharField(max_length=20, default="#005aa2", help_text="Main color for buttons, headers, etc. (e.g. #005aa2)")
    secondary_color = models.CharField(max_length=20, default="#008cff", help_text="Highlight color, e.g., on hover (e.g. #008cff)")
    background_color = models.CharField(max_length=20, default="snow", help_text="Global background color (e.g. snow)")
    button_color = models.CharField(max_length=20, default="#005aa2", help_text="Button background color (e.g. #005aa2)")
    text_color = models.CharField(max_length=20, default="#000000", help_text="Global text color (e.g. #000000 or black)")

    class Meta:
        verbose_name = "Theme Setting"
        verbose_name_plural = "Theme Settings (Singleton)"

    def __str__(self):
        return "Theme Settings (Edit this to update colors)"
    
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

class SitePage(models.Model):
    PAGE_CHOICES = [
        ("terms", "Terms and Conditions"),
        ("contact", "Contact Us"),
    ]

    page_key = models.CharField(max_length=32, choices=PAGE_CHOICES, unique=True)
    title = models.CharField(max_length=200)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Page"
        verbose_name_plural = "Site Pages (Terms & Contact)"

    def __str__(self):
        return self.get_page_key_display()

    @property
    def last_updated(self):
        latest_section = self.sections.aggregate(models.Max("updated_at"))["updated_at__max"]
        if latest_section and latest_section > self.updated_at:
            return latest_section
        return self.updated_at


class PageSection(models.Model):
    page = models.ForeignKey(SitePage, related_name="sections", on_delete=models.CASCADE)
    heading = models.CharField(max_length=200, blank=True, help_text="Optional heading shown above this section.")
    body = RichTextField(help_text="Section content. Use the toolbar for formatting, links, and lists.")
    is_published = models.BooleanField(default=True, help_text="Uncheck to hide this section from the live site without deleting it.")
    order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Page Section"

    def __str__(self):
        return self.heading or f"Section {self.order + 1}"


class ServerBenchmark(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default="Running")
    results_json = models.JSONField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Server Benchmark"
        verbose_name_plural = "Server Benchmarks"
        
    def __str__(self):
        return f"Benchmark Run - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class ToolSetting(models.Model):
    """Switch a tool on or off from the admin. Without a row the defaults of enabled_tools.csv apply; the
    ENABLE_TOOL_<name> environment variables of a deployment still win over both (see tool_catalog.enabled_map)."""
    tool = models.CharField(max_length=64, unique=True, help_text="Tool key, e.g. 'blast' or 'padloc'.")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["tool"]
        verbose_name = "Tool switch"
        verbose_name_plural = "Tool switches"

    def __str__(self):
        return f"{self.tool}: {'on' if self.enabled else 'off'}"


class CustomTool(models.Model):
    """A tool added in the admin: an uploaded genome/file is handed to a bash script, and the files the script
    writes to its output folder are shown as a table, an HTML report or a plain download. Turned into a
    toolkit.Tool by toolkit/custom.py, so it gets a page, menu entry, job queue and results like any other tool."""
    CATEGORY_CHOICES = [
        ("qc", "Quality Control & Assembly"),
        ("amr", "AMR, Virulence & Mobile Elements"),
        ("strain", "Strain Typing & Taxonomy"),
        ("compgen", "Comparative Genomics"),
        ("annot", "Annotation & Biosynthetic Gene Clusters"),
        ("search", "Sequence Search"),
    ]
    RESULT_CHOICES = [
        ("files", "Just the download (zip of the output files)"),
        ("table", "Show one table file"),
        ("html", "Show one HTML report"),
    ]
    ENV_CHOICES = [
        ("none", "No environment needed"),
        ("pending", "Not built yet"),
        ("building", "Building"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]

    name = models.CharField(max_length=24, unique=True, help_text="Short identifier: lowercase letters and digits, starting with a letter (e.g. 'mytool'). Used in the URL and the job ids; cannot be changed later.")
    title = models.CharField(max_length=100, help_text="Name shown in the menus and on the page.")
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default="annot")
    description = models.CharField(max_length=300, blank=True, help_text="One sentence shown under the page title.")
    enabled = models.BooleanField(default=False, help_text="Show the tool to users. Build its environment and test it first.")

    accepted_extensions = models.CharField(max_length=200, default=".fasta,.fa,.fna", help_text="Comma separated file extensions users may upload, e.g. .fasta,.fa,.fna")
    min_files = models.PositiveSmallIntegerField(default=1)
    max_files = models.PositiveSmallIntegerField(default=20)

    script = models.TextField(help_text="Bash commands run for every job. Available: $INPUT_DIR (the uploaded files), $OUTPUT_DIR (write results here), $CORES_PER_JOB, $DATABASES_DIR (/databases) and one $PARAM_<NAME> per parameter below. If an environment is defined, it is activated first. A non-zero exit code fails the job.")
    environment_yml = models.TextField(blank=True, help_text="Optional conda environment (conda YAML) for the script. Leave empty if the script only needs tools that are already in the image. Build it with the 'Build environment' action.")
    env_status = models.CharField(max_length=16, choices=ENV_CHOICES, default="none", editable=False)
    env_log = models.TextField(blank=True, editable=False)

    parameters = models.TextField(blank=True, help_text='Optional options users can set, as JSON, e.g. [{"name": "mode", "label": "Mode", "type": "choice", "choices": ["fast", "accurate"], "default": "fast"}, {"name": "evalue", "label": "E-value exponent", "type": "int", "min": 1, "max": 20, "default": 5}, {"name": "strict", "label": "Strict mode", "type": "bool"}]. Types: choice, int, bool.')

    result_kind = models.CharField(max_length=8, choices=RESULT_CHOICES, default="files")
    result_file = models.CharField(max_length=200, blank=True, help_text="File (name or pattern like *.tsv, relative to $OUTPUT_DIR) to show on the results page for the table / HTML result types.")
    result_title = models.CharField(max_length=100, blank=True, help_text="Heading of the shown table / report.")
    result_separator = models.CharField(max_length=8, default="tab", help_text="Column separator of the table file: 'tab' or ',' or ';'.")
    keep_outputs = models.CharField(max_length=300, blank=True, help_text="Comma separated names / folders / patterns to keep from $OUTPUT_DIR. Empty keeps everything.")

    databases = models.CharField(max_length=300, blank=True, help_text="Comma separated folders under databases/ the script needs (checked on the database status page).")
    citation_text = models.CharField(max_length=500, blank=True, help_text="Publication to cite (shown on the page and in the results).")
    citation_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "Custom tool"
        verbose_name_plural = "Custom tools"

    def __str__(self):
        return f"{self.title} ({self.name})"

    def clean(self):
        from django.core.exceptions import ValidationError
        from .toolkit import custom
        custom.validate_row(self, ValidationError)

    @property
    def env_name(self):
        return f"server_{self.name}"

    def save(self, *args, **kwargs):
        if not self.environment_yml:
            self.env_status = "none"
        elif self.env_status == "none":
            self.env_status = "pending"
        else:
            previous = CustomTool.objects.filter(pk=self.pk).values_list("environment_yml", flat=True).first() if self.pk else None
            if previous is not None and previous != self.environment_yml:
                self.env_status = "pending"   # the YAML changed: the built environment is out of date
        super().save(*args, **kwargs)


class EmailMessages(models.Model):
    """The e-mails users get: job finished, job failed, results about to be deleted. One row; edit it in the admin. Empty = the default text."""
    finished_subject = models.CharField(max_length=200, blank=True, help_text="Default: Job {job_id} Finished")
    finished_body = models.TextField(blank=True)
    failed_subject = models.CharField(max_length=200, blank=True, help_text="Default: Job {job_id} Failed")
    failed_body = models.TextField(blank=True)
    expiry_subject = models.CharField(max_length=200, blank=True, help_text="Default: Results of {job_name} will be deleted soon")
    expiry_body = models.TextField(blank=True)

    class Meta:
        verbose_name = "E-mail messages"
        verbose_name_plural = "E-mail messages (singleton)"

    def __str__(self):
        return "E-mail messages (edit the texts of the notifications)"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        from .email_templates import PLACEHOLDERS, unknown_placeholders
        errors = {}
        for kind in PLACEHOLDERS:
            for part in ('subject', 'body'):
                unknown = unknown_placeholders(kind, getattr(self, f'{kind}_{part}'))
                if unknown:
                    errors[f'{kind}_{part}'] = "Unknown placeholder: " + ', '.join('{%s}' % n for n in unknown) + ". Available: " + ', '.join('{%s}' % n for n in PLACEHOLDERS[kind])
        if errors:
            raise ValidationError(errors)


class EmailPolicy(models.Model):
    """Which e-mail addresses may be used for job notifications (and as the e-mail of an account). Optional: empty = any address.
    One row; edit it in the admin."""
    allowed_domain_patterns = models.TextField(
        blank=True,
        help_text="One regular expression per line, matched against the whole part after the @ (case-insensitive). "
                  "Leave empty to allow any address. Examples: 'example\\.org' (exactly that domain), '.*\\.example\\.org' (all its sub-domains), "
                  "'(example\\.org|example\\.de)' (two domains), '.*\\.edu' (any .edu address). Remember that '.' in a regular expression means any character: write '\\.' for a dot.")

    class Meta:
        verbose_name = "E-mail policy"
        verbose_name_plural = "E-mail policy (singleton)"

    def __str__(self):
        return "E-mail policy (edit this to restrict notification addresses)"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def clean(self):
        import re
        from django.core.exceptions import ValidationError
        for number, line in enumerate(self.patterns(), 1):
            try:
                re.compile(line)
            except re.error as error:
                raise ValidationError({"allowed_domain_patterns": f"Line {number} is not a valid regular expression: {error}"})

    def patterns(self):
        return [line.strip() for line in self.allowed_domain_patterns.splitlines() if line.strip()]


class SiteLimits(models.Model):
    """Fair-share limits on jobs that are queued or running at the same time. 0 = no limit. One row; edit it in the admin."""
    max_active_jobs_per_user = models.PositiveSmallIntegerField(default=0, help_text="Per logged-in user.")
    max_active_jobs_per_group = models.PositiveSmallIntegerField(default=0, help_text="Per user group (all members together).")
    max_active_jobs_anonymous = models.PositiveSmallIntegerField(default=0, help_text="All jobs submitted without logging in, together.")

    class Meta:
        verbose_name = "Job limits"
        verbose_name_plural = "Job limits (singleton)"

    def __str__(self):
        return "Job limits (0 = unlimited)"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class ApiToken(models.Model):
    """A key a user (or a script of theirs) sends as `Authorization: Bearer <key>` to the API. Only a hash of the key is stored."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=64, help_text="What the key is used for, e.g. 'pipeline on the cluster'.")
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    prefix = models.CharField(max_length=8, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @staticmethod
    def hash_key(key):
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()

    @classmethod
    def create_for(cls, user, name):
        """(token, plain key); the plain key is shown once and cannot be recovered."""
        import secrets
        key = "lm_" + secrets.token_urlsafe(32)
        return cls.objects.create(user=user, name=name, key_hash=cls.hash_key(key), prefix=key[:8]), key


def assign_group_from_ldap(user, ldap_user, **kwargs):
    """When LDAP login is on (LDAP_GROUP_ATTRIBUTE set): put the user into the group named by that LDAP attribute (e.g. department)."""
    attribute = getattr(settings, "LDAP_GROUP_ATTRIBUTE", "")
    values = ldap_user.attrs.get(attribute) if attribute else None
    if not values:
        return
    group, _ = LabGroup.objects.get_or_create(name=str(values[0]).strip()[:64])
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.group_id != group.pk:
        profile.group = group
        profile.save()


from django.contrib.auth.signals import user_logged_in


@receiver(user_logged_in)
def sync_group_from_ldap(sender, request, user, **kwargs):
    """django-auth-ldap attaches `ldap_user` to users that logged in through LDAP; take their group from it."""
    ldap_user = getattr(user, "ldap_user", None)
    if ldap_user is not None:
        assign_group_from_ldap(user, ldap_user)
