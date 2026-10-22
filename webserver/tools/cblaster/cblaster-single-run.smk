# snakemake -s cblaster-single-run.smk --configfile cblaster-single-run.yml --cores 8 --use-conda

import os


path_output = config['path_output']


def get_search_options(kwargs):
    res = ' '.join(f'--{k} \"{v}\"' for k, v in kwargs.items())
    return res


onsuccess:
    shell("cp -v \"{log}\" \"{path_output}\"/logs/snakemake.log")

onerror:
    shell("cp -v \"{log}\" \"{path_output}\"/logs/snakemake.log")


rule all:
    input: os.path.join(path_output, 'results', 'plot_clusters.html')


rule cblaster_search:
    input:
        query = config['query_file']
    conda: 'server_cblaster'
    output:
        session = os.path.join(path_output, 'results', 'session.json'),
        summary = os.path.join(path_output, 'results', 'summary.txt'),
        plot = os.path.join(path_output, 'results', 'plot.html'),
        blasthits = os.path.join(path_output, 'results', 'blasthits.txt'),
        binary = os.path.join(path_output, 'results', 'binary.txt'),
    retries: config.get('retries', 0)
    resources:
        rule_log = lambda wildcards, attempt: os.path.join(path_output, 'logs', f'cblaster-search.{attempt}.log'),
    params:
        # ipg is only generated in the remote mode so i cannot place this one in the outputs
        ipg = os.path.join(path_output, 'results', 'ipg.txt'),
        cmd_options = get_search_options(config['search_kwargs'])
    threads: config.get('num_threads', workflow.cores)
    benchmark:
        os.path.join(path_output, 'logs', 'cblaster-search.benchmark.txt')
    shell:
        """
        cblaster search \
            --mode {config[mode]:q} \
            --database {config[database]:q} \
            --query_file {input.query:q} \
            --cpus {threads:q} \
            --session_file {output.session:q} \
            --output {output.summary:q} \
            --plot {output.plot:q} \
            --blast_file {output.blasthits:q} \
            --ipg_file {params.ipg:q} \
            --binary {output.binary:q} \
            --sort_clusters \
            {params.cmd_options} \
        &> "{resources.rule_log}"
        """


rule cblaster_intermediate_search:
    input: os.path.join(path_output, 'results', 'session.json')
    output: os.path.join(path_output, 'results', 'session-intermediate.json')
    conda: 'server_cblaster'
    retries: config.get('retries', 0)
    resources:
        rule_log = lambda wildcards, attempt: os.path.join(path_output, 'logs', f'cblaster-intermediate-search.{attempt}.log'),
    benchmark:
        os.path.join(path_output, 'logs', 'cblaster-intermediate-search.benchmark.txt')
    shell:
        """
        sed -i 's/\\.dmnd/\\.sqlite3/g' {input:q}
        cblaster search \
            --session_file {input:q} \
            --recompute {output:q} \
            --intermediate_genes \
            -md {config[intermediate_kwargs][max_distance]:q} \
            -mic {config[intermediate_kwargs][max_clusters]:q} \
        &> "{resources.rule_log}" || cp {input:q} {output:q}
        """


def get_plot_clusters_input(wildcards):
    if config.get('search_intermediate', False):
        return os.path.join(path_output, 'results', 'session-intermediate.json')
    return os.path.join(path_output, 'results', 'session.json')


rule cblaster_plot_clusters:
    input: get_plot_clusters_input
    output: os.path.join(path_output, 'results', 'plot_clusters.html')
    conda: 'server_cblaster'
    shell:
        """
        cblaster plot_clusters {input:q} -o {output:q}
        """
