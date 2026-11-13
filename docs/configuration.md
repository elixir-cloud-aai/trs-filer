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

## Deployment configuration

TRS-Filer works with any OpenID Connect provider that issues access tokens
as per [RFC 9068](https://www.rfc-editor.org/rfc/rfc9068) (JWTs). The
identity provider, its claims and the groups mapped to roles are deployment
configuration: the base config has no defaults for them, so each deployment
sets them in an overlay (or in the Helm chart's `config` value),
otherwise the app refuses to start:

- `security.auth.issuers`: the trusted token issuers (the `iss` claim of their
  tokens, e.g., `https://login.example.org/oidc/`); tokens of other issuers
  are rejected (see [Authentication](access-control.md#authentication));
- `security.auth.audience`: the client IDs of the apps whose tokens are
  accepted (the `aud` claim, e.g., of a portal or gateway that registers
  tools), unless `security.auth.verify_audience` is `false`, which accepts
  tokens for any audience (not recommended);
- `security.access_control.claim_groups`: the claim with the groups of users
  (e.g., `groups`), needed for admins; add it to
  `security.auth.userinfo_claims` if the identity provider releases it via
  user info only, not in access tokens;
- `security.access_control.group_mapping`: the group(s) whose members are
  admins (values of the group claim, see [Access
  control](access-control.md#admins)), or
  `security.access_control.require_admin: false` to run without admins
  (nobody can write then).

For example:

```yaml
security:
    auth:
        issuers:
            - https://login.example.org/oidc/
        audience:
            - trs-portal
        userinfo_claims:
            - groups
    access_control:
        claim_groups: groups
        group_mapping:
            trs-admins: admin
```

### Entitlement-style groups

Some identity providers release groups as entitlements, i.e., URNs, in a
multi-valued claim (here `entitlement`) other than `groups`, and only via user
info:

```yaml
security:
    auth:
        issuers:
            - https://idp.example.org/
        audience:
            - <client ID of the portal>
        userinfo_claims:
            - entitlement
    access_control:
        claim_groups: entitlement
        group_mapping:
            "urn:example:group:trs-admins#issuer.example.org": admin
```

Settings for specific identity providers belong to the documentation of the
deployment, not here.

Notes:

- The group (the URN above is illustrative) is a value of the claim. Quote
  such keys in YAML, as they contain `:` and `#`.
- Without the claim in `userinfo_claims`, no user gets the admin role.
- Clients must request the scope that releases the claim when logging in
  (here the one for `entitlement`, besides `openid`), and the identity
  provider must allow it for the client.
- TRS-Filer accepts only access tokens with the `typ` header `at+jwt`
  (`security.auth.verify_token_type`, enabled by default). Before going live,
  check that the identity provider issues such tokens to the clients, and
  that their `aud` matches `audience`: otherwise writes fail with `401
  Unauthorized`.
- To accept tokens of some clients only (e.g., of a portal or gateway in
  front of TRS-Filer), list their client IDs in `security.auth.clients`
  (FOCA compares them with the `client_id` claim of tokens, or `azp`
  without it); tokens of other clients, or without either claim, get `401
  Unauthorized`. With several issuers, make sure that clients of one issuer
  can't claim the IDs of another's.

The policies (`security.access_control.policies`, see FOCA's [access
control](https://foca.readthedocs.io/en/latest/access-control/#configuring-policies))
say what each role may do. They are named, so that an overlay can change,
add or remove single rules by name (FOCA's [named
entries](https://foca.readthedocs.io/en/latest/configuration/#named-entries));
the base config has rules for reads only, which apply if login is required
for them (see [Requiring login for
reads](access-control.md#requiring-login-for-reads)): writes are for admins.
An overlay that gives the policies as a list replaces all rules of the base
config instead; FOCA refuses to start if an overlay gives named rules after
one that gives a list.

The API specification (`api.specs`) is named `trs`, too, so that an overlay
can change it by name, e.g., to [require login for
reads](access-control.md#requiring-login-for-reads).

FOCA's service clients (`security.auth.service_clients`,
`security.auth.on_behalf_of_header`) are not supported; the app refuses to
start with them (see [Authentication](access-control.md#authentication)).

## Local overrides

Docker Compose mounts
[`config.dev.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/config.dev.yaml),
an overlay for local development that trusts a fictitious token issuer
(`https://login.example.org/oidc/`; set your own in a local override), sets
an example group claim (`groups`), accepts tokens for any audience and
requires no admins, so writes are refused until you set your identity
provider and admin group (see [Getting started](getting-started.md#usage),
and [Running without
authentication](development.md#running-without-authentication) for
development without an identity provider). To override values locally
without changing it, put them in `config.local.yaml` and mount it in a
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
other parts of the config go into its `config` value (see
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

- `open` (the default): any authenticated user, explicitly (`POST
  /toolClasses`, or `PUT /toolClasses/{id}` with the identifier of no tool
  class) or by registering a tool with a new tool class (see above; not with
  `custom.toolclass.validation: true`, which leaves only the explicit way);
  only admins replace and delete tool classes;
- `controlled`: only admins add tool classes; tools must have a registered
  tool class;
- `moderated`: tool classes added by users other than admins are pending
  until an admin approves them, and so are the tools that have them.

`open` is the only mode TRS-Filer supports for now: the app refuses to
start with `controlled` or `moderated`, with an error that the custom config
doesn't match its model, caused by one that names the setting
(`access_control.tool_classes: Value error, only the mode 'open' of adding
tool classes is supported yet`). Nor does it limit the number of tool
classes that no tool has per user, as Cloud Registry does for service types:
any authenticated user can add tool classes without bound; admins delete
unwanted ones with `DELETE /toolClasses/{id}` (see [Access
control](access-control.md#admins)). To keep users from adding tool classes
explicitly until `controlled` is supported, remove the rule
`add-tool-classes` in a config overlay (`security.access_control.policies`,
`add-tool-classes: null`): `POST /toolClasses` and `PUT /toolClasses/{id}`
are then for admins only, but registering tools with new tool classes still
adds them, unless `custom.toolclass.validation` is true. Without the rule
for adding to a collection (`register-tools` for tools, `add-tool-classes`
for tool classes), `PUT` with a new identifier is refused (`403`) also for
users whom other rules allow to replace objects (e.g., editors, see
[Admins](access-control.md#admins)): such rules let them replace stored
objects, not add new ones.

For example, in a config overlay:

```yaml
custom:
    access_control:
        tool_classes: open
```

## Remote files

Files of tool versions are registered with their content (`content`) or a
URL (`url`) that TRS-Filer retrieves the content from: on registration, and
when it serves the files of a version as a ZIP archive or a descriptor as
plain text (`PLAIN_` types) and has no stored content for one of them.
`custom.remote_files` sets how URLs are retrieved:

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
`400 Bad Request`; for ZIP archives and plain descriptors, `404 Not
Found`. The app logs the reason, which names the problem but not the URL
(e.g., `InvalidURL: The URL has user info`; for errors of lower layers,
only their types, such as `ConnectionError (caused by MaxRetryError,
NameResolutionError, gaierror)`), next to the URL without its user info.
Name resolution is not limited by the timeouts. For example, to register
files of a web server on the Docker Compose network in a local setup:

```yaml
custom:
  remote_files:
    schemes: [http, https]
    allowed_hosts: [files.local]
```

## I/O Schemas

`custom.io_schema.validation` (experimental, `false` by default) checks
GA4GH I/O Schema files (files of type `OTHER` named `ga4gh-io.schema.json`)
on registration against the meta-schema of the GA4GH I/O Profile 0.3.0,
and rejects invalid ones with `400 Bad Request` (see [Checking I/O
Schemas](io-schema.md#checking-io-schemas)); `custom.io_schema.timeout`
(default: `10`) is the time limit of checking a file, in seconds:

```yaml
custom:
    io_schema:
        validation: true
        timeout: 10
```

## File storage

By default, TRS-Filer stores the content of files in MongoDB, with the
other data of tools. Optionally, it stores the content of files in
**S3-compatible object storage** instead, and keeps only their metadata in
MongoDB (`custom.storage`):

| Option | Default | Description |
| --- | --- | --- |
| `backend` | `mongodb` | Where the content of files registered from now on is stored: `mongodb` or `s3`. |
| `s3.bucket` | | Name of the bucket, which must exist; required if `s3` is set. |
| `s3.endpoint_url` | | URL of the S3 API, e.g., `https://s3.example.org`; boto3's default if not set (AWS, or the environment variable `AWS_ENDPOINT_URL_S3` or `AWS_ENDPOINT_URL`). |
| `s3.region` | | Region of the bucket; boto3's default if not set (e.g., the environment variable `AWS_REGION`). |
| `s3.prefix` | `""` | Prefix of the keys of the objects (e.g., `trs-filer/`), so that a bucket can be shared. |
| `s3.addressing_style` | `path` | `path` (`<endpoint>/<bucket>/<key>`, which most self-hosted servers need), `virtual` (`<bucket>.<endpoint>/<key>`) or `auto` (boto3's choice). |
| `s3.presigned_urls` | `false` | Serve files via presigned URLs of their objects instead of through the app (see below). |
| `s3.presigned_url_expiry` | `300` | Validity of presigned URLs, in seconds (at most 604800, 7 days). |
| `s3.connect_timeout` | `5` | Seconds to connect to the S3 API. |
| `s3.read_timeout` | `10` | Seconds per read from the S3 API. |

TRS-Filer talks to the storage through the S3 API only (with
[boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)),
so any S3-compatible server or service works, e.g.,
[SeaweedFS](https://github.com/seaweedfs/seaweedfs) or [Zenko
CloudServer](https://github.com/scality/cloudserver) (both Apache-2.0),
Ceph RGW, or the S3 services of cloud and HPC providers. CI tests with
SeaweedFS.

**Credentials** are never part of the config (which rejects unknown
settings): boto3 takes them from the environment with its [default
credential
chain](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html),
e.g., from the environment variables `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` (set from a Secret, see [Object
storage](deployment.md#object-storage) for the Helm chart), or a web
identity token. The app needs the S3 permissions to put, get and delete
objects in the bucket (with the prefix, if set); the bucket isn't created
by the app.

For example:

```yaml
custom:
  storage:
    backend: s3
    s3:
      endpoint_url: https://s3.example.org
      bucket: trs-filer
      region: us-east-1
      prefix: trs-filer/
```

How files are stored:

- When a version is registered (also with its tool, and when it is
  replaced), the content of each of its files, once all files are valid
  (and retrieved from their URLs, see [Remote files](#remote-files)), is
  written once as a new object, under a random key with the prefix (as
  `text/plain; charset=utf-8`). MongoDB keeps the file's metadata and a
  reference to the object, with the SHA-256 checksum and the size of the
  content; the reference is never served.
- When files are served, their content is read from the object and checked
  against the checksum and size; changed or missing objects fail the
  request with `500 Internal Server Error`, and the app logs the key. A
  missing object is first read again from the stored files once, as the
  version may have been replaced or deleted meanwhile (this needs reads
  from the primary: with a `readPreference` of secondaries in `MONGO_URI`,
  the retry may still see the old files).
- Objects that no stored file refers to any more are deleted at the end of
  the request that released them: those of replaced and deleted versions
  and tools, and those of registrations that failed. If deleting an object
  fails, or the app stops during a request, objects can be left without a
  file that refers to them (logged at `ERROR`); they are not served.
- The backend only decides where new files go: files stay where they were
  stored. With `backend: mongodb` and `s3` set, files in object storage are
  still served (e.g., to switch back); without `s3`, they fail with `500
  Internal Server Error`. Existing files are not moved to object storage.

With **presigned URLs** (`s3.presigned_urls: true`), clients get files from
the object storage directly, which then must be reachable by them: JSON
responses with files (descriptors, tests, containerfiles) have the
presigned URL of the object as `url`, instead of the `content` and of the
URL given on registration, and the SHA-256 checksum of the content
(`sha-256`, unless given on registration); plain responses (`PLAIN_`
types) redirect to the presigned URL (`302 Found`). Presigned URLs expire
after `s3.presigned_url_expiry` seconds, or earlier, when the version is
replaced or deleted (its objects are deleted). ZIP archives are still built
by the app.

A presigned URL lets anybody who has it read the file until it expires,
without a token, also if the deployment requires login for reads (see
[Requiring login for reads](access-control.md#requiring-login-for-reads)):
keep the expiry short there, and keep the URLs out of logs. Serve the S3
API on another host than TRS-Filer, so that clients don't send their
access tokens along with the redirect.

**Docker Compose** doesn't bundle an object store. To try object storage
locally, add SeaweedFS (here with the S3 API without authentication, for
tests only) in a `docker-compose.override.yaml`, and set the backend in a
config overlay (e.g., `config.s3.yaml`, after `config.dev.yaml`):

```yaml
# docker-compose.override.yaml
services:
  trs-filer:
    environment:
      FOCA_CONFIG_OVERLAY: /etc/trs-filer/config.dev.yaml:/etc/trs-filer/config.s3.yaml
      # Any values: SeaweedFS without authentication doesn't check them
      AWS_ACCESS_KEY_ID: test
      AWS_SECRET_ACCESS_KEY: test
    volumes:
      - ./config.s3.yaml:/etc/trs-filer/config.s3.yaml:ro
  seaweedfs:
    image: docker.io/chrislusf/seaweedfs:4.51
    command: server -s3 -ip.bind=0.0.0.0
    ports:
      - "127.0.0.1:8333:8333"
```

```yaml
# config.s3.yaml
custom:
  storage:
    backend: s3
    s3:
      endpoint_url: http://seaweedfs:8333
      bucket: trs-filer
      region: us-east-1
```

Then create the bucket, e.g., with the AWS CLI on the host:
`aws --endpoint-url http://127.0.0.1:8333 s3 mb s3://trs-filer`.

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
headers (with the Helm chart, in `trsFiler.extraEnv`, see [Forwarded
headers](deployment.md#forwarded-headers)). `server.host` and
`server.port` of the config only apply to Flask's development server
(`python -m trs_filer.app`). `server.debug` must stay off outside local
development: Flask's debugger allows executing arbitrary code.

## Database

TRS-Filer stores tools (with their versions and files; the content of files
optionally in object storage, see [File storage](#file-storage)) and tool
classes in the collections `tools` and `toolclasses` of the MongoDB
database `trsStore` at `db.host` and `db.port` (in the base config:
`mongodb:27017`, the service of Docker Compose). FOCA reads the environment variables `MONGO_HOST`,
`MONGO_PORT`, `MONGO_DBNAME`, `MONGO_USERNAME` and `MONGO_PASSWORD`, or a
complete connection string in `MONGO_URI`, which take precedence over the
config (see the [FOCA documentation](https://foca.readthedocs.io/en/latest/));
with `MONGO_DBNAME` set, the app uses that database instead of `trsStore`.
FOCA keeps the rules of access control in the collection `policy_rules` of
the same database (`security.access_control.db_name` and
`collection_name`), and its changes in `policy_rules_changes`.

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
The base config sets `exceptions.validation_reasons: true`, so that this
`detail` is the validator's reason, as up to FOCA 0.21, which may quote
the rejected values; set it to `false` for FOCA's default, which names
the invalid fields by location and code instead.
Requests that TRS-Filer itself refuses (e.g., deleting the last version of
a tool) get their reason as `detail` whatever `exceptions.validation_details`
is set to; it names the rule, not the values sent (see
[Errors](api.md#errors)). Like all `detail`s, it is shortened to
`exceptions.max_detail_length` characters, and not sent if
`exceptions.public_members` doesn't list `detail`.
