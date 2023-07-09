##### BASE IMAGE #####
FROM elixircloud/foca:20221110-py3.10

##### METADATA ##### 
LABEL software="TRS-filer"
LABEL software.description="Tool Registry Service with FOCA"
LABEL software.website="https://github.com/elixir-cloud-aai/trs-filer"
LABEL software.license="https://spdx.org/licenses/Apache-2.0"
LABEL maintainer="nagorikushagra9@gmail.com"
LABEL maintainer.organisation="ELIXIR Cloud & AAI"

WORKDIR /app
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
COPY ./ .
RUN pip install -e .

## Add permissions for storing updated API specification
## (required by FOCA)
RUN chmod -R a+rwx /app/trs_filer/api

