"""Tools added in the admin (models.CustomTool) become ordinary toolkit Tools here.

What an administrator writes is a bash script. For every job it is wrapped like this and run by the
Celery worker (as the same user as every other tool):

    bash <wrapper> <input dir> <output dir> <cores> <parameter values...>

so the script sees $INPUT_DIR, $OUTPUT_DIR, $CORES_PER_JOB, $DATABASES_DIR and $PARAM_<NAME>, inside the
conda environment built from the optional environment YAML.
"""
import json
import os
import re

from django.conf import settings

from .files import run_command
from .forms import genome_form
from .helpers import choice, cores
from .menu import CATEGORY_KEYS
from .results import html_results, table_results
from .tool import Tool

NAME_PATTERN = re.compile(r'^[a-z][a-z0-9]{1,23}$')
PARAM_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]{0,19}$')
EXTENSION_PATTERN = re.compile(r'^\.[A-Za-z0-9][A-Za-z0-9.]{0,9}$')
SEPARATORS = {'tab': '\t', ',': ',', ';': ';', '|': '|'}
MAX_FILES_LIMIT = 100


def split_list(text):
    return [item.strip() for item in (text or '').split(',') if item.strip()]


def parse_parameters(text):
    """The parameters JSON of a CustomTool as a normalised list; raises ValueError with a readable message."""
    if not (text or '').strip():
        return []
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f'The parameters are not valid JSON: {error}')
    if not isinstance(raw, list):
        raise ValueError('The parameters must be a JSON list.')
    parameters, seen = [], set()
    for index, item in enumerate(raw, 1):
        where = f'Parameter {index}'
        if not isinstance(item, dict):
            raise ValueError(f'{where} must be an object.')
        name = item.get('name', '')
        if not PARAM_NAME_PATTERN.match(str(name)):
            raise ValueError(f'{where}: "name" must be lowercase letters, digits or _ (starting with a letter).')
        if name in seen:
            raise ValueError(f'{where}: the name "{name}" is used twice.')
        seen.add(name)
        kind = item.get('type', 'choice')
        if kind not in ('choice', 'int', 'bool'):
            raise ValueError(f'{where} ({name}): "type" must be choice, int or bool.')
        parameter = {'name': name, 'label': str(item.get('label') or name), 'type': kind}
        if kind == 'choice':
            choices = [str(c) for c in item.get('choices', [])]
            if not choices or any(not re.match(r'^[A-Za-z0-9._+-]{1,40}$', c) for c in choices):
                raise ValueError(f'{where} ({name}): "choices" must be a list of simple values (letters, digits, . _ + -).')
            default = str(item.get('default', choices[0]))
            if default not in choices:
                raise ValueError(f'{where} ({name}): the default is not one of the choices.')
            parameter.update(choices=choices, default=default)
        elif kind == 'int':
            try:
                low, high = int(item.get('min', 0)), int(item.get('max', 100))
                default = int(item.get('default', low))
            except (TypeError, ValueError):
                raise ValueError(f'{where} ({name}): min, max and default must be whole numbers.')
            if not low <= default <= high:
                raise ValueError(f'{where} ({name}): the default must lie between min and max.')
            parameter.update(min=low, max=high, default=default)
        else:
            parameter['default'] = bool(item.get('default', False))
        parameters.append(parameter)
    return parameters


def validate_row(row, ValidationError):
    """Checks a CustomTool before it is saved (CustomTool.clean calls this)."""
    from . import registry
    from ..models import CustomTool

    errors = {}
    row.name = (row.name or '').strip().lower()
    if not NAME_PATTERN.match(row.name):
        errors['name'] = 'Use 2-24 lowercase letters and digits, starting with a letter.'
    elif row.pk and CustomTool.objects.filter(pk=row.pk).exclude(name=row.name).exists():
        errors['name'] = 'The name of an existing tool cannot be changed (its jobs and results are filed under it).'
    elif row.name in registry.reserved_names() or row.name in {tool.name for tool in registry.builtin_tools()}:
        errors['name'] = 'This name is used by another tool or page of the platform.'

    if row.category not in CATEGORY_KEYS:
        errors['category'] = 'Unknown category.'

    extensions = split_list(row.accepted_extensions)
    if not extensions or any(not EXTENSION_PATTERN.match(e) for e in extensions):
        errors['accepted_extensions'] = 'Give one or more extensions starting with a dot, separated by commas (e.g. .fasta,.fa).'
    else:
        row.accepted_extensions = ','.join(e.lower() for e in extensions)

    if not 1 <= (row.min_files or 0) <= MAX_FILES_LIMIT:
        errors['min_files'] = f'Between 1 and {MAX_FILES_LIMIT}.'
    elif not row.min_files <= (row.max_files or 0) <= MAX_FILES_LIMIT:
        errors['max_files'] = f'Between the minimum and {MAX_FILES_LIMIT}.'

    row.script = (row.script or '').replace('\r\n', '\n').strip() + '\n'
    if not row.script.strip():
        errors['script'] = 'The script cannot be empty.'
    row.environment_yml = (row.environment_yml or '').replace('\r\n', '\n').strip()
    if row.environment_yml and 'dependencies' not in row.environment_yml:
        errors['environment_yml'] = 'This does not look like a conda environment file (no "dependencies:").'

    try:
        parse_parameters(row.parameters)
    except ValueError as error:
        errors['parameters'] = str(error)

    if row.result_kind in ('table', 'html') and not (row.result_file or '').strip():
        errors['result_file'] = 'Name the file (or pattern) to show for this result type.'
    if (row.result_file or '').startswith('/') or '..' in (row.result_file or ''):
        errors['result_file'] = 'Use a path relative to the output folder.'
    if row.result_separator not in SEPARATORS:
        errors['result_separator'] = "Use 'tab', ',', ';' or '|'."
    for entry in split_list(row.keep_outputs):
        if entry.startswith('/') or '..' in entry:
            errors['keep_outputs'] = 'Use paths relative to the output folder.'
    for folder in split_list(row.databases):
        if not re.match(r'^[A-Za-z0-9._-]+$', folder):
            errors['databases'] = 'Folder names only (letters, digits, . _ -).'

    if errors:
        raise ValidationError(errors)


# ---- the wrapper script and the environment ----
def env_prefix(name):
    """Where the conda environment of a custom tool lives: on the persistent data volume, so it survives image updates."""
    return os.path.join(settings.CUSTOM_ENVS_DIR, f'server_{name}')


def wrapper_script(name, script, has_environment, parameters):
    """The bash file that is run for a job: arguments -> variables, environment, then the administrator's script."""
    lines = [
        '#!/bin/bash',
        'set -e',
        'INPUT_DIR="$1"',
        'OUTPUT_DIR="$2"',
        'CORES_PER_JOB="${3:-1}"',
        f'export DATABASES_DIR="{settings.DATABASES_DIR}"',
        'export INPUT_DIR OUTPUT_DIR CORES_PER_JOB',
    ]
    for position, parameter in enumerate(parameters, 4):
        lines.append(f'export PARAM_{parameter["name"].upper()}="${{{position}}}"')
    if has_environment:
        lines += ['eval "$(conda shell.bash hook)"', f'conda activate --no-stack "{env_prefix(name)}"']
    lines += ['cd "$OUTPUT_DIR"', '', script]
    return '\n'.join(lines) + '\n'


def parameter_arguments(parameters, post):
    """The values of the parameters as script arguments, taken from the submitted form and checked against the definition."""
    values = []
    for parameter in parameters:
        raw = post.get(f'param_{parameter["name"]}')
        if parameter['type'] == 'choice':
            values.append(choice(raw, parameter['choices'], parameter['default']))
        elif parameter['type'] == 'int':
            try:
                number = int(raw)
            except (TypeError, ValueError):
                number = parameter['default']
            values.append(str(min(max(number, parameter['min']), parameter['max'])))
        else:
            values.append('yes' if raw in ('on', 'true', 'yes', '1') else 'no')
    return values


def files_results(request, job_id, download_dir):
    """Results page of a tool without a table/report: the list of files in the download."""
    from django.shortcuts import render
    from .results import citation_for
    listing = []
    for root, _, files in os.walk(download_dir):
        for file in sorted(files):
            path = os.path.join(root, file)
            listing.append({'name': os.path.relpath(path, download_dir), 'size': os.path.getsize(path)})
    if not [item for item in listing if not item['name'].startswith('input' + os.sep)]:
        return None
    return render(request, 'results_custom_files.html', {'job_id': job_id, 'files': sorted(listing, key=lambda item: item['name']), 'citation': citation_for(job_id)})


def build_tool(row):
    """The toolkit Tool for a CustomTool row."""
    parameters = parse_parameters(row.parameters)
    extensions = tuple(split_list(row.accepted_extensions))
    name, script, has_env = row.name, row.script, bool(row.environment_yml)
    keep = split_list(row.keep_outputs)

    def run(ctx):
        # Written here (not when the row is saved) so every worker has the current version, whatever it cached.
        folder = os.path.join(settings.CUSTOM_TOOLS_DIR, name)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f'{name}_script.sh')
        with open(path, 'w') as handle:
            handle.write(wrapper_script(name, script, has_env, parameters))
        run_command(['bash', path] + ctx['command'][1:], ctx['output_dir'])

    if row.result_kind == 'table':
        results = table_results(row.result_file.strip(), row.result_title or row.title, sep=SEPARATORS[row.result_separator], table_id=f'{name}ResultsTable')
    elif row.result_kind == 'html':
        results = html_results(row.result_file.strip(), row.result_title or row.title)
    else:
        results = files_results
    if row.result_kind != 'files':
        fallback = files_results
        shown = results
        results = lambda request, job_id, download_dir: shown(request, job_id, download_dir) or fallback(request, job_id, download_dir)

    tool = Tool(
        name=name,
        title=row.title,
        category=row.category,
        description=row.description,
        form=genome_form(extensions, min_files=row.min_files, max_files=row.max_files),
        args=lambda request: [cores()] + parameter_arguments(parameters, request.POST),
        run=run,
        outputs=keep or None,
        results=results,
        citation=[{'text': row.citation_text, 'url': row.citation_url}] if row.citation_text else [],
        page_context=lambda: {'parameters': parameters, 'accepted_extensions': extensions, 'min_files': row.min_files,
                              'max_files': row.max_files, 'description': row.description},
        databases=split_list(row.databases),
        template='custom_tool.html',
        source='custom',
    )
    tool.directory = os.path.join(settings.CUSTOM_TOOLS_DIR, name)
    tool.script = f'{name}_script.sh'
    tool.admin_enabled = row.enabled
    return tool
