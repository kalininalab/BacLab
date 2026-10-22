from django.urls import path, include


from django.conf import settings
from . import account_views, api, chain_views, tool_views, views
from .toolkit import registry
from django.contrib import admin

app_name = 'baclab'
urlpatterns = [
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('guides/', views.guides, name='guides'),
    path('terms/', views.terms, name='terms'),

    path('results/', views.results, name='results'),
    path('qrcode/', views.qrcode, name='qrcode'),
    path('accounts/signup/', account_views.signup, name='signup'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('my-jobs/', account_views.my_jobs, name='my_jobs'),
    path('api/v1/tools/', api.tools, name='api_tools'),
    path('api/v1/jobs/', api.job_list, name='api_jobs'),
    path('api/v1/jobs/<str:job_id>/', api.job_status, name='api_job'),
    path('api/v1/jobs/<str:job_id>/download/', api.job_download, name='api_download'),
    path('api/v1/jobs/<str:tool_name>/submit/', api.create_job_view, name='api_submit'),
    path('my-jobs/api-keys/', account_views.api_keys, name='api_keys'),
    path('my-jobs/api-keys/<int:token_id>/delete/', account_views.api_key_delete, name='api_key_delete'),
    path('projects/<int:project_id>/', account_views.project_detail, name='project_detail'),
    path('projects/<int:project_id>/download/', account_views.project_download, name='project_download'),
    path('projects/<int:project_id>/delete/', account_views.project_delete, name='project_delete'),
    path('my-jobs/<str:job_id>/project/', account_views.set_project, name='set_project'),
    path('my-jobs/email/', account_views.set_email, name='set_email'),
    path('my-jobs/<str:job_id>/', account_views.job_detail, name='job_detail'),
    path('my-jobs/<str:job_id>/label/', account_views.set_label, name='set_label'),
    path('my-jobs/<str:job_id>/rerun/', chain_views.rerun, name='rerun'),
    path('my-jobs/<str:job_id>/send/', chain_views.send_to, name='send_to'),
    path('my-jobs/<str:job_id>/methods/', account_views.job_methods, name='job_methods'),
    path('my-jobs/<str:job_id>/private/', account_views.set_private, name='set_private'),
    path('my-jobs/<str:job_id>/retention/', account_views.set_retention, name='set_retention'),
    path('sample/', views.sample, name='sample'),
    path('strains/<str:strains_list>', views.strains, name='strains'),
    path('strains/collection/<slug:collection_slug>/', views.strain_collection, name='strain_collection'),
    path('faa_viewer/<str:strain>', views.faa_viewer, name='faa_viewer'),
    path('taxonomy/<str:strain>', views.taxonomy_viewer, name='taxonomy_viewer'),
    path('taxonomy_database/', views.taxonomy_database_viewer, name='taxonomy_database'),
    path('phylogenetic_tree/', views.phylogenetic_tree_viewer, name='phylogenetic_tree'),
    path('download/<str:file_type>/<str:strain_name>/', views.download_file, name='download_file'),
    path('job_progress/<str:job_id>/', views.job_progress, name='job_progress'),

    # Tools that describe themselves (tools/<name>/tool.py) and tools added in the admin
    path('custom/<slug:tool_name>/', tool_views.custom_tool, name='custom_tool'),
    path('example-data/<str:job_type>/', tool_views.download_example_data, name='download_example_data'),
    path('example-results/<str:job_type>/', tool_views.example_results, name='example_results'),
    path('report-file/<str:job_id>/<path:filepath>', tool_views.serve_tool_report_file, name='tool_report_file'),
]

# One page per tool folder (see tools/README.md), plus whatever extra URLs a tool defines
for tool in registry.builtin_tools():
    urlpatterns.append(path(f'{tool.name}/', tool_views.handle_job, {'job_type': tool.name}, name=tool.name))
    urlpatterns += tool.urls

if settings.LOCAL_MODE:
    urlpatterns += [
        path('databases/AntismashResults/<path:relpath>', views.serve_antismash_dev, name='antismash_dev'),
        path('data/downloads/<path:relpath>', views.serve_cblaster_dev, name='cblaster_dev'),
    ]
