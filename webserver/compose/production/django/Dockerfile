# Base image pinned to the one the released version was built and tested with (miniforge3, Ubuntu 24.04, 2026-08-31); a newer 'latest' could change
# compilers, conda or the solver and with them the environments below. Update it deliberately, then re-run `baclab selftest --run`.
FROM condaforge/miniforge3@sha256:c7af1b9e9a2877b1aa7604fd250f8ad311876f6f0f52849acbff0a7011508eb7

ENV LANG C.UTF-8

ENV PYTHONUNBUFFERED 1

RUN groupadd -r django &&\
    useradd -r -g django django &&\
    mkdir /home/django && chown -R django /home/django

# Requirements have to be pulled and installed here, otherwise caching won't work
COPY ./requirements /requirements
RUN pip install conda-merge==0.2.0 &&\
    conda-merge /requirements/base.yml /requirements/production.yml > /requirements/merged.yml &&\
    pip uninstall --yes conda-merge &&\
    mamba env update -n base -f /requirements/merged.yml &&\
    conda clean --all --yes &&\
    rm -rf /requirements

COPY --chown=django --chmod=755 ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint

COPY --chown=django --chmod=755 ./compose/production/django/start /start
RUN sed -i 's/\r//' /start

COPY --chown=django --chmod=755 ./compose/production/django/create_superuser /create_superuser
RUN sed -i 's/\r//' /create_superuser

COPY --chown=django --chmod=755 ./compose/production/django/celery/worker/start /start-celeryworker
RUN sed -i 's/\r//' /start-celeryworker

COPY --chown=django --chmod=755 ./compose/production/django/celery/beat/start /start-celerybeat
RUN sed -i 's/\r//' /start-celerybeat

COPY --chown=django --chmod=755 ./compose/production/django/celery/flower/start /start-flower
RUN sed -i 's/\r//' /start-flower

# Conda environments of the tools, as two layers so that a new tool does not rebuild the others:
#   conda_environments/        the older tools
#   tools/<name>/install/      the tools with their own folder (environment file + optional pre/post scripts, tools/README.md)
# Built as the django user; the build tools and wget that some post scripts need only exist while they run.
USER root
COPY --chmod=755 ./compose/install_envs.sh /install_envs.sh
COPY --chown=django ./conda_environments /tmp/envs_legacy
# /opt/conda belongs to root in the base image; the environments are built as the django user
RUN mkdir -p /opt/conda/envs /opt/conda/pkgs && chown django /opt/conda/envs /opt/conda/pkgs
RUN apt-get update && \
    apt-get install -y wget cmake build-essential time && \
    su django -c "PATH=$PATH /install_envs.sh /tmp/envs_legacy"
COPY --chown=django ./tools/*/install/ /tmp/envs_tools/
RUN su django -c "PATH=$PATH /install_envs.sh /tmp/envs_tools" && \
    rm /install_envs.sh
COPY --chown=django ./tools /app/tools
COPY --chown=django ./configure_tools.sh /tmp/configure_tools.sh
RUN su django -c "PATH=$PATH bash /tmp/configure_tools.sh" && \
    apt-get remove --purge -y wget cmake build-essential && \
    apt-get autoremove -y --purge && \
    apt-get clean && \
    rm /tmp/configure_tools.sh
USER django

# The application itself (the tools were copied above; compose/, requirements/ and the settings templates stay out of the image)
COPY --chown=django ./baclab /app/baclab
COPY --chown=django ./config /app/config
COPY --chown=django ./manage.py ./create_users.py ./benchmark_tools.py ./enabled_tools.csv ./VERSION /app/

RUN mkdir /app/staticfiles &&\
    mkdir /app/baclab/media &&\
    cd /app &&\
    CELERY_BROKER_URL=dummy\
    REDIS_URL=dummy DATABASE_URL=dummy DJANGO_SECRET_KEY=dummy DJANGO_ADMIN_URL=dummy\
    python /app/manage.py collectstatic --settings config.settings.production --noinput

# Optional LDAP login (--build-arg INSTALL_LDAP=1, or INSTALL_LDAP=1 in webserver/.env): see docs/ADMIN_GUIDE.md.
# Last in the file, so that switching it on or off never rebuilds the conda environments above.
ARG INSTALL_LDAP=0
USER root
RUN if [ "$INSTALL_LDAP" = "1" ]; then mamba install -y -n base -c conda-forge python-ldap && pip install django-auth-ldap==4.1.0 && conda clean --all --yes; fi
USER django

WORKDIR /app

ENTRYPOINT ["/entrypoint"]
