##### BASE IMAGE #####
## Pinned by digest, so that rebuilds use the same base image.
## TEMPORARY: FOCA's development image built from the commit that
## `requirements.txt` pins (#88), replaced by the release image
## (`elixircloud/foca:0.17.0-py3.13`) before the next release
## (`scripts/check_release_pins.py`); dated tags move with later commits of
## the day, so only the digest identifies the image
## FOCA commit: 29af8a64a2b0aae21845fa37a4a54076811f62bf
FROM elixircloud/foca:20261023-py3.13@sha256:1e1275f77be3a256449dc8739410f32b0d0376534b824d8b746d5316d27cdb1f

##### METADATA #####
LABEL software="TRS-filer"
LABEL software.description="Tool Registry Service with FOCA"
LABEL software.website="https://github.com/elixir-cloud-aai/trs-filer"
LABEL software.license="https://spdx.org/licenses/Apache-2.0"
LABEL maintainer="nagorikushagra9@gmail.com"
LABEL maintainer.organisation="ELIXIR Cloud & AAI"

## Install dependencies first, so that code changes do not reinstall them;
## the FOCA image runs as non-root user `foca` (UID 1000), so install as
## root. A direct reference to a FOCA commit (temporary) is left out, as the
## image has no Git: the build fails unless the base image has FOCA of that
## commit (`scripts/image_requirements.py`)
WORKDIR /app
USER root
## TEMPORARY: the Helm chart's config Job runs `update-config-map.sh` in this
## image, which needs `curl` and `jq` (also for `yq`); FOCA's images no longer
## ship them. Removed with the config Job (#135)
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl jq \
  && rm -rf /var/lib/apt/lists/*
COPY ./requirements.txt ./scripts/image_requirements.py /tmp/src/
RUN python /tmp/src/image_requirements.py /tmp/src/requirements.txt > /tmp/src/image_requirements.txt \
  && pip install --no-cache-dir -r /tmp/src/image_requirements.txt \
  && rm -rf /tmp/src
## The app itself, without dependencies (installed above). FOCA no longer
## writes to the API directory, which needs no write permissions
COPY ./ .
RUN pip install --no-cache-dir --no-deps -e .
USER 1000

CMD ["bash", "-c", "cd /app/trs_filer && gunicorn -c gunicorn.py wsgi:app"]
