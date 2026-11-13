# Upgrading

The [release notes](changelog.md) list the breaking changes of each release
and how to upgrade. This page describes how existing setups and data are
affected by the changes since the tag `v0.3.0` (2023) and the images
published from `dev` before the move to FOCA 0.17 (tagged `latest` and by
date, with FOCA 0.12); for images from `dev` since then, see [Images from
`dev` since FOCA 0.17](#images-from-dev-since-foca-017).
Upgrading from 0.5.0? See [From 0.5.0](#from-050); from 0.4.0, see
[From 0.4.0](#from-040) too.

## From 0.5.0

The API implements TRS 2.0.2, and TRS-Filer runs on FOCA 0.23 (see FOCA's
[migration
guide](https://github.com/elixir-cloud-aai/foca/blob/dev/docs/migration-0.23.md));
existing data needs no changes. Check clients and custom configs:

- `GET /tools` filters by `tags` (comma-separated; tools must have all of
  them) instead of refusing the filter with `400 Bad Request`. Tools get
  their tags on registration (`tags` of `ToolRegister`, strings without
  commas) and return them; stored tools have none (see [Listing
  tools](api.md#listing-tools)).
- The descriptor type `SMK` (Snakemake) is supported: versions and files of
  type `SMK` are registered, and the `SMK` and `PLAIN_SMK` paths of the
  descriptor, test and file endpoints behave as those of the other types,
  instead of giving `400 Bad Request` (see [Descriptor
  types](api.md#descriptor-types)).
- Descriptors are served as plain text (`text/plain`) for the `PLAIN_`
  types (`{type}/descriptor` and `{type}/descriptor/{relative_path}`, e.g.,
  `PLAIN_CWL`), instead of `404 Not Found`; tests are still not served for
  them (see [Descriptor types](api.md#descriptor-types)). The `text/plain`
  responses of these endpoints have no schema in the served specification.
- `{type}/descriptor/{relative_path}` finds files in subdirectories by
  encoded paths (`tools%2Fecho.cwl`, as in the specification) and by plain
  ones (`tools/echo.cwl`), instead of `404 Not Found`; paths encoded twice
  (`tools%252Fecho.cwl`), which clients had to send before, still work (see
  [Relative paths](api.md#relative-paths)). The parameter `relative_path`
  has format `path` in the served specification.
- Versions take a `description` (`ToolVersionRegister`), which they
  return; registrations with it failed with `400 Bad Request` before.
- The served specification (`openapi.json`, Swagger UI) has the app's
  `info` (title `TRS-Filer`, license and contact), instead of the TRS
  specification's.
- **TRS 2.0.2 (breaking):** the served specification is that of the TRS
  release 2.0.2 instead of a commit of TRS `develop` before it (see
  [Supported TRS version](api.md#supported-trs-version)), and the service
  info reports TRS version `2.0.2` (`type.version`) instead of `2.0.1`.
  Custom configs that set `service_info.service.type.version` keep their
  value; set it to `2.0.2`. The response of `GET
  /tools/{id}/versions/{version_id}/{type}/files?format=zip` is declared as
  a binary file (`application/zip`), as it is served; clients generated
  from the specification may change.
- The read operations of TRS and the service info are declared public
  (`security: []`), and TRS's security scheme `BEARER` as an HTTP bearer
  scheme (it was left out); nothing changes for clients, as no endpoint
  required a token before. Config overlays with `patches` of
  `api.specs.trs` must patch the operations of the new specification, and
  `null` in patches now removes the key instead of setting it to `null`
  (FOCA 0.23). Config overlays that set `api.specs.trs.path` must list
  `api/20250902.4854e2f.openapi.yaml` instead of
  `api/20230406.1dd4bf8.openapi.yaml`, in the order of the base config.
- Versions take the versions of their languages (`descriptor_type_version`
  of `ToolVersionRegister`, by descriptor type), which they return;
  registrations with it failed with `400 Bad Request` before.
- **Tokens for writes (breaking):** registering, changing and deleting tools,
  versions and tool classes (`POST`, `PUT` and `DELETE`, see [Registering
  tools](api.md#registering-tools)) need an access token (RFC 9068,
  `at+jwt`) of a trusted OpenID Connect provider, of a user in a group mapped
  to the role `admin`; without a valid token, they answer `401
  Unauthorized`, with a token of other users `403 Forbidden`. Reads stay
  public. The app refuses to start until the deployment sets its identity
  provider and admin group (see [Access control](access-control.md)). To
  upgrade:
    1. Register TRS-Filer's clients (e.g., a portal, a gateway or the
       scripts that register tools) with your identity provider, so that
       they get access tokens of type `at+jwt` for an audience of
       TRS-Filer, with the group claim (or the scope that releases it via
       user info).
    2. Add to your config overlay (with the Helm chart: the value
       `config`, without which rendering fails)
       `security.auth.issuers`, `security.auth.audience`,
       `security.access_control.claim_groups` (and
       `security.auth.userinfo_claims` if the identity provider releases the
       claim via user info only) and `security.access_control.group_mapping`
       with your admin group (see [Deployment
       configuration](configuration.md#deployment-configuration)).
    3. Let the clients send the token (`Authorization: Bearer <token>`)
       with writes.
    4. Custom config overlays that replace the default one (e.g., a
       `docker-compose.override.yaml` that sets `FOCA_CONFIG_OVERLAY`, or a
       `config.local.yaml`) must set these keys too, or the app refuses to
       start. If you deployed a copy of the Helm chart with a config overlay
       of its own (as the 0.5.0 deployment README described), move that
       overlay's content into `config` and drop your template changes: the
       chart sets `FOCA_CONFIG_OVERLAY` itself.
    5. Restrictions of writes in front of the app (e.g., methods allowed
       only from some addresses at the ingress controller) are no longer
       needed for access control; keep them if you want both, and at least
       until the upgrade is complete: during a rolling update, pods of the
       old version still accept writes without a token.

  FOCA's service clients are not supported (the app refuses to start with
  them). The rules of access control are stored in the collection
  `policy_rules` of the app's database; FOCA's permissions API is served at
  `/admin/access-control/` (see [Permissions
  API](operations.md#permissions-api)). Docker Compose trusts a fictitious
  identity provider (`config.dev.yaml`, which requires no admins and
  verifies no audiences), so writes are refused until you set yours in a
  local override (Compose passes `TRS_FILER_CONFIG_OVERLAY`, if set, to the
  app as `FOCA_CONFIG_OVERLAY`, which lists the overlays); for
  local development without an identity provider, see [Running without
  authentication](development.md#running-without-authentication).
- **Helm chart (breaking):** the chart is a thin chart over FOCA's library
  chart `foca-common`, with camelCase values, and **releases of earlier
  charts can't be upgraded**: uninstall them and install the new chart,
  moving the data, as described in [From earlier
  charts](deployment.md#from-earlier-charts) (`helm upgrade` fails for
  them). Rendering fails for the earlier values, which are renamed or
  removed:
    - `host_name` is `hostName`, `trs_filer` is `trsFiler`, and
      `trs_filer.config` is the top-level `config`.
    - `trs_filer.image` is split into `trsFiler.image` (by default
      `docker.io/elixircloud/trs-filer`) and `trsFiler.tag` (by default
      the chart's `appVersion`: `dev` in the repository, the release
      version in released charts).
    - `trs_filer.appName` is removed: resources are named after the
      release (`<app>`, e.g., `trs-filer`, and `<app>-mongodb` for
      MongoDB, was `mongodb-<appName>`; `fullnameOverride` sets `<app>`),
      with the standard labels instead of `app: <appName>` (see [Names and
      labels](deployment.md#names-and-labels)).
    - The config Job, its ServiceAccount, Role and RoleBinding
      (`<appName>-configurer`) and `apiServer` are removed: the chart
      renders the config overlay (ConfigMap `<app>-config`) itself, and no
      pod gets a service account token. The image has no `curl`, `jq`, `yq`
      or `update-config-map.sh` any more.
    - `trs_filer.forwardedAllowIps` (by default `*`) is removed: Gunicorn
      trusts `X-Forwarded-*` headers from the local host only, so the
      `self_link` and `next_page` headers of listings get `http` behind a
      proxy that terminates TLS, until `FORWARDED_ALLOW_IPS` is set to the
      proxy's addresses in `trsFiler.extraEnv` (see [Forwarded
      headers](deployment.md#forwarded-headers)). The `url` of tools comes
      from `hostName` and keeps `https`.
    - `mongodb.dbName` (by default `trs-filer-db`) is removed: the app's
      database is `trsStore`, that of the base config, also for the rules
      of access control; the restore moves the data there.
      `mongodb.volumeSize` is `mongodb.persistence.size`.

  New values: `trsFiler.gunicorn` (Gunicorn's settings), `trsFiler.replicas`
  with a PodDisruptionBudget, `trsFiler.extraEnv`, `extraEnvFrom` and
  `rolloutOnSecrets`, probes (`trsFiler.probePath` and the probe specs),
  `trsFiler.preStopSleepSeconds`, a Gateway API HTTPRoute
  (`trsFiler.httpRoute`), `mongodb.persistence` and an external MongoDB
  (`mongodb.enabled: false`); `values.schema.json` checks the values (see
  [Deployment](deployment.md)). The chart in the repository needs `helm
  dependency build deployment` before installing; released charts contain
  the library chart.

## From 0.4.0

TRS-Filer now runs on FOCA 0.22 (from 0.19; see FOCA's migration guides
for [0.20](https://foca.readthedocs.io/en/v0.21.0/migration-0.20/),
[0.21](https://foca.readthedocs.io/en/v0.21.0/migration-0.21/) and
[0.22](https://foca.readthedocs.io/en/v0.22.0/migration-0.22/)). Check
clients, custom configs and log checks:

- Requests that fail the validation of the API specification keep the
  validator's reason as `detail` (`exceptions.validation_reasons`). Where
  the invalid fields are known, their responses gain the members `type`
  (FOCA's problem type, a URL ending in `/problems/invalid-request/`),
  `code` (`invalid-request`) and `errors`, which lists them.
- Logs: requests (`Incoming request`) name the route of the request instead
  of its path, and rejected requests (`Request rejected`) name the locations
  and codes of their invalid fields (otherwise the mapped `detail`) instead
  of the validator's reason. Paths and reasons are logged only at `DEBUG`,
  so rejected values no longer show up at `INFO`. FOCA warns once per
  worker of what it deprecates ahead of its release on ASGI.
- Requests that TRS-Filer itself refuses (e.g., `limit=0`, deleting the
  last version of a tool, or a tool class that tools use) get their reason
  as `detail` instead of the generic `The request is malformed.` (see
  [Errors](api.md#errors)); clients that compared `detail` with the generic
  text must check `status` instead.
- Query parameters that an operation doesn't declare now give `400 Bad
  Request` on all operations, also on `GET /service-info`,
  `GET /toolClasses`, `POST /tools` and `POST /toolClasses`, which ignored
  them (see [Errors](api.md#errors)).
- JSON bodies with unpaired surrogates (e.g., `"\ud800"`) get `400 Bad
  Request` before TRS-Filer sees them, with a `detail` that names neither
  the field nor the value.
- Custom configs: string values with `${...}` now reference environment
  variables (an unset variable stops the app), and `$$` stands for a
  literal `$`; write `$$` for each `$` that's meant literally there. A `log`
  section whose handlers or `root` name a handler or filter that it doesn't
  configure stops the app (e.g., `handlers` replaced by one of your own,
  without `root.handlers`). Errors of the custom configuration (`custom`)
  name the setting and the reason, without the invalid value.
- MongoDB clients time out after 5 seconds (server selection and connect,
  down from 30 and 20), so with MongoDB down, startup and requests fail
  sooner; set them in `db.client_options` or `MONGO_URI` if MongoDB takes
  longer in your deployment.
- Responses have the header `X-Request-ID`, generated by the app, which log
  records carry too; a request ID set by a proxy in front of the app isn't
  used (see FOCA's `server.request_id.trust_incoming`).
- The image has no pip (and no uv): images derived from the TRS-Filer image
  that run `pip install` must install with uv instead, mounted from a
  pinned stage (see FOCA's migration guide for 0.20). The image installs
  the locked versions of its dependencies (`uv.lock`), with hash checks.
- Helm chart, security contexts: all pods run as non-root users with a
  read-only root file system ([Security
  context](deployment.md#security-context)). MongoDB runs as user and
  group 999 from the start (before, its entrypoint started as root and
  switched to that user); the data that it wrote belongs to that user
  already, and `fsGroup` keeps the volume writable for it (with storage
  that applies `fsGroup`).
- Helm chart, NetworkPolicy: only the app may connect to MongoDB ([Network
  policies](deployment.md#network-policies)). Other workloads that connect
  to MongoDB (e.g., backups) need a policy of their own, or set
  `mongodb.networkPolicy.enabled: false`.
- Helm chart, **MongoDB authentication (breaking):** MongoDB requires
  credentials from an existing Secret (`mongodb.auth.existingSecret`), and
  rendering fails without it. Existing databases have no users, and
  MongoDB creates none on an existing volume: create the Secret and the
  users **before** the upgrade, as described in
  [Authentication](deployment.md#authentication), or set
  `mongodb.auth.enabled: false` to keep MongoDB without authentication.
- Helm chart, upgrades with `--reuse-values` keep the earlier settings (no
  security contexts, no NetworkPolicy, no authentication unless they
  name the Secret with `mongodb.auth.existingSecret`): pass your values
  file instead, or use `--reset-then-reuse-values` (see
  [Upgrades](deployment.md#upgrades)).
- Helm chart: the configuration Job's ServiceAccount is bound to a Role
  with only the rights that the Job uses (Role and RoleBinding
  `<appName>-configurer`), instead of the ClusterRole `admin` (RoleBinding
  `admin-<appName>-configurer`, which the upgrade removes). The Job finds
  the app's base config through the installed package, instead of a path
  that depended on the image's Python version, and works with older images
  too. With images of this release or later, it fails if the API server
  refuses reading or patching the ConfigMap or listing pods (before, it
  reported success): copies of the chart that add their own steps to the
  Job may need more rights in the Role. The Job restarts the pods with the
  label `app: <appName>` (the app's), no longer all pods whose names start
  with `<appName>-`.
- Helm chart: `trs_filer.imagePullPolicy` sets the pull policy of the app's
  image (app and configuration Job); the default, `Always`, is the earlier
  behaviour, also for upgrades with `--reuse-values`.
- Helm chart: `trs_filer.forwardedAllowIps` sets the addresses that
  forwarded headers are trusted from; the default, `*`, is the earlier
  behaviour (see [Forwarded headers](deployment.md#forwarded-headers)).
- Config: `custom.access_control.tool_classes` sets who may add tool
  classes; its default, `open`, is the earlier behaviour (see [Adding tool
  classes](configuration.md#adding-tool-classes)).

## Configuration

TRS-Filer runs on FOCA 0.23 and Python 3.13. Custom configs must apply the
config changes of FOCA 0.14 to 0.23 (see the [FOCA release
notes](https://github.com/elixir-cloud-aai/foca/releases) and migration
guides), e.g., `exceptions.mapping` instead of the old exception members,
no `server.environment` or `server.use_reloader`, and no top-level
`plugins` section other than FOCA's (validated since FOCA 0.18, with
unknown keys refused; TRS-Filer loads no plugins);
`server.max_content_length` must be set (see [Request size
limit](configuration.md#request-size-limit)). Configs are best written as
overlays of the base config (see [Configuration](configuration.md)), which
the image no longer has at `/app/trs_filer/config.yaml` (the package is
installed, not copied).

- The identifier character sets (`custom.tool.id.charset`,
  `custom.version.id.charset`, `custom.toolclass.id.charset`) list the
  characters themselves (e.g., `ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789`);
  expressions such as `string.ascii_uppercase + string.digits` are rejected
  on startup.
- Identifiers of tool classes registered with the tool class endpoints
  follow `custom.toolclass.id` (they used `custom.tool.id`): by default
  lower-case letters and digits.
- `custom.service` (the [public URL](configuration.md#public-url)) defaults
  to `http://localhost:8080`; deployments set their own.
- File contents are retrieved from URLs as configured in
  `custom.remote_files` (see [Remote files](configuration.md#remote-files)):
  `http` URLs are only retrieved if `http` is added to `schemes`, hosts that
  resolve to addresses that are not public only if listed in
  `allowed_hosts`, and responses other than `2xx` or larger than `max_size`
  fail the registration with `400 Bad Request` (before, error pages were
  stored as content).

## Service info

`POST /service-info` and the `service_info` collection are removed: the
service info is configured in `service_info.service` (FOCA's section, see
[Service info](configuration.md#service-info)); `custom.service_info` is
rejected on startup. The collection stays in existing databases, unused;
drop it if you like.

## API

- `GET /tools`: `limit=0` gave all tools; it now gives `400 Bad Request`,
  as do other limits below 1. Invalid `offset` and `limit` values give `400`
  instead of `422`. `limit` is at most 1000 (larger values are reduced to
  1000). `next_page` is omitted on the last page, and `last_page` is counted
  in steps of `limit` from the requested offset. Filters of versions and
  images apply to the same version and image (they overwrote each other).
  The links `next_page` and `last_page` keep the filters of the request
  (they had only `offset` and `limit`). An empty `author` matches only empty
  authors (it matched all tools), and the filter `tags` filters by the
  tags of tools (it was ignored). See [Listing
  tools](api.md#listing-tools).
- Registering or replacing a tool no longer changes an existing tool class:
  the tool stores a copy of the stored tool class instead of the one it was
  sent with. With `custom.toolclass.validation: true`, a tool with an
  unknown tool class is no longer stored (before, it was stored although the
  request failed with `400`). See [Tool
  classes](configuration.md#tool-classes).
- Replacing a tool, version or tool class with an identical one succeeds
  (it failed with `500`).
- Replacing tools and versions increments their `meta_version` (it stayed
  at the initial value), as configured in
  `custom.tool.meta_version.increment` and
  `custom.version.meta_version.increment`. Adding, replacing or deleting a
  version also increments the `meta_version` of its tool, so clients see
  that the tool changed; set
  `custom.tool.meta_version.on_version_change: false` to keep the tool's
  meta version unchanged on version changes. See [Meta
  versions](configuration.md#meta-versions).
- Deleting the last version of a tool gives `400 Bad Request`; delete the
  tool instead.
- Versions without `is_production` are registered as non-production
  versions (they failed with `500`).

## Errors

Errors are problem details (`title`, `status`, `detail`), sent as
`application/json`, instead of objects with `message` and `code` (see
[Errors](api.md#errors)). Requests that the validation of the API
specification rejects get the reason as `detail` (e.g., `'FOO' is not one
of ['CWL', ...]`), no longer the generic `The request is malformed.`; set
`exceptions.validation_details: false` to keep the generic one (see
[Errors](configuration.md#errors)). Requests that TRS-Filer itself refuses
(e.g., `limit=0`, deleting the last version of a tool, or a tool class that
tools use) get their reason as `detail`, too (see [Errors](api.md#errors));
before, the reason was only logged.

## Database

Without `MONGO_DBNAME`, the image uses the database `trsStore` (as
configured) instead of `trs-filer-db`. Deployments with data in
`trs-filer-db` (e.g., the Docker Compose setup of earlier versions) set
`MONGO_DBNAME=trs-filer-db`, or move the data (see below). The Helm charts
up to 0.5.0 set it (value `mongodb.dbName`, by default `trs-filer-db`); the
current chart uses `trsStore` (see [Helm chart](#helm-chart)).

MongoDB 4.4 or later is required (Docker Compose and the Helm chart use
7.0). MongoDB 7.0 can't open data files of 3.6, which earlier Compose
setups used: migrate them with `mongodump` (with MongoDB 3.6) and
`mongorestore` (with 7.0), e.g., into `trsStore`, or upgrade one major
version at a time. For the Helm chart, see [Helm chart](#helm-chart).

## Image

- Image tags: `latest` is the highest stable release from the first release
  with the new release process on, no longer the head of `dev`, which is
  tagged `dev` (and `sha-<commit>` per commit); dated tags are no longer
  published. Pin a release (`X.Y.Z`) in deployments (see [Versioning and
  releases](development.md#versioning-and-releases)). Images published by
  the new workflows are scanned, attested and signed (see [Verifying images
  and charts](operations.md#verifying-images-and-charts)).
- Gunicorn is configured by `trs_filer/gunicorn_config.py` and the
  environment variable `GUNICORN_CMD_ARGS` (e.g., `--workers 2`; see
  [Server](configuration.md#server)); `GUNICORN_PROCESSES`,
  `GUNICORN_THREADS` and `TRS_CONFIG` are no longer read, and Gunicorn
  always binds `0.0.0.0:8080`.
- Forwarded headers (`X-Forwarded-*`) are trusted from Gunicorn's default
  (`127.0.0.1`) only, no longer from every client: behind a proxy that
  terminates TLS, set `FORWARDED_ALLOW_IPS` to its addresses (with the
  Helm chart, in `trsFiler.extraEnv`, see [Forwarded
  headers](deployment.md#forwarded-headers); the charts up to 0.5.0 set it,
  by default to `*`).
- The image runs as user 1000 (also with a read-only root file system and a
  writable `/tmp`) and reports its version (e.g., in the service info) from
  the build argument `SETUPTOOLS_SCM_PRETEND_VERSION`.

## Docker Compose

The service is named `trs-filer` (was `trs`), and the app is published at
`http://localhost:8080/ga4gh/trs/v2/` on the loopback interface only (was
port 80 on all interfaces). MongoDB data lives in the named volume
`mongodb-data` instead of `../data/trs/db`: migrate it with `mongodump` and
`mongorestore` if needed (see [Database](#database)). The Compose setup
applies the overlay `config.dev.yaml` (see [Local
overrides](configuration.md#local-overrides)).

## Helm chart

Releases attach the chart (see [Verifying images and
charts](operations.md#verifying-images-and-charts)). Releases of earlier
charts (that of the tag `v0.3.0`, of 0.4.0 and 0.5.0, and those on `dev`
before the library chart) can't be upgraded to the current chart: uninstall
them and install it, moving the data by dump and restore, as described in
[From earlier charts](deployment.md#from-earlier-charts). Check two things
**before** you start, as charts before 0.4.0 differ from the commands
there:

- **The names of MongoDB's Deployment and claim** (`kubectl get deploy,pvc
  -n <namespace>`): the charts up to 0.5.0 called them `mongodb-<appName>`
  (`trs_filer.appName`, by default `trs-filer`); charts before July 2024,
  including that of `v0.3.0`, called them `mongodb`. Use that name (`OLD`
  below) in the dump. Charts before 0.4.0 ran MongoDB without
  authentication: leave out `-u`, `-p` and `--authenticationDatabase` in
  the dump, and create the Secret with MongoDB's credentials before
  installing the current chart (see
  [Installation](deployment.md#installation)).
- **The running MongoDB version**: the chart runs MongoDB 7.0
  (`mongodb.image`, see [Version](deployment.md#version)). Charts before
  January 2026 ran `mongo:3.6`; the chart on `dev` since then ran the
  floating `mongo:noble` (MongoDB 8.2, 8.3 or 9.0, depending on when the pod
  last started). The dump and restore move the data to the new version;
  check the version (and the feature compatibility version) of the running
  server (with `mongosh`, or `mongo`, the old shell, in images before 6.0):

    ```bash
    kubectl exec deploy/OLD -n <namespace> -- sh -c \
      '"$(command -v mongosh || echo mongo)" --quiet --eval "printjson({version: db.version(), fcv: db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1}).featureCompatibilityVersion})"'
    ```

    If MongoDB doesn't start any more (`CrashLoopBackOff`, e.g., after a
    restart pulled a newer `mongo:noble` that can't open the data), its log
    names the versions (`kubectl logs deploy/OLD -n <namespace>
    --previous`): set an image that can open the data (e.g., `kubectl set
    image deploy/OLD OLD=docker.io/library/mongo:8.3 -n <namespace>`; the
    container is named after the Deployment), wait until it runs, then
    dump. If the restore into 7.0 fails on the options of an index, restore
    with `--noIndexRestore`: the app creates its indexes on startup; or set
    `mongodb.image` to the dumped major and minor version (mind the kernel
    requirements of 8.x, see [Version](deployment.md#version)).

Also count the documents of each collection before the dump, for a
comparison after the restore (in `trs-filer-db`, and in `trsStore` after
it):

```bash
kubectl exec deploy/OLD -n <namespace> -- sh -c \
  '"$(command -v mongosh || echo mongo)" --quiet trs-filer-db --eval "db.getCollectionNames().forEach(c => print(c, db[c].countDocuments ? db[c].countDocuments({}) : db[c].count()))"'
```

The claim `mongodb` of charts before July 2024 isn't annotated to be kept:
before uninstalling, keep its volume as a fallback by setting the reclaim
policy of its PersistentVolume to `Retain`
(`kubectl patch pv "$(kubectl get pvc mongodb -n <namespace> -o
jsonpath='{.spec.volumeName}')" -p '{"spec": {"persistentVolumeReclaimPolicy":
"Retain"}}'`), and delete the volume once the new release works (`kubectl
delete pv <name>` deletes only the PersistentVolume object: delete its
storage, e.g., the disk, with your storage provider). The chart of the tag
`v0.3.0` deploys the app with the API `extensions/v1beta1`, which
Kubernetes no longer serves since 1.16; if `helm uninstall` fails because
the release's manifest contains removed APIs, map them first with the
[mapkubeapis](https://github.com/helm/helm-mapkubeapis) plugin (`helm
mapkubeapis trs-filer -n <namespace>`). The `service_info` collection of
the dump is no longer used (see [Service info](#service-info)).

### Values

Rendering fails for the values of the charts up to 0.5.0 (see [From
earlier charts](deployment.md#from-earlier-charts) for the renamed ones).
Values of the chart of `v0.3.0` have no successor: `clusterType` is removed,
as the chart creates an Ingress (`trsFiler.ingress.enabled`, by default
`true`; HTTPS via cert-manager with `trsFiler.ingress.https`), a Gateway
API HTTPRoute (`trsFiler.httpRoute`) or, with neither, an OpenShift Route
(with TLS at the router), as `v0.3.0` did with `clusterType: openshift` (see
[Exposing the app](deployment.md#exposing-the-app)). `hostName` has no
default (`host_name` was a test host). The default image is
`elixircloud/trs-filer` (was `lvarin/trs-filer:0.1.0`), and MongoDB's is
`docker.io/library/mongo:7.0` (was `mongo:3.6`, and `mongo:noble` on `dev`).
The chart in the repository has the placeholder version `0.0.0` (was
`2.0.0`); released charts have the release's version.

## Images from `dev` since FOCA 0.17

Images from `dev` built since the move to FOCA 0.17 (`dev`, `sha-<commit>`)
ran on an unreleased FOCA commit; the first release since then runs on
FOCA 0.19. Besides the `detail` of rejected requests (see [Errors](#errors)), the startup warning
about the placeholders of the service info changes: FOCA logs it
(logger `foca.api.service_info`) while `id`, `organization.url`,
`contactUrl` or `documentationUrl` are in a reserved example domain (RFC
2606, e.g., `org.example.trs` or `https://trs.example.org`), instead of the
app (logger `trs_filer.app`), which warned of the placeholders `id` and
`organization` (name or URL) of the base config only; a placeholder
`organization.name` is no longer warned of. FOCA's plugin store
(collection `plugin_store`) and plugin listing are for gateway apps:
TRS-Filer creates no collections or indexes beyond its own, so its
database user needs no new rights.
