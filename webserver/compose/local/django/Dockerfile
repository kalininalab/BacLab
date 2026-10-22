# Base image pinned to the one the released version was built and tested with (miniforge3, Ubuntu 24.04, 2026-08-31); a newer 'latest' could change
# compilers, conda or the solver and with them the environments below. Update it deliberately, then re-run `baclab selftest --run`.
FROM condaforge/miniforge3@sha256:c7af1b9e9a2877b1aa7604fd250f8ad311876f6f0f52849acbff0a7011508eb7

ENV LANG C.UTF-8

ENV PYTHONUNBUFFERED 1

# install pkill for celery autoreload
# build stuff and wget for nerpa
# time for benchmark_tools.py's peak-RAM measurement (/usr/bin/time -v)
RUN apt-get update && apt-get install -y procps wget cmake build-essential libgomp1 time && apt-get clean

COPY ./requirements /requirements
RUN pip install conda-merge==0.2.0 &&\
    conda-merge /requirements/base.yml /requirements/local.yml > /requirements/merged.yml &&\
    pip uninstall --yes conda-merge &&\
    mamba env update -n base -f /requirements/merged.yml &&\
    conda clean --all --yes &&\
    rm -rf /requirements

COPY --chmod=755 ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint

COPY --chmod=755 ./compose/local/django/start /start
RUN sed -i 's/\r//' /start

COPY --chmod=755 ./compose/production/django/create_superuser /create_superuser
RUN sed -i 's/\r//' /create_superuser

COPY --chmod=755 ./compose/local/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r//' /start-celeryworker

COPY --chmod=755 ./compose/local/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r//' /start-celerybeat

COPY --chmod=755 ./compose/local/django/celery/flower/start /start-flower
RUN sed -i 's/\r//' /start-flower

# Conda environments of the tools, as two layers so that a new tool does not rebuild the others
# (see the production Dockerfile and tools/README.md)
COPY --chmod=755 ./compose/install_envs.sh /install_envs.sh
COPY ./conda_environments /tmp/envs_legacy
RUN /install_envs.sh /tmp/envs_legacy
COPY ./tools/*/install/ /tmp/envs_tools/
RUN /install_envs.sh /tmp/envs_tools && rm /install_envs.sh

COPY ./tools /app/tools
COPY ./configure_tools.sh /tmp/configure_tools.sh
RUN bash /tmp/configure_tools.sh && rm /tmp/configure_tools.sh

# Optional LDAP login (--build-arg INSTALL_LDAP=1, or INSTALL_LDAP=1 in webserver/.env): see docs/ADMIN_GUIDE.md.
# Last in the file, so that switching it on or off never rebuilds the conda environments above.
ARG INSTALL_LDAP=0
RUN if [ "$INSTALL_LDAP" = "1" ]; then mamba install -y -n base -c conda-forge python-ldap && pip install django-auth-ldap==4.1.0 && conda clean --all --yes; fi

WORKDIR /app

ENTRYPOINT ["/entrypoint"]
