##### BASE IMAGE #####
FROM elixircloud/foca:20200809

##### METADATA ##### 
LABEL software="TRS-filer"
LABEL software.description="Tool Registry Service with FOCA"
LABEL software.website="https://github.com/elixir-cloud-aai/trs-filer"
LABEL software.license="https://spdx.org/licenses/Apache-2.0"
LABEL maintainer="nagorikushagra9@gmail.com"
LABEL maintainer.organisation="ELIXIR Cloud & AAI"

## Copy app files
COPY ./ /app

## Install app
RUN cd /app \
  && python setup.py develop \
  && cd / \
  && chmod g+w /app/trs_filer/api/ \
  && pip install yq

CMD ["bash", "-c", "cd /app/trs_filer; python app.py"]
