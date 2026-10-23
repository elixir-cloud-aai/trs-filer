##### BASE IMAGE #####
## Pinned by digest, so that rebuilds (e.g., of a release) use the same base
## image; Dependabot updates the tag and digest together
## (`.github/dependabot.yml`)
## TEMPORARY: FOCA's development image built from the commit that
## `pyproject.toml` pins (#88), replaced by the release image
## (`elixircloud/foca:0.17.0-py3.13`) before the next release
## (`scripts/check_release_pins.py`); dated tags move with later commits of
## the day, so only the digest identifies the image
## FOCA commit: 29af8a64a2b0aae21845fa37a4a54076811f62bf
FROM elixircloud/foca:20261023-py3.13@sha256:1e1275f77be3a256449dc8739410f32b0d0376534b824d8b746d5316d27cdb1f

##### METADATA #####
## OCI annotations; images built from the FOCA image inherit its own, so all
## static ones are set here
LABEL org.opencontainers.image.title="TRS-Filer"
LABEL org.opencontainers.image.description="GA4GH Tool Registry Service (TRS) implementation by ELIXIR On-Cloud"
LABEL org.opencontainers.image.url="https://github.com/elixir-cloud-aai/trs-filer"
LABEL org.opencontainers.image.source="https://github.com/elixir-cloud-aai/trs-filer"
LABEL org.opencontainers.image.documentation="https://github.com/elixir-cloud-aai/trs-filer#readme"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.authors="ELIXIR On-Cloud <cloud-service@elixir-europe.org>"
LABEL org.opencontainers.image.vendor="ELIXIR On-Cloud"

## TEMPORARY: the Helm chart's config Job runs `update-config-map.sh` in this
## image, which needs `curl`, `jq` and `yq`; FOCA's images ship none of them,
## and `yq` is no dependency of the app. Removed with the config Job (#135)
USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl jq \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --no-cache-dir yq==3.4.3
COPY update-config-map.sh /app/update-config-map.sh

## Install dependencies (`project.dependencies` of `pyproject.toml`) first,
## so that code changes do not reinstall them; the FOCA image runs as non-root
## user. A direct reference to a FOCA commit (temporary) is left out, as the
## image has no Git: the build fails unless the base image has FOCA of that
## commit (`scripts/image_requirements.py`)
COPY pyproject.toml scripts/image_requirements.py /tmp/src/
RUN python /tmp/src/image_requirements.py /tmp/src/pyproject.toml > /tmp/src/requirements.txt \
  && pip install --no-cache-dir -r /tmp/src/requirements.txt

## Install app (non-editable; the base config is installed with the package,
## and deployments override it via `FOCA_CONFIG_OVERLAY`)
## (`README.md` is the package's long description; the license text is
## installed with the package metadata, e.g.,
## `site-packages/trs_filer-<version>.dist-info/licenses/LICENSE`)
## The build context has no Git metadata, so the version is passed as a build
## argument (e.g., `--build-arg SETUPTOOLS_SCM_PRETEND_VERSION=0.4.0`, as the
## workflow does); without it, the app reports version `0.0.0.dev0`
COPY pyproject.toml README.md LICENSE /tmp/src/
COPY trs_filer /tmp/src/trs_filer
ARG SETUPTOOLS_SCM_PRETEND_VERSION
RUN pip install --no-cache-dir --no-deps /tmp/src \
  && rm -rf /tmp/src
USER 1000

## Probe the Swagger UI, which needs neither authentication nor the database;
## set `HEALTHCHECK_URL` if Gunicorn's `--bind` changes the port, or the config
## changes the API base path or the Swagger UI setting (`api.specs.trs`)
ENV HEALTHCHECK_URL=http://localhost:8080/ga4gh/trs/v2/ui/
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(os.environ['HEALTHCHECK_URL'], timeout=4)"]

## Serve with Gunicorn (settings in `trs_filer/gunicorn_config.py`; override
## them via `GUNICORN_CMD_ARGS`, e.g., `--workers 2`); each worker creates the
## app (no preloading) and runs its startup checks, and Gunicorn exits if they
## fail. `python -m trs_filer.app` runs Flask's development server instead
CMD ["gunicorn", "--config", "python:trs_filer.gunicorn_config", \
  "trs_filer.app:create_app()"]
