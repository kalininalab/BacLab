import json
import os
import tempfile

from adminsortable2.admin import SortableAdminBase, SortableInlineAdminMixin
from django.conf import settings
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .email_templates import KINDS, PLACEHOLDERS, default_texts, send_samples
from .forms import InhouseStrainBulkUploadForm
from .inhouse_strain_bulk import bulk_create_inhouse_strains
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from .models import ApiToken, Project, SiteLimits, EmailPolicy, EmailMessages, LabGroup, UserProfile, CustomTool, ToolSetting, JobRecord, ServerBenchmark, InhouseStrain, InhouseStrainCollection, GlobalStrainResource, CustomDatabase, ThemeSettings, SitePage, PageSection
from .tasks import process_inhouse_strain, build_custom_database, build_custom_tool_environment

admin.site.site_header = "BacLab Administration"
admin.site.site_title = "BacLab Admin"
admin.site.index_title = "Pipelines & Resources"


STATUS_COLORS = {
    "queued": "#6c757d",
    "pending": "#6c757d",
    "running": "#fd7e14",
    "building": "#fd7e14",
    "finished": "#28a745",
    "completed": "#28a745",
    "ready": "#28a745",
    "failed": "#dc3545",
}


def render_status_badge(status):
    if not status:
        return "—"
    color = STATUS_COLORS.get(status, "#6c757d")
    label = status.replace("_", " ").title()
    return format_html(
        '<span style="background-color:{}; color:white; padding:2px 8px; '
        'border-radius:10px; font-size:11px; font-weight:600;">{}</span>',
        color, label,
    )


def render_error_summary(error_message):
    if not error_message:
        return "—"
    short = error_message if len(error_message) <= 60 else error_message[:57] + "..."
    return format_html('<span title="{}">{}</span>', error_message, short)


@admin.register(JobRecord)
class JobRecordAdmin(admin.ModelAdmin):
    list_display = ('job_id', 'job_type', 'status_badge', 'owner', 'group', 'email', 'queued_at', 'duration_display', 'error_summary')
    list_filter = ('status', 'job_type', 'group', 'queued_at')
    search_fields = ('job_id', 'job_type', 'email', 'owner__username', 'label')
    readonly_fields = ('job_id', 'queued_at', 'started_at', 'finished_at', 'duration_display')
    ordering = ('-queued_at',)
    date_hierarchy = 'queued_at'
    list_per_page = 50

    fieldsets = (
        ('Job Info', {'fields': ('job_id', 'job_type', 'status', 'label')}),
        ('Owner', {'fields': ('owner', 'group', 'retention_days', 'parameters')}),
        ('Timing', {'fields': ('queued_at', 'started_at', 'finished_at', 'duration_display')}),
        ('Notification', {'fields': ('email',)}),
        ('Errors', {'fields': ('error_message', 'error_log')}),
    )

    def duration_display(self, obj):
        if obj.duration:
            return str(obj.duration)
        return '—'
    duration_display.short_description = 'Duration'

    def status_badge(self, obj):
        return render_status_badge(obj.status)
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def error_summary(self, obj):
        return render_error_summary(obj.error_message)
    error_summary.short_description = 'Error'

    actions = ['mark_stuck_as_failed']

    @admin.action(description="Mark selected as failed (for jobs stuck queued/running)")
    def mark_stuck_as_failed(self, request, queryset):
        stuck = queryset.filter(status__in=['queued', 'running'])
        count = stuck.count()
        stuck.update(status='failed', error_message='Marked as failed manually via admin (job appeared stuck).')
        skipped = queryset.count() - count
        if skipped > 0:
            self.message_user(request, f"Marked {count} job(s) as failed. Skipped {skipped} already-finished job(s).", level='warning')
        else:
            self.message_user(request, f"Marked {count} job(s) as failed.", level='success')


@admin.register(InhouseStrain)
class InhouseStrainAdmin(admin.ModelAdmin):
    change_list_template = "admin/baclab/inhousestrain/change_list.html"
    list_display = (
        'strain_id', 'status_badge',
        'has_protein_output', 'has_antismash_output', 'has_taxonomy_output',
        'created_at', 'error_summary',
    )
    list_filter = ('status', 'created_at')
    search_fields = ('strain_id',)
    readonly_fields = ('status', 'taxonomy', 'error_message', 'created_at')
    date_hierarchy = 'created_at'
    list_per_page = 50

    fieldsets = (
        ('Strain', {'fields': ('strain_id', 'genome_fasta')}),
        ('Pipelines', {'fields': ('run_prokka', 'run_antismash', 'run_gtdbtk')}),
        ('Status', {'fields': ('status', 'taxonomy', 'created_at')}),
        ('Errors', {'fields': ('error_message', 'error_log')}),
    )

    def status_badge(self, obj):
        return render_status_badge(obj.status)
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def error_summary(self, obj):
        return render_error_summary(obj.error_message)
    error_summary.short_description = 'Error'

    def has_protein_output(self, obj):
        if not obj.run_prokka:
            return None
        return os.path.exists(os.path.join(settings.ANNOTATION_DB_PATH, f"{obj.strain_id}.faa"))
    has_protein_output.boolean = True
    has_protein_output.short_description = 'Prokka output'

    def has_antismash_output(self, obj):
        if not obj.run_antismash:
            return None
        return os.path.isdir(os.path.join(settings.ANTISMASH_DATA_PATH, obj.strain_id))
    has_antismash_output.boolean = True
    has_antismash_output.short_description = 'AntiSMASH output'

    def has_taxonomy_output(self, obj):
        if not obj.run_gtdbtk:
            return None
        return bool(obj.taxonomy)
    has_taxonomy_output.boolean = True
    has_taxonomy_output.short_description = 'Taxonomy output'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.status == "pending":
            transaction.on_commit(lambda: process_inhouse_strain.delay(obj.strain_id))

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('bulk-add/', self.admin_site.admin_view(self.bulk_add_view), name='baclab_inhousestrain_bulk_add'),
        ]
        return custom + urls

    def bulk_add_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied

        if request.method == 'POST':
            form = InhouseStrainBulkUploadForm(request.POST, request.FILES)
            if form.is_valid():
                with tempfile.TemporaryDirectory() as tmp:
                    zip_path = os.path.join(tmp, 'upload.zip')
                    with open(zip_path, 'wb') as f:
                        for chunk in form.cleaned_data['zip_file'].chunks():
                            f.write(chunk)
                    try:
                        results = bulk_create_inhouse_strains(
                            zip_path,
                            form.cleaned_data['run_prokka'],
                            form.cleaned_data['run_antismash'],
                            form.cleaned_data['run_gtdbtk'],
                        )
                    except ValueError as e:
                        self.message_user(request, f"Could not read archive: {e}", level='error')
                        return redirect('admin:baclab_inhousestrain_bulk_add')

                if results['created']:
                    self.message_user(
                        request,
                        f"Queued {len(results['created'])} new strain(s): {', '.join(results['created'])}",
                        level='success',
                    )
                if results['skipped_exists']:
                    self.message_user(
                        request,
                        f"Skipped {len(results['skipped_exists'])} strain(s) that already exist: {', '.join(results['skipped_exists'])}",
                        level='warning',
                    )
                if results['skipped_duplicate']:
                    self.message_user(
                        request,
                        f"Skipped {len(results['skipped_duplicate'])} duplicate strain name(s) within the zip: {', '.join(results['skipped_duplicate'])}",
                        level='warning',
                    )
                if results['invalid']:
                    detail = '; '.join(f"{name} ({reason})" for name, reason in results['invalid'])
                    self.message_user(request, f"Rejected {len(results['invalid'])} invalid file(s): {detail}", level='error')
                if results['ignored']:
                    self.message_user(
                        request,
                        f"Ignored {len(results['ignored'])} non-FASTA file(s) in the archive: {', '.join(results['ignored'])}",
                        level='info',
                    )
                if not any(results.values()):
                    self.message_user(request, "The archive did not contain any files.", level='warning')

                return redirect('admin:baclab_inhousestrain_changelist')
        else:
            form = InhouseStrainBulkUploadForm()

        context = dict(
            self.admin_site.each_context(request),
            form=form,
            opts=self.model._meta,
            title='Bulk add inhouse strains',
        )
        return render(request, 'admin/baclab/inhousestrain/bulk_add.html', context)

    actions = ['rerun_selected_strains', 'recheck_output_and_flag']

    @admin.action(description='Re-run selected strains (if input exists)')
    def rerun_selected_strains(self, request, queryset):
        count = 0
        skipped = 0
        for strain in queryset:
            if strain.genome_fasta and os.path.exists(strain.genome_fasta.path):
                strain.status = "pending"
                strain.save()
                # Use default arg in lambda to capture the current loop variable
                transaction.on_commit(lambda s_id=strain.strain_id: process_inhouse_strain.delay(s_id))
                count += 1
            else:
                skipped += 1

        if skipped > 0:
            self.message_user(request, f"Successfully re-queued {count} strains. Skipped {skipped} strains because their FASTA files no longer exist.", level='warning')
        else:
            self.message_user(request, f"Successfully re-queued {count} strains.", level='success')

    @admin.action(description='Re-check output files and flag mismatches as failed')
    def recheck_output_and_flag(self, request, queryset):
        flagged = 0
        for strain in queryset:
            problems = []
            if strain.run_prokka and not os.path.exists(os.path.join(settings.ANNOTATION_DB_PATH, f"{strain.strain_id}.faa")):
                problems.append("Prokka requested but no .faa output found")
            if strain.run_antismash and not os.path.isdir(os.path.join(settings.ANTISMASH_DATA_PATH, strain.strain_id)):
                problems.append("AntiSMASH requested but no output directory found")
            if strain.run_gtdbtk and not strain.taxonomy:
                problems.append("GTDB-Tk requested but no taxonomy classification recorded")
            if problems:
                strain.status = "failed"
                strain.error_message = "; ".join(problems)
                strain.save()
                flagged += 1

        if flagged:
            self.message_user(request, f"Flagged {flagged} strain(s) with missing output as failed.", level='warning')
        else:
            self.message_user(request, "No mismatches found — all selected strains have the output their requested pipelines should produce.", level='success')


@admin.register(InhouseStrainCollection)
class InhouseStrainCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'strain_count', 'created_at')
    search_fields = ('name',)
    filter_horizontal = ('strains',)
    prepopulated_fields = {'slug': ('name',)}

    def strain_count(self, obj):
        return obj.strains.count()
    strain_count.short_description = 'Strains'


@admin.register(GlobalStrainResource)
class GlobalStrainResourceAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'has_tree', 'has_taxonomy_db')

    def has_add_permission(self, request):
        return not GlobalStrainResource.objects.exists()

    def has_tree(self, obj):
        return bool(obj.phylogenetic_tree)
    has_tree.boolean = True
    has_tree.short_description = 'Tree uploaded'

    def has_taxonomy_db(self, obj):
        return bool(obj.taxonomy_db)
    has_taxonomy_db.boolean = True
    has_taxonomy_db.short_description = 'Taxonomy DB uploaded'


@admin.register(CustomDatabase)
class CustomDatabaseAdmin(admin.ModelAdmin):
    list_display = ('db_name', 'tool', 'status_badge', 'created_at', 'error_summary')
    list_filter = ('tool', 'status', 'created_at')
    search_fields = ('db_name',)
    readonly_fields = ('status', 'error_message', 'created_at')
    date_hierarchy = 'created_at'
    list_per_page = 50

    fieldsets = (
        ('Database', {'fields': ('db_name', 'tool', 'input_files')}),
        ('Status', {'fields': ('status', 'created_at')}),
        ('Errors', {'fields': ('error_message',)}),
    )

    def status_badge(self, obj):
        return render_status_badge(obj.status)
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def error_summary(self, obj):
        return render_error_summary(obj.error_message)
    error_summary.short_description = 'Error'

    def changelist_view(self, request, extra_context=None):
        from django.core.management import call_command
        try:
            call_command('sync_custom_dbs')
        except Exception:
            pass
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.status == "pending":
            transaction.on_commit(lambda: build_custom_database.delay(obj.id))

    actions = ['retry_selected_databases']

    @admin.action(description='Retry selected databases (if input exists)')
    def retry_selected_databases(self, request, queryset):
        count = 0
        skipped = 0
        for db in queryset:
            if db.input_files and os.path.exists(db.input_files.path):
                db.status = "pending"
                db.error_message = ""
                db.save()
                transaction.on_commit(lambda db_id=db.id: build_custom_database.delay(db_id))
                count += 1
            else:
                skipped += 1

        if skipped > 0:
            self.message_user(request, f"Successfully re-queued {count} database(s). Skipped {skipped} because their input files no longer exist.", level='warning')
        else:
            self.message_user(request, f"Successfully re-queued {count} database(s).", level='success')


class PageSectionInline(SortableInlineAdminMixin, admin.StackedInline):
    model = PageSection
    extra = 0
    fields = ('heading', 'body', 'is_published', 'order', 'preview')
    readonly_fields = ('preview',)

    class Media:
        js = ('admin/js/section_live_preview.js',)
        css = {'all': ('admin/css/section_live_preview.css',)}

    def preview(self, obj):
        content = mark_safe(obj.body) if obj and obj.pk else ''
        return format_html('<div class="section-live-preview">{}</div>', content)
    preview.short_description = 'Live preview'


@admin.register(SitePage)
class SitePageAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ('__str__', 'section_count', 'last_updated')
    inlines = [PageSectionInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def section_count(self, obj):
        return obj.sections.count()
    section_count.short_description = 'Sections'


@admin.register(ThemeSettings)
class ThemeSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'color_preview')

    def has_add_permission(self, request):
        return not ThemeSettings.objects.exists()

    def color_preview(self, obj):
        swatch = '<span style="display:inline-block;width:16px;height:16px;border:1px solid #ccc;margin-right:4px;vertical-align:middle;background:{}" title="{}"></span>'
        return format_html(
            swatch + swatch + swatch + swatch,
            obj.primary_color, 'Primary',
            obj.secondary_color, 'Secondary',
            obj.button_color, 'Button',
            obj.background_color, 'Background',
        )
    color_preview.short_description = 'Preview'


@admin.register(ServerBenchmark)
class ServerBenchmarkAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status', 'created_at', 'view_results')
    readonly_fields = ('status', 'view_results', 'results_json', 'created_at')
    date_hierarchy = 'created_at'

    def view_results(self, obj):
        if obj.status == "Running":
            status_text = "Initializing..."
            # the benchmark writes its progress next to the media files of the installation
            status_file = os.path.join(settings.MEDIA_ROOT, "benchmarks", str(obj.id), "current_status.txt")
            docker_status_file = f"/app/baclab/media/benchmarks/{obj.id}/current_status.txt"
            if os.path.exists(docker_status_file):
                with open(docker_status_file, "r") as sf:
                    status_text = sf.read().strip()
            elif os.path.exists(status_file):
                with open(status_file, "r") as sf:
                    status_text = sf.read().strip()

            return format_html(
                '<span style="color: orange;"><b>Running:</b> {}</span>'
                '<script>if(!window.__bacBenchRefresh){{window.__bacBenchRefresh = true; '
                'setTimeout(function(){{ window.location.reload(); }}, 5000);}}</script>',
                status_text,
            )

        if not obj.results_json:
            return "No Results"

        try:
            results = obj.results_json if isinstance(obj.results_json, list) else json.loads(obj.results_json)
            table = "<table style='width:100%; border: 1px solid #ddd; border-collapse: collapse;'>"
            table += "<tr style='background-color: #f2f2f2;'><th style='padding:8px; border: 1px solid #ddd;'>Tool</th><th style='padding:8px; border: 1px solid #ddd;'>Time (s)</th><th style='padding:8px; border: 1px solid #ddd;'>Peak RAM (MB)</th><th style='padding:8px; border: 1px solid #ddd;'>Status</th></tr>"
            for row in results:
                table += f"<tr><td style='padding:8px; border: 1px solid #ddd;'>{row.get('tool', '')}</td><td style='padding:8px; border: 1px solid #ddd;'>{row.get('time_s', 0):.2f}</td><td style='padding:8px; border: 1px solid #ddd;'>{row.get('ram_mb', 0):.2f}</td><td style='padding:8px; border: 1px solid #ddd;'>{row.get('status', '')}</td></tr>"
            table += "</table>"
            return format_html(table)
        except Exception as e:
            return str(e)

    view_results.short_description = "Benchmark Results Table"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            from .tasks import run_server_benchmark_task
            transaction.on_commit(lambda: run_server_benchmark_task.delay(obj.id))

    actions = ['run_new_benchmark']

    def run_new_benchmark(self, request, queryset):
        from .tasks import run_server_benchmark_task
        new_bench = ServerBenchmark.objects.create(status="Running")
        run_server_benchmark_task.delay(new_bench.id)
        self.message_user(request, "A new server benchmark has been initiated in the background.")
    run_new_benchmark.short_description = "Run New Server Benchmark (Background)"


@admin.register(ToolSetting)
class ToolSettingAdmin(admin.ModelAdmin):
    """Switch tools on or off without touching files. Without a row a tool follows enabled_tools.csv."""
    list_display = ('tool', 'enabled')
    list_editable = ('enabled',)
    search_fields = ('tool',)
    ordering = ('tool',)


@admin.register(CustomTool)
class CustomToolAdmin(admin.ModelAdmin):
    """Add a tool without programming: a bash script, an optional conda environment and how to show the results.
    The tool gets its own page, menu entry, job queue and results page. Scripts run on the server with the rights of the
    other tools, so only give this permission to administrators you trust."""
    list_display = ('title', 'name', 'category', 'enabled', 'env_badge', 'open_page', 'updated_at')
    list_filter = ('category', 'enabled', 'env_status')
    search_fields = ('name', 'title')
    readonly_fields = ('env_status', 'env_log', 'created_at', 'updated_at')
    actions = ['build_environment', 'enable_tools', 'disable_tools']

    fieldsets = (
        ('Tool', {'fields': ('name', 'title', 'category', 'description', 'enabled'),
                  'description': 'Steps: 1) describe the tool and its input, 2) write the script, 3) save, 4) build the environment (list view action) if you gave one, 5) tick enabled. Full guide: docs/ADMIN_GUIDE.md.'}),
        ('Input', {'fields': ('accepted_extensions', 'min_files', 'max_files', 'parameters')}),
        ('Script', {'fields': ('script', 'environment_yml', 'env_status', 'env_log', 'databases'),
                   'description': 'The script runs in bash with $INPUT_DIR, $OUTPUT_DIR, $CORES_PER_JOB, $DATABASES_DIR and $PARAM_&lt;NAME&gt;. Scripts run on the server: only trusted administrators should edit them.'}),
        ('Results', {'fields': ('result_kind', 'result_file', 'result_title', 'result_separator', 'keep_outputs')}),
        ('Citation', {'fields': ('citation_text', 'citation_url')}),
        ('Info', {'fields': ('created_at', 'updated_at')}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        return fields + ['name'] if obj else fields   # job ids and result folders are filed under the name

    def env_badge(self, obj):
        return render_status_badge(obj.env_status if obj.env_status != 'none' else None)
    env_badge.short_description = 'Environment'

    def open_page(self, obj):
        if not obj.pk:
            return '—'
        return format_html('<a href="{}">open</a>', reverse('baclab:custom_tool', args=[obj.name]))
    open_page.short_description = 'Page'

    @admin.action(description="Build the conda environment of the selected tools")
    def build_environment(self, request, queryset):
        started = 0
        for tool in queryset:
            if not tool.environment_yml:
                self.message_user(request, f"{tool.name}: no environment YAML defined.", level='warning')
                continue
            CustomTool.objects.filter(pk=tool.pk).update(env_status='building')
            transaction.on_commit(lambda pk=tool.pk: build_custom_tool_environment.delay(pk))
            started += 1
        if started:
            self.message_user(request, f"Building {started} environment(s) in the background; reload this page to follow the status "
                                       "(it can take several minutes).", level='success')

    @admin.action(description="Show the selected tools to users")
    def enable_tools(self, request, queryset):
        blocked = queryset.filter(env_status__in=['pending', 'building', 'failed'])
        for tool in blocked:
            self.message_user(request, f"{tool.name}: the environment is not ready ({tool.env_status}); not enabled.", level='warning')
        queryset.exclude(pk__in=blocked.values('pk')).update(enabled=True, updated_at=timezone.now())

    @admin.action(description="Hide the selected tools from users")
    def disable_tools(self, request, queryset):
        queryset.update(enabled=False, updated_at=timezone.now())


def system_status(request):
    """Admin page: version, tools (with switches and missing databases) and the database installation state."""
    from . import db_status, tool_catalog
    from .toolkit import registry

    enabled = tool_catalog.enabled_map()
    tools = []
    for tool in registry.all_tools():
        on = tool.admin_enabled if tool.source == 'custom' else tool_catalog.is_enabled(tool.settings_key, enabled)
        tools.append({'title': tool.title, 'kind': 'custom (admin)' if tool.source == 'custom' else 'tool folder', 'enabled': on,
                      'missing': db_status.missing_for_tool(tool), 'url': tool.url})
    from . import monitoring
    queue = monitoring.queue_report()
    context = dict(admin.site.each_context(request), title='System status', version=settings.BACLAB_VERSION, tools=tools,
                   disks=[dict(d, used_h=monitoring.human(d['used']), total_h=monitoring.human(d['total']), free_h=monitoring.human(d['free'])) for d in monitoring.disk_report()],
                   queue=queue,
                   databases=db_status.overview(with_size=request.GET.get('size') == '1'), databases_dir=settings.DATABASES_DIR)
    return render(request, 'admin/system_status.html', context)


_original_get_urls = admin.site.get_urls


def _get_urls_with_status():
    return [path('system-status/', admin.site.admin_view(system_status), name='system_status')] + _original_get_urls()


admin.site.get_urls = _get_urls_with_status


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Group (members of a group see each other's jobs)"


class LabUserAdmin(UserAdmin):
    """The standard user admin plus the user's group. Accounts are optional: nobody needs one to use the tools."""
    inlines = [UserProfileInline]
    list_display = UserAdmin.list_display + ('user_group',)

    def save_formset(self, request, form, formset, change):
        """A profile is created automatically with every new user, so on "add user" the inline must update it
        instead of inserting a second one (which the database refuses)."""
        if formset.model is UserProfile and not change:
            data = formset.forms[0].cleaned_data if formset.forms and formset.forms[0].is_valid() else {}
            profile, _ = UserProfile.objects.get_or_create(user=form.instance)
            profile.group = data.get('group')
            profile.save()
            formset.new_objects, formset.changed_objects, formset.deleted_objects = [], [], []   # what the admin log reads
            return
        super().save_formset(request, form, formset, change)

    def user_group(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.group if profile and profile.group else '—'
    user_group.short_description = 'Group'


admin.site.unregister(get_user_model())
admin.site.register(get_user_model(), LabUserAdmin)


@admin.register(LabGroup)
class LabGroupAdmin(admin.ModelAdmin):
    """Groups (labs, departments, classes). Put users into a group on their user page."""
    list_display = ('name', 'member_count')
    search_fields = ('name',)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


@admin.register(EmailPolicy)
class EmailPolicyAdmin(admin.ModelAdmin):
    """Optional: limit which e-mail addresses can be used for job notifications. Empty = any address."""
    def has_add_permission(self, request):
        return not EmailPolicy.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class EmailMessagesForm(forms.ModelForm):
    restore_defaults = forms.BooleanField(required=False, label="Restore the default texts",
                                          help_text="Tick and save to replace all subjects and texts above by the defaults that BacLab ships with.")
    send_test_to = forms.EmailField(required=False, label="Send a test to",
                                    help_text="Optional: after saving, one sample of each message (with the texts above) is sent to this address, so you can see what users get.")

    class Meta:
        model = EmailMessages
        fields = '__all__'


@admin.register(EmailMessages)
class EmailMessagesAdmin(admin.ModelAdmin):
    """The texts of the e-mails users get. Placeholders in {curly brackets}; empty text = default."""
    form = EmailMessagesForm
    fieldsets = tuple(
        (label, {'fields': (f'{kind}_subject', f'{kind}_body'),
                 'description': 'Placeholders: ' + '; '.join('<code>{%s}</code> %s' % (n, d) for n, d in PLACEHOLDERS[kind].items())})
        for kind, label in KINDS.items()
    ) + (('Defaults and test', {'fields': ('restore_defaults', 'send_test_to')}),)

    def get_changeform_initial_data(self, request):
        return default_texts()

    def changelist_view(self, request, extra_context=None):
        row = EmailMessages.objects.first()       # one row only: go straight to it
        if row is not None:
            return redirect(reverse('admin:baclab_emailmessages_change', args=[row.pk]))
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return not EmailMessages.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get('restore_defaults'):
            for field, text in default_texts().items():
                setattr(obj, field, text)
            self.message_user(request, "The default texts were restored.", level=messages.SUCCESS)
        super().save_model(request, obj, form, change)
        address = form.cleaned_data.get('send_test_to')
        if not address:
            return
        backend = settings.EMAIL_BACKEND.rsplit('.', 2)[-2]
        try:
            count = send_samples(address)
        except Exception as error:
            self.message_user(request, f"The test e-mail could not be sent ({backend} backend): {error}", level=messages.ERROR)
            return
        where = "written to the server log (local mode: no mail server is used)" if backend == 'console' else f"sent to {address}"
        self.message_user(request, f"{count} test messages {where}.", level=messages.SUCCESS)


@admin.register(SiteLimits)
class SiteLimitsAdmin(admin.ModelAdmin):
    """Fair-share limits on jobs that wait or run at the same time. 0 = no limit."""
    def has_add_permission(self, request):
        return not SiteLimits.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    search_fields = ('name', 'owner__username')


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """API keys are created by the users themselves (my jobs -> API keys); here an administrator can see and revoke them."""
    list_display = ('name', 'user', 'prefix', 'created_at', 'last_used')
    readonly_fields = ('user', 'name', 'prefix', 'created_at', 'last_used')

    def has_add_permission(self, request):
        return False


def usage_report(request):
    """Admin page: jobs and compute time per user, group and tool for a month (CSV with ?format=csv)."""
    import csv
    from collections import defaultdict
    from datetime import datetime
    from django.http import HttpResponse
    from .models import JobRecord

    today = timezone.now()
    month = request.GET.get('month') or today.strftime('%Y-%m')
    try:
        start = datetime.strptime(month, '%Y-%m').replace(tzinfo=today.tzinfo)
    except ValueError:
        month, start = today.strftime('%Y-%m'), today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))
    jobs = JobRecord.objects.filter(queued_at__gte=start, queued_at__lt=end).select_related('owner', 'group')

    def table(key):
        rows = defaultdict(lambda: {'jobs': 0, 'failed': 0, 'seconds': 0.0})
        for job in jobs:
            row = rows[key(job)]
            row['jobs'] += 1
            row['failed'] += job.status == 'failed'
            row['seconds'] += job.duration.total_seconds() if job.duration else 0
        return [{'name': name, 'jobs': r['jobs'], 'failed': r['failed'], 'wall_hours': round(r['seconds'] / 3600, 2),
                 'cpu_hours': round(r['seconds'] / 3600 * settings.CORES_PER_JOB, 1)} for name, r in sorted(rows.items(), key=lambda i: -i[1]['seconds'])]

    tables = [('By user', table(lambda j: j.owner.username if j.owner else '(anonymous)')),
              ('By group', table(lambda j: j.group.name if j.group else '(no group)')),
              ('By tool', table(lambda j: j.tool_label))]
    if request.GET.get('format') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="baclab-usage-{month}.csv"'
        writer = csv.writer(response)
        writer.writerow(['view', 'name', 'jobs', 'failed', 'wall_hours', 'cpu_hours_estimate'])
        for title, rows in tables:
            for r in rows:
                writer.writerow([title, r['name'], r['jobs'], r['failed'], r['wall_hours'], r['cpu_hours']])
        return response
    return render(request, 'admin/usage.html', dict(admin.site.each_context(request), title='Usage', month=month, tables=tables,
                                                    cores=settings.CORES_PER_JOB, total_jobs=jobs.count()))


_status_get_urls = admin.site.get_urls


def _get_urls_with_usage():
    return [path('usage/', admin.site.admin_view(usage_report), name='usage')] + _status_get_urls()


admin.site.get_urls = _get_urls_with_usage


def live_monitor(request):
    """Admin page: CPU, memory, GPU, disks and running jobs, refreshed every few seconds."""
    return render(request, 'admin/monitor.html', dict(admin.site.each_context(request), title='Live monitor', cpu_count=os.cpu_count()))


def live_monitor_data(request):
    from django.http import JsonResponse
    from . import monitoring
    return JsonResponse(monitoring.snapshot(include_queue=request.GET.get('queue') == '1'))


_usage_get_urls = admin.site.get_urls


def _get_urls_with_monitor():
    return [path('monitor/', admin.site.admin_view(live_monitor), name='monitor'),
            path('monitor/data/', admin.site.admin_view(live_monitor_data), name='monitor_data')] + _usage_get_urls()


admin.site.get_urls = _get_urls_with_monitor
