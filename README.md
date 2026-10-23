[![ELIXIR On-Cloud][logo]][org]

# TRS-Filer

[![License][badge-license]][badge-url-license]
[![Build_status][badge-build-status]][badge-url-build-status]
[![Coverage][badge-coverage]][badge-url-coverage]
[![GitHub_tag][badge-github-tag]][badge-url-github-tag]

<!-- --8<-- [start:synopsis] -->
A registry of tools and workflows for your project, network or
infrastructure, brought to you by [ELIXIR On-Cloud](https://elixir-on.cloud/).
It implements the [GA4GH Tool Registry Service (TRS)
API](https://github.com/ga4gh/tool-registry-service-schemas), so that clients
such as workflow engines and execution services can find tools and workflows,
their versions and tool classes, and fetch their descriptors, test files,
container image definitions and other files, one by one or as a ZIP archive.
Additional endpoints register, update and delete tools, tool versions and
tool classes, and set the service info, so that you can run TRS-Filer as the
registry of your own tools or index tools that are published elsewhere. Run it
with Docker Compose or deploy it to Kubernetes with its Helm chart.
<!-- --8<-- [end:synopsis] -->

See [`deployment/`][deployment] for the deployment with the Helm chart and
[`trs_filer/config.yaml`][config] for the configuration.

## Known deployments

<!-- --8<-- [start:deployments] -->
None listed yet.

Running TRS-Filer yourself? Open a pull request that adds your deployment
(URL, operator and notes) to this section of
[`README.md`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/README.md).
<!-- --8<-- [end:deployments] -->

## Quick start

<!-- --8<-- [start:quick-start] -->
With [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and
[Docker](https://docs.docker.com/get-docker/) with the [Compose
plugin](https://docs.docker.com/compose/install/) (version 2) installed, clone
the repository and start TRS-Filer with its MongoDB database:

```bash
git clone https://github.com/elixir-cloud-aai/trs-filer.git
cd trs-filer
docker compose up --build --wait
```

The TRS API is then served at `http://localhost:8080/ga4gh/trs/v2/`, with a
Swagger UI at
[http://localhost:8080/ga4gh/trs/v2/ui](http://localhost:8080/ga4gh/trs/v2/ui):

```bash
curl -X GET "http://localhost:8080/ga4gh/trs/v2/tools" -H "accept: application/json"
```
<!-- --8<-- [end:quick-start] -->

## Contributing

Contributions are welcome! See [`CONTRIBUTING.md`](CONTRIBUTING.md) and mind
our [code of conduct](CODE_OF_CONDUCT.md).

[badge-build-status]: <https://github.com/elixir-cloud-aai/trs-filer/actions/workflows/checks.yaml/badge.svg>
[badge-coverage]: <https://codecov.io/gh/elixir-cloud-aai/trs-filer/branch/dev/graph/badge.svg?branch=dev>
[badge-github-tag]: <https://img.shields.io/github/v/tag/elixir-cloud-aai/trs-filer?color=C39BD3>
[badge-license]: <https://img.shields.io/badge/license-Apache%202.0-blue.svg>
[badge-url-build-status]: <https://github.com/elixir-cloud-aai/trs-filer/actions/workflows/checks.yaml>
[badge-url-coverage]: <https://codecov.io/gh/elixir-cloud-aai/trs-filer?branch=dev>
[badge-url-github-tag]: <https://github.com/elixir-cloud-aai/trs-filer/releases>
[badge-url-license]: <https://www.apache.org/licenses/LICENSE-2.0>
[config]: trs_filer/config.yaml
[deployment]: deployment/
[logo]: docs/images/logo_elixir_on_cloud.png
[org]: <https://elixir-on.cloud/>
