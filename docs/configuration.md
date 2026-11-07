# Configuration

The app is configured by
[`trs_filer/config.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/config.yaml),
the base config, which documents its values. It is a
[FOCA](https://foca.readthedocs.io/) config: the sections `server`, `db`,
`api`, `service_info`, `log` and `exceptions` are described in the [FOCA
documentation](https://foca.readthedocs.io/en/latest/), the app's own
settings are in section `custom` (validated on startup by
[`trs_filer.custom_config.CustomConfig`](reference.md#trs_filer.custom_config.CustomConfig)).
To override some values, write them to a config overlay file and list it in
environment variable `FOCA_CONFIG_OVERLAY` (several files separated by `:`);
FOCA merges overlays into the config on startup (see the [FOCA deployment
guide](https://foca.readthedocs.io/en/latest/deployment/)). Mappings are
merged recursively; all other values, including lists, replace those of the
base config.

## Local overrides

Docker Compose mounts
[`config.dev.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/config.dev.yaml),
an overlay for local development (see [Getting
started](getting-started.md#usage)). To override values locally without
changing it, put them in `config.local.yaml` and mount it in a
`docker-compose.override.yaml` (both are ignored by Git):

```yaml
services:
    trs-filer:
        environment:
            FOCA_CONFIG_OVERLAY: /etc/trs-filer/config.dev.yaml:/etc/trs-filer/config.local.yaml
        volumes:
            - ./config.local.yaml:/etc/trs-filer/config.local.yaml:ro
```

## Public URL

The TRS API includes the URLs of tools and tool versions in its responses
(`url`), which TRS-Filer builds from `custom.service`:
`<url_prefix>://<external_host>:<external_port>/<api_path>/tools/<id>`. The
base config has the URL of the Docker Compose setup
(`http://localhost:8080/ga4gh/trs/v2`); deployments set their own, e.g.:

```yaml
custom:
  service:
    url_prefix: https
    external_host: trs.example.org
    external_port: 443
    api_path: ga4gh/trs/v2
```

The Helm chart sets it from its values (see [Deployment](deployment.md));
it can't set other parts of the config yet (see
[Configuration](deployment.md#configuration) there).

## Identifiers

TRS-Filer generates the identifiers of tools, tool versions and tool classes
that are registered without one (`POST`): random strings of `length`
characters from `charset`, in `custom.tool.id`, `custom.version.id` and
`custom.toolclass.id`. By default, tool identifiers have six upper-case
letters and digits, and version and tool class identifiers six lower-case
letters and digits (tool classes created along with a tool, see [Tool
classes](#tool-classes), get identifiers like tools). `charset` lists the characters themselves (e.g.,
`ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789`); expressions such as
`string.ascii_uppercase + string.digits` are rejected on startup (see
[Upgrading](upgrading.md#configuration)). Identifiers can also be chosen by
the client (`PUT`, see [API](api.md)).

## Meta versions

Tools and versions have a `meta_version` (a field of the TRS API that tells
clients that an object changed), set in `custom.tool.meta_version` and
`custom.version.meta_version`:

- New tools and versions get the `init` value (default 1).
- Replacing a tool (`PUT /tools/{id}` with the identifier of a stored tool)
  adds `custom.tool.meta_version.increment` (default 1) to its meta
  version, and `custom.version.meta_version.increment` (default 1) to those
  of its versions that replace stored versions (same identifier); its other
  versions are new and get the `init` value.
- Replacing a version (`PUT /tools/{id}/versions/{version_id}`) adds
  `custom.version.meta_version.increment` to the version's meta version.
- Adding, replacing or deleting a version with the version endpoints
  (`POST /tools/{id}/versions`, `PUT` and `DELETE
  /tools/{id}/versions/{version_id}`) also adds
  `custom.tool.meta_version.increment` to the tool's meta version, as the
  tool as served (its `versions`) changes. Set
  `custom.tool.meta_version.on_version_change: false` to change the tool's
  meta version only when the tool itself is replaced. Requests that fail
  change no meta version.
- Stored meta versions that are not integers restart at the `init` value.

Replacements with identical content increment the meta versions, too.
Concurrent changes of the same object may give it the same meta version,
or, for tools whose versions change at the same time, set it back to an
earlier value. Tool classes have none (`custom.toolclass.meta_version` is
unused).

## Tool classes

Each tool has a tool class (e.g., workflow or command-line tool), which is
stored with the tool and in the list of tool classes (`GET /toolClasses`).
When a tool is registered or replaced (`POST /tools`, `PUT /tools/{id}`):

- If a tool class with the identifier of the tool's `toolclass.id` exists,
  the tool stores a copy of that tool class, not the one it was sent with,
  and the tool class is not changed.
- Otherwise, with `custom.toolclass.validation: false` (the default), the
  tool class is created as sent with the tool (with a generated identifier
  if it has none); with `custom.toolclass.validation: true`, the
  registration fails with `400 Bad Request` and nothing is stored.

Tool classes are changed only with the [tool class
endpoints](api.md#registering-tools). The copies stored with tools are not
updated when a tool class is replaced (`PUT /toolClasses/{id}`); register
the tools again to update them. The `toolClass` filter of `GET /tools` uses
the copies.

If tools with the same new tool class identifier but different tool classes
are registered at the same time, the tool class of the first one is
created, and the others store a copy of it, too.

### Adding tool classes

`custom.access_control.tool_classes` sets who may add tool classes, with
the modes of the service types of [Cloud
Registry](https://cloud-registry.readthedocs.io/en/latest/configuration/#service-types):

- `open` (the default): any user who may register tools, explicitly (`POST
  /toolClasses`, `PUT /toolClasses/{id}`) or by registering a tool with a
  new tool class (see above; not with `custom.toolclass.validation: true`,
  which leaves only the explicit way);
- `controlled`: only admins add tool classes; tools must have a registered
  tool class;
- `moderated`: tool classes added by users other than admins are pending
  until an admin approves them, and so are the tools that have them.

TRS-Filer has no users and admins yet (see [Access
control](access-control.md)), so `open` is the only mode it supports for
now: the app refuses to start with `controlled` or `moderated`, with an
error that the custom config doesn't match its model, caused by one that
names the setting (`access_control.tool_classes: Value error, only the
mode 'open' of adding tool classes is supported yet`).
For the same reason, it doesn't limit the number of tool classes that no
tool has per user, as Cloud Registry does for service types: anybody who
may write can add tool classes without bound, so restrict writes in front
of the app, and delete unwanted tool classes (`DELETE /toolClasses/{id}`).

For example, in a config overlay:

```yaml
custom:
    access_control:
        tool_classes: open
```

## Remote files

Files of tool versions are registered with their content (`content`) or a
URL (`url`) that TRS-Filer retrieves the content from: on registration, and
when it serves the files of a version as a ZIP archive and has no stored
content for one of them. `custom.remote_files` sets how URLs are retrieved:

| Option | Default | Description |
| --- | --- | --- |
| `schemes` | `[https]` | Allowed URL schemes (`http`, `https`). |
| `allowed_hosts` | `[]` | Host names, IP addresses and CIDR networks that may be retrieved although they resolve to addresses that are not public (e.g., for local setups). |
| `connect_timeout` | `5` | Seconds to connect, per address of a host. |
| `read_timeout` | `10` | Seconds per read. |
| `total_timeout` | `30` | Seconds per file, including redirects. |
| `max_size` | `1048576` | Maximum size of a file, in bytes (1 MiB). |
| `max_redirects` | `5` | Redirects followed per file. |

Hosts must resolve to public addresses only (also after redirects), unless
they are listed in `allowed_hosts`; proxy settings of the environment are
not used. Retrievals that fail (e.g., a refused URL, a timeout, a response
other than `2xx` or a file that is too large) fail the registration with
`400 Bad Request`; for ZIP archives, `404 Not Found`. Name resolution is not
limited by the timeouts. For example, to register files of a web server on
the Docker Compose network in a local setup:

```yaml
custom:
  remote_files:
    schemes: [http, https]
    allowed_hosts: [files.local]
```

## Request size limit

Request bodies are limited to `server.max_content_length` bytes (default:
1048576, i.e., 1 MiB), by FOCA: larger requests, also chunked ones, are
rejected with `413 Content Too Large` before they are parsed. The app
refuses to start without a limit. Raise it to register tools with larger
inline file contents, together with the limits of any proxies in front of
the app; prefer files with URLs.

## Rate limits

TRS-Filer has no rate limits of its own. In production, limit the rate of
requests per client at the reverse proxy or ingress controller in front of
it, so that single clients can't overload the app or its database.

## Server

The image serves the app with [Gunicorn](https://gunicorn.org/), with the
settings of
[`trs_filer/gunicorn_config.py`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/gunicorn_config.py):
it listens on port 8080, with one worker process with four threads.
Override settings with the environment variable `GUNICORN_CMD_ARGS` (e.g.,
`--workers 2 --threads 8`), but not `--bind`: the image's health check and
the Helm chart expect port 8080. Behind a reverse proxy, set its addresses
in `FORWARDED_ALLOW_IPS`, so that Gunicorn trusts its `X-Forwarded-*`
headers (the Helm chart sets it from `trs_filer.forwardedAllowIps`, see
[Forwarded headers](deployment.md#forwarded-headers)). `server.host` and `server.port` of the config only apply to Flask's
development server (`python -m trs_filer.app`). `server.debug` must stay off
outside local development: Flask's debugger allows executing arbitrary code.

## Database

TRS-Filer stores tools (with their versions and files) and tool classes in
the collections `tools` and `toolclasses` of the MongoDB database `trsStore`
at `db.host` and `db.port` (in the base config: `mongodb:27017`, the service
of Docker Compose). FOCA reads the environment variables `MONGO_HOST`,
`MONGO_PORT`, `MONGO_DBNAME`, `MONGO_USERNAME` and `MONGO_PASSWORD`, or a
complete connection string in `MONGO_URI`, which take precedence over the
config (see the [FOCA documentation](https://foca.readthedocs.io/en/latest/));
with `MONGO_DBNAME` set, the app uses that database instead of `trsStore`.

## Service info

`GET /service-info` is served by FOCA from section `service_info` of the
config, according to the GA4GH service info schema (validated on startup).
Its `version` is the version of the installed package
(`service_info.package`). The base config describes the app, not a
deployment: its `id` (`org.example.trs-filer`) and `organization` are
placeholders in reserved example domains (RFC 2606). FOCA warns on startup
while `id`, `organization.url`, `contactUrl` or `documentationUrl` are in
such a domain (as in the example below), not of other fields (e.g.,
`organization.name`, which overlays keep unless they set it). Deployments
set their own `id`, `name`, `description`, `organization`, `contactUrl` and
`environment` in `service_info.service`, e.g.:

```yaml
service_info:
  service:
    id: org.example.trs
    name: Example TRS
    description: Tools and workflows of the Example Organization.
    organization:
      name: Example Organization
      url: https://example.org
    contactUrl: mailto:trs-admins@example.org
    environment: prod
```

The Helm chart has no value for the service info yet, so chart deployments
serve the placeholders unless they deploy an overlay of their own (see
[Configuration](deployment.md#configuration) in the deployment docs).

## Errors

Errors are problem details, sent as `application/json` (section
`exceptions`, see [Errors](api.md#errors)). Requests that the validation of
the API specification rejects (e.g., an unknown descriptor type) get the
reason as `detail`, shortened to `exceptions.max_detail_length` characters
(500 by default); set `exceptions.validation_details: false` to send a
generic `detail` instead (see FOCA's
[documentation](https://foca.readthedocs.io/en/latest/configuration/exceptions/)).
Requests that TRS-Filer itself refuses (e.g., deleting the last version of
a tool) get their reason as `detail` whatever `exceptions.validation_details`
is set to; it names the rule, not the values sent (see
[Errors](api.md#errors)). Like all `detail`s, it is shortened to
`exceptions.max_detail_length` characters, and not sent if
`exceptions.public_members` doesn't list `detail`.
