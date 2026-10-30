[![ELIXIR On-Cloud](images/logo_elixir_on_cloud.png)](https://elixir-on.cloud/)

# TRS-Filer

--8<-- "README.md:synopsis"

## Known deployments

--8<-- "README.md:deployments"

## Contents

- [Getting started](getting-started.md): run TRS-Filer with Docker Compose
  and send the first requests.
- [Configuration](configuration.md): the base config, overlays, the public
  URL, identifiers, tool classes, remote files, the request size limit, the
  server and the service info.
- [API](api.md): the GA4GH TRS endpoints, the endpoints that register tools,
  versions and tool classes, and errors.
- [Access control](access-control.md): who can read and change the
  registry, and how to restrict it.
- [Deployment](deployment.md): the Helm chart for Kubernetes.
- [Operations](operations.md): the components, logs and the database.
- [Upgrading](upgrading.md): changes to existing deployments and data.
- [Development](development.md): development setup, checks, documentation
  and versions.
- [Contributing](contributing.md): how to contribute, the code of conduct,
  pull requests, commit messages and the Python guidelines.
- [API reference](reference.md): the code, generated from its docstrings.
- [Changelog](changelog.md): release notes.

## Architecture

TRS-Filer is a [Flask](https://flask.palletsprojects.com/) app built with
[FOCA](https://github.com/elixir-cloud-aai/foca), configured declaratively in
YAML, which serves the [GA4GH Tool Registry Service
(TRS)](https://github.com/ga4gh/tool-registry-service-schemas) API from its
OpenAPI specification. It stores tools, their versions and files, and tool
classes in a [MongoDB](https://www.mongodb.com/) database; file contents are
either stored with the files or retrieved from their URLs (see [Remote
files](configuration.md#remote-files)). A [Helm](https://helm.sh/) chart and
a [Docker Compose](https://docs.docker.com/compose/) setup are provided for
deployments on Kubernetes and for development, respectively.

## License

This project is covered by the [Apache License
2.0](https://www.apache.org/licenses/LICENSE-2.0) also [shipped with this
repository](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/LICENSE).

## Contact

The project is a collaborative effort under the umbrella of [ELIXIR
On-Cloud](https://elixir-on.cloud/). Follow the link to get in touch with us
via chat or email. Please mention the name of this service for any inquiry,
proposal, question etc.
