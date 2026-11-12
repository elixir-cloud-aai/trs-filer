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
    2. Add to your config overlay (with the Helm chart: the new value
       `trs_filer.config`, without which rendering fails)
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
       overlay's content into `trs_filer.config` and drop your template
       changes: the chart now sets `FOCA_CONFIG_OVERLAY` itself. The first
       upgrade restarts the app (new config map).
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
  contexts](deployment.md#security-contexts)). MongoDB runs as user and
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
`MONGO_DBNAME=trs-filer-db`, or move the data (see below); the Helm chart
sets it already (value `mongodb.dbName`, by default `trs-filer-db`).

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
  terminates TLS, set `FORWARDED_ALLOW_IPS` to its addresses (the Helm
  chart sets it, by default to `*`; narrow it with the value
  `trs_filer.forwardedAllowIps`, see [Forwarded
  headers](deployment.md#forwarded-headers)).
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
charts](operations.md#verifying-images-and-charts)); upgrade with it, and
your values file, as described in [Deployment](deployment.md#upgrades).
Releases installed from the chart in the repository before (from the tag
`v0.3.0` or from `dev`) may need more steps, depending on two things, which
you check **before** the upgrade:

- **The name of MongoDB's claim** (`kubectl get pvc -n <namespace>`): the
  chart calls MongoDB's Deployment, Service and PersistentVolumeClaim
  `mongodb-<appName>` (`trs_filer.appName`, by default `trs-filer`); charts
  before July 2024, including that of `v0.3.0`, called them `mongodb`. Helm
  deletes resources that are no longer in the chart, so upgrading such a
  release **deletes the claim `mongodb`** and, with the reclaim policy
  `Delete` (the default of most storage classes), its volume and the data,
  and starts MongoDB on a new, empty claim.
- **The running MongoDB version**: the chart runs MongoDB 7.0
  (`mongodb.image`, see [MongoDB](deployment.md#mongodb)). Charts before
  January 2026 ran `mongo:3.6`, whose data files 7.0 can't open; the chart
  on `dev` since then ran the floating `mongo:noble` (MongoDB 8.2, 8.3 or
  9.0, depending on when the pod last started), whose data 7.0 can't open
  either (MongoDB doesn't support downgrades). Check the version (and the
  feature compatibility version) of the running server (with `mongosh`,
  or `mongo`, the old shell, in images before 6.0); `OLD` is the MongoDB
  Deployment (`mongodb` or `mongodb-<appName>`):

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
    continue here.

Then:

- **Claim `mongodb-<appName>` and MongoDB 7.0:** upgrade as usual.
- **Claim `mongodb-<appName>` and MongoDB 8.x or 9.0:** set `mongodb.image`
  in the values file to the running major and minor version (e.g.,
  `docker.io/library/mongo:8.2`, as `db.version()` reports it; mind the
  kernel requirements of 8.x, see [MongoDB](deployment.md#mongodb)) and
  upgrade; or move the data to 7.0 by dump and restore as below.
- **Otherwise** (claim `mongodb`, or MongoDB 3.6): dump the data before the
  upgrade and restore it afterwards, as below.

### Dump and restore

The app is down from the first to the last step. The commands are for the
release `trs-filer` with the default `trs_filer.appName` (`trs-filer`, the
name of the app's Deployment and the label `app` of its pods; MongoDB's
Deployment and claim are `mongodb-trs-filer`) and database
(`trs-filer-db`, `mongodb.dbName`); replace them if yours differ. `OLD` is
the MongoDB Deployment, and claim, before the upgrade (`mongodb` or
`mongodb-trs-filer`). Clients can reach the app whenever it runs, also with
the empty database between the upgrade (step 4, which starts the app again)
and step 5, and the restore replaces what they write then: keep clients
away during the migration (e.g., by blocking the host at a proxy in front
of the cluster, or in a maintenance window).

1. Stop the app and wait until its pod is gone, so that the data doesn't
   change during the dump:

    ```bash
    kubectl scale deploy/trs-filer -n <namespace> --replicas=0
    kubectl wait pod -l app=trs-filer -n <namespace> --for=delete --timeout=120s
    ```

2. Count the documents of each collection, for a comparison after the
   restore, and dump the database to a local file; check that `mongodump`
   succeeds (the command prints `Dump OK`):

    ```bash
    kubectl exec deploy/OLD -n <namespace> -- sh -c \
      '"$(command -v mongosh || echo mongo)" --quiet trs-filer-db --eval "db.getCollectionNames().forEach(c => print(c, db[c].countDocuments ? db[c].countDocuments({}) : db[c].count()))"'
    kubectl exec deploy/OLD -n <namespace> -- \
      mongodump --quiet --db trs-filer-db --archive > trs-filer-db.archive \
    && echo "Dump OK"
    ```

3. Keep the old volume as a fallback: set the reclaim policy of its
   PersistentVolume to `Retain`, which keeps the volume (with the data) when
   its claim is deleted:

    ```bash
    kubectl patch pv "$(kubectl get pvc OLD -n <namespace> \
      -o jsonpath='{.spec.volumeName}')" \
      -p '{"spec": {"persistentVolumeReclaimPolicy": "Retain"}}'
    ```

    - With the claim `mongodb`, also annotate the claim, so that Helm keeps
      it (Helm checks the annotation on the claim in the cluster before
      deleting it on upgrades):
      `kubectl annotate pvc mongodb -n <namespace> helm.sh/resource-policy=keep`.
    - With the claim `mongodb-trs-filer` (and MongoDB 3.6, or a version to
      leave), the upgrade keeps the claim, so MongoDB would start on the old
      data files; delete MongoDB's Deployment and the claim (the volume is
      retained), so that the upgrade creates them anew, with an empty volume:
      `kubectl delete deploy/mongodb-trs-filer pvc/mongodb-trs-filer -n <namespace>`.

4. Create the Secret with MongoDB's credentials (see
   [Authentication](deployment.md#authentication); MongoDB creates the users
   on the new, empty volume), update the values file (see
   [Values](#values); with `mongodb.auth.existingSecret`) and upgrade the
   release with the chart of the release, e.g.:

    ```bash
    helm upgrade trs-filer trs-filer-{{ chart_version }}.tgz -n <namespace> -f values.yaml
    ```

    The chart of the tag `v0.3.0` deploys the app with the API
    `extensions/v1beta1`, which Kubernetes no longer serves since 1.16; if
    `helm upgrade` fails because the release's manifest contains removed
    APIs, map them first with the
    [mapkubeapis](https://github.com/helm/helm-mapkubeapis) plugin
    (`helm mapkubeapis trs-filer -n <namespace>`).

5. Stop the app again, so that it doesn't write during the restore, and
   wait until MongoDB has initialized the new volume (its entrypoint first
   runs a temporary server for the init script, then starts MongoDB) and
   accepts connections:

    ```bash
    kubectl scale deploy/trs-filer -n <namespace> --replicas=0
    kubectl wait pod -l app=trs-filer -n <namespace> --for=delete --timeout=120s
    timeout 300 sh -c 'until kubectl logs deploy/mongodb-trs-filer -n <namespace> \
      | grep -q "ready for start up"; do sleep 2; done' \
    && timeout 120 sh -c 'until kubectl exec deploy/mongodb-trs-filer -n <namespace> -- \
      mongosh --quiet --eval "db.runCommand({ping: 1}).ok"; do sleep 2; done' \
    && echo "MongoDB ready"
    ```

    Continue only if `MongoDB ready` is printed; otherwise check MongoDB's
    pod and log (`kubectl get pods`, `kubectl logs`): e.g., after a failed
    init, MongoDB restarts without it and doesn't print the line.

6. Restore the dump, replacing the collections that the app has created,
   and count the documents again:

    ```bash
    kubectl exec -i deploy/mongodb-trs-filer -n <namespace> -- sh -c \
      'mongorestore --quiet --drop --archive \
        -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
        --authenticationDatabase admin' < trs-filer-db.archive \
    && kubectl exec deploy/mongodb-trs-filer -n <namespace> -- sh -c \
      'mongosh --quiet trs-filer-db \
        -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
        --authenticationDatabase admin \
        --eval "db.getCollectionNames().forEach(c => print(c, db[c].countDocuments({})))"'
    ```

    (With `mongodb.auth.enabled: false`, leave out `-u`, `-p` and
    `--authenticationDatabase`.)

    If the restore fails on the options of an index, restore with
    `--noIndexRestore`: the app creates its indexes on startup. The restore
    is repeatable (`--drop`).

7. Only if the restore succeeded and the counts match those of step 2,
   start the app:

    ```bash
    kubectl scale deploy/trs-filer -n <namespace> --replicas=1
    ```

Once the new release works, delete the old claim `mongodb` (if any:
`kubectl delete pvc mongodb -n <namespace>`), the retained volume
(`kubectl delete pv <name>`; this deletes only the PersistentVolume object:
delete its storage, e.g., the disk, with your storage provider) and the
local dump. The `service_info`
collection of the dump is no longer used (see [Service
info](#service-info)).

### Values

Since the chart of `v0.3.0`, the values changed:

- `clusterType` is removed: the chart creates an Ingress
  (`trs_filer.ingress.enabled`, by default `true`; HTTPS via cert-manager
  with `trs_filer.ingress.https`) or, with the Ingress disabled, an
  OpenShift Route (with TLS at the router), as `v0.3.0` did with
  `clusterType: openshift`. `trs_filer.route.enabled` (by default `true`)
  turns the Route off, e.g., for a Route of your own, and
  `trs_filer.route.annotations` sets its annotations (see [Ingress and
  Route](deployment.md#ingress-and-route)).
- `host_name` has no default (it was a test host); set it.
- `trs_filer.image` is `elixircloud/trs-filer` (released charts set the
  release's image), no longer `lvarin/trs-filer:0.1.0`.
- `trs_filer.resources` and `mongodb.resources` set the requests and limits
  of the app and of MongoDB.
- `trs_filer.forwardedAllowIps` (by default `*`, as before; also kept by
  upgrades with `--reuse-values`) sets the addresses whose `X-Forwarded-*`
  headers the app trusts; narrow it (see [Forwarded
  headers](deployment.md#forwarded-headers)).
- `mongodb.image` is `docker.io/library/mongo:7.0` (was `mongo:3.6`, and
  `mongo:noble` on `dev`), pulled as `mongodb.imagePullPolicy` says;
  `mongodb.dbName` sets the app's database (`trs-filer-db` if empty).

The chart annotates MongoDB's claim with `helm.sh/resource-policy: keep`
(see [MongoDB](deployment.md#mongodb)), and replaces MongoDB's pod with the
`Recreate` strategy.
MongoDB's init script (ConfigMap `mongo-init-script-<appName>`, was
`mongo-init-script`) creates the collections of the app's database only
(no `service_info`, and nothing in `trsStore`); it runs on an empty volume
only, so existing databases are not changed. The app gets the MongoDB host
from `MONGO_HOST` (the Service `mongodb-<appName>`), also if the config Job
fails. The chart in the repository has the placeholder version `0.0.0`
(was `2.0.0`); released charts have the release's version.

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
