##### BASE IMAGE #####
FROM elixircloud/foca:latest

##### METADATA ##### 
LABEL software="TRS-filer"
LABEL software.description="Tool Registry Service with FOCA"
LABEL software.website="https://github.com/elixir-cloud-aai/trs-filer"
LABEL software.license="https://spdx.org/licenses/Apache-2.0"
LABEL maintainer="alexander.kanitz@alumni.ethz.ch"
LABEL maintainer.organisation="ELIXIR Cloud & AAI"

# Python UserID workaround for OpenShift/K8S
ENV LOGNAME=ipython
ENV USER=ipython
ENV HOME=/tmp/user

# Install general dependencies
RUN apt-get update && apt-get install -y nodejs openssl git build-essential python3-dev curl jq

## Set working directory
WORKDIR /app

## Copy Python requirements
COPY ./requirements.txt /app/requirements.txt

## Install Python dependencies - (TODO: Refer cwl-wes later)
RUN cd /app \
  && pip install -r requirements.txt \

## Copy remaining app files
COPY ./ /app

## Install app
## Install app
RUN cd /app \
  && python setup.py develop \
  && cd / \
  && chmod g+w /app/drs_filer/api/