# Development

* Adding a tool: see "Adding a tool" in the {doc}`tools reference <tools>` and the scaffold `webserver/tools/new_tool.sh`.
* Tests: `python manage.py test baclab` (in the `webserver` folder, or inside the django container).
* Example data and where it comes from: below.

```{include} ../webserver/baclab/example_data/README.md
```

## Pinned versions
Nothing is left to "latest": every package in the conda environment files (`webserver/conda_environments/`, `webserver/tools/*/install/`) has an exact version, the
base images are pinned by digest (`FROM condaforge/miniforge3@sha256:...`, nginx), redis and PostgreSQL by tag, and the sources some tools are built from by commit.
`webserver/locks/<environment>.txt` records everything installed in each environment of the tested image (`name=version=build`), including the packages that are only
pulled in as dependencies. To update a tool deliberately: change its version in the environment file, rebuild, run `./baclab selftest --run`, and refresh the lock file
(`conda list -n <env> --export` inside the container).
