# Upgrading

The [release notes](changelog.md) list the breaking changes of each release
and how to upgrade. This page describes how existing setups and data are
affected by the changes since the tag `v0.3.0` (2023) and the images
published from `dev` before the move to FOCA 0.17 (tagged `latest` and by
date, with FOCA 0.12).

## Configuration

TRS-Filer runs on FOCA 0.17 and Python 3.13. Custom configs must apply the
config changes of FOCA 0.14 to 0.17 (see the [FOCA release
notes](https://github.com/elixir-cloud-aai/foca/releases) and migration
guides), e.g., `exceptions.mapping` instead of the old exception members,
and no `server.environment` or `server.use_reloader`;
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
  authors (it matched all tools), and the unsupported filter `tags` gives
  `400 Bad Request` (it was ignored). See [Listing
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
  `custom.version.meta_version.increment`; see [Meta
  versions](configuration.md#meta-versions).
- Adding, replacing or deleting a version also increments the
  `meta_version` of its tool (it changed only when the tool was replaced),
  so clients see that the tool changed. Set
  `custom.tool.meta_version.on_version_change: false` to keep the tool's
  meta version unchanged on version changes.
- Deleting the last version of a tool gives `400 Bad Request`; delete the
  tool instead.
- Versions without `is_production` are registered as non-production
  versions (they failed with `500`).

## Errors

Errors are problem details (`title`, `status`, `detail`), sent as
`application/json`, instead of objects with `message` and `code` (see
[Errors](api.md#errors)).

## Database

Without `MONGO_DBNAME`, the image uses the database `trsStore` (as
configured) instead of `trs-filer-db`. Deployments with data in
`trs-filer-db` (e.g., the Docker Compose setup of earlier versions) set
`MONGO_DBNAME=trs-filer-db`, or move the data (see below); the Helm chart
sets it already (value `mongodb.dbName`, by default `trs-filer-db`).

MongoDB 4.4 or later is required (Docker Compose uses 7.0). MongoDB 7.0
can't open data files of 3.6, which earlier Compose setups used: migrate
them with `mongodump` (with MongoDB 3.6) and `mongorestore` (with 7.0),
e.g., into `trsStore`, or upgrade one major version at a time.

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
  chart sets it).
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
