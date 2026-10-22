#!/bin/bash
# Builds the conda environments of the tools: one `mamba env create` for every server_<env>.yml in the given folder.
# Next to an environment file there may be
#   server_<env>.pre.sh    sourced before the environment is created (e.g. to export variables the package install scripts read)
#   server_<env>.post.sh   run (with bash) after it is created: extra installs, installs from source, configuration
# The Dockerfiles call this twice - for conda_environments/ (the older tools) and for tools/*/install/ (the tools with their
# own folder, see tools/README.md) - as two image layers, so adding a tool does not rebuild the environments of the others.
#
# Usage: install_envs.sh <folder with server_*.yml files>
set -e

ENV_DIR=${1:?usage: install_envs.sh <folder with server_*.yml files>}

for yml in "$ENV_DIR"/server_*.yml; do
    [ -f "$yml" ] || continue
    env=$(basename "$yml" .yml)
    echo "=== Building conda environment $env"
    if [ -f "$ENV_DIR/$env.pre.sh" ]; then
        source "$ENV_DIR/$env.pre.sh"
    fi
    mamba env create --yes -n "$env" -f "$yml" < /dev/null
    if [ -f "$ENV_DIR/$env.post.sh" ]; then
        bash "$ENV_DIR/$env.post.sh"
    fi
done

conda clean --all --force-pkgs-dirs --yes
rm -rf "$ENV_DIR"
