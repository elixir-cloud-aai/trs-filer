# Getting started

To quickly install the service for development/testing purposes, we recommend
deployment via [Docker Compose](https://docs.docker.com/compose/install/), as
described below. For more durable deployments on cloud native infrastructure,
we also provide a [Helm](https://helm.sh/) chart in the
[`deployment/`](https://github.com/elixir-cloud-aai/trs-filer/tree/dev/deployment)
directory (see [Deployment](deployment.md)). The [FOCA deployment
guide](https://foca.readthedocs.io/en/latest/deployment/) explains how FOCA
apps, such as this one, are configured with Docker Compose and Helm.

## Quick start

--8<-- "README.md:quick-start"

Only TRS-Filer is published, on the host's loopback interface
(`127.0.0.1`); MongoDB is only reachable from the containers. Its data is
kept in the Compose project's volume `mongodb-data` (e.g.,
`trs-filer_mongodb-data`, see `docker volume ls`). Earlier versions kept the
data elsewhere (see [Upgrading](upgrading.md#docker-compose)). The comments
in
[`docker-compose.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/docker-compose.yaml)
describe the settings.

### Other useful commands

To shut down the service, run:

```bash
docker compose down
```

Add `--volumes` to also delete the database.

If you need to inspect the logs, call:

```bash
docker compose logs
```

## Usage

[Endpoints](api.md) can be probed with `curl`, as above, or tried in the
Swagger UI. To register a first tool, with one version and its CWL
descriptor:

```bash
curl -X POST "http://localhost:8080/ga4gh/trs/v2/tools" \
  -H "Content-Type: application/json" \
  -d '{
    "organization": "Example Organization",
    "name": "hello",
    "toolclass": {"name": "Workflow", "description": "A workflow"},
    "versions": [{
      "name": "1.0.0",
      "is_production": false,
      "descriptor_type": ["CWL"],
      "files": [{
        "tool_file": {"path": "hello.cwl", "file_type": "PRIMARY_DESCRIPTOR"},
        "file_wrapper": {"content": "cwlVersion: v1.2\nclass: CommandLineTool\nbaseCommand: echo\ninputs: []\noutputs: []\n"},
        "type": "CWL"
      }]
    }]
  }'
```

The response is the tool's new identifier, e.g., `"ABC123"`; the tool is
then listed by `GET /tools`, and its descriptor is served at
`GET /tools/ABC123/versions/<version_id>/CWL/descriptor` (the version's
identifier is in `GET /tools/ABC123/versions`).

See [Configuration](configuration.md) to change the config of the Docker
Compose setup, e.g., to [allow](configuration.md#remote-files) files whose
contents are retrieved from local URLs. Set the [service
info](configuration.md#service-info) and the [public
URL](configuration.md#public-url) to describe your deployment: the defaults
are placeholders, and TRS-Filer logs a warning on startup while `id` or
`organization` of the service info still have them.

!!! warning
    TRS-Filer has no authentication yet: anybody who can reach the API can
    register, change and delete tools (see [Access
    control](access-control.md)). This is why Docker Compose publishes it
    on the loopback interface only.
