import json
import os
import shutil

from django.conf import settings
from django.shortcuts import render

from baclab.toolkit import Tool, cores, matching_file_in_dir
from baclab.toolkit.files import copy_output_to_downloads

STRAIN_FILES = {'public_myxo': 'public_myxo_16s.fasta', 'all_myxo': 'all_myxo_16s.fasta'}


def strain_options():
    """The extra strains the page offers to add to the tree: strain_options.json in the phylogeny database folder."""
    try:
        with open(os.path.join(settings.PHYLOGENY_DATABASE, 'strain_options.json'), 'r') as f:
            options = json.load(f).get('strain_options', [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        print(f"Error loading phylogeny strain options: {error}")
        return []
    validated = []
    for option in options:
        if not isinstance(option, dict):
            continue
        if 'value' not in option or 'label' not in option:
            print(f"Warning: Skipping phylogeny option with missing required fields: {option}")
            continue
        validated.append({'value': option['value'], 'label': option['label'], 'show_warning': option.get('show_warning', False)})
    return validated


def arguments(request):
    additional = request.POST.get('additional_strains', 'none')
    if additional == 'none':
        additional_file = 'none'
    else:
        additional_file = os.path.join(settings.PHYLOGENY_DATABASE, STRAIN_FILES.get(additional, f'{additional}.fasta'))
    return [request.POST.get('phylogeny_type', 'iqtree'), additional_file, cores()]


def post_process(ctx):
    downloads_dir = ctx['downloads_dir']
    copy_output_to_downloads(ctx['output_dir'], downloads_dir)
    shutil.rmtree(os.path.join(downloads_dir, 'tmp_input_with_additional'), ignore_errors=True)
    for file in os.listdir(downloads_dir):
        if file.endswith('.fasta'):
            try:
                os.remove(os.path.join(downloads_dir, file))
            except OSError:
                pass


def phylogeny_results(request, job_id, download_dir):
    phylogenetic_tree_file = matching_file_in_dir(download_dir, '*.treefile', '*.nwk')

    if not phylogenetic_tree_file:
        return None

    with open(phylogenetic_tree_file, 'r') as phylogenyfile:
        phylogenetic_tree_string = phylogenyfile.read().replace('\n', '')

    context = {
        'job_id': job_id,
        'phylogeneticTreeData': phylogenetic_tree_string,
    }
    return render(request, 'results_phylogeny.html', context)



def build_custom_database(tmpdirname, db_name):
    """Add a set of reference sequences an administrator uploaded to the strains the page offers."""
    os.makedirs(settings.PHYLOGENY_DATABASE, exist_ok=True)
    combined_fasta = os.path.join(settings.PHYLOGENY_DATABASE, f"{db_name}.fasta")
    with open(combined_fasta, "w") as outfile:
        for root, _, files in os.walk(tmpdirname):
            for f in files:
                if f.endswith((".fasta", ".fa", ".fna", ".faa")):
                    with open(os.path.join(root, f), "r") as infile:
                        outfile.write(infile.read())
                        outfile.write("\n")

    json_path = os.path.join(settings.PHYLOGENY_DATABASE, "strain_options.json")
    options = {"strain_options": []}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as jf:
                options = json.load(jf)
        except Exception:
            pass

    for opt in options.setdefault("strain_options", []):
        if opt.get("value") == db_name:
            opt["label"] = f"{db_name} (Custom)"
            break
    else:
        options["strain_options"].append({"value": db_name, "label": f"{db_name} (Custom)", "show_warning": False})
    with open(json_path, "w") as jf:
        json.dump(options, jf, indent=4)


tool = Tool(
    name='phylogeny',
    title='Phylogeny (MAFFT, IQ-TREE, FastTree)',
    category='compgen',
    args=arguments,
    post_process=post_process,
    results=phylogeny_results,
    page_context=lambda: {'strain_options': strain_options()},
    custom_database=build_custom_database,
    citation=[
        {
            'text': 'Katoh K, Standley DM. 2013. MAFFT multiple sequence alignment software version 7. Molecular Biology and Evolution 30(4):772-780.',
        },
        {
            'text': 'Nguyen LT, Schmidt HA, von Haeseler A, Minh BQ. 2015. IQ-TREE: a fast and effective stochastic algorithm for estimating maximum-likelihood phylogenies. Molecular Biology and Evolution 32(1):268-274.',
        },
    ],
    example=[('phylogeny_example.fasta', 'phylogeny_example.fasta')],

)
