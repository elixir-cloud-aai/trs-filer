# Operations

## Components

A deployment of TRS-Filer consists of:

- the app (the TRS API), served by Gunicorn (see
  [Server](configuration.md#server));
- MongoDB, which stores the tools, with their versions and files, and the
  tool classes (database `trsStore`, or `trs-filer-db` with the Helm chart,
  collections `tools` and `toolclasses`; see
  [Database](configuration.md#database)).

The Docker Compose setup and the [Helm chart](deployment.md) run both.

## Logs

The app logs to standard error (section `log` of the config, by default at
level `INFO`): each request to the API (method, path and client address,
not the body) and the status of its response, registered and replaced
objects, and errors, e.g., the reasons why the content of a file could not
be retrieved from its URL (which clients don't get, see [Remote
files](configuration.md#remote-files)). Read them with
`docker compose logs` or `kubectl logs`.

## Health checks

The image checks its health by requesting the Swagger UI
(`/ga4gh/trs/v2/ui/`), which needs neither the database nor authentication;
set `HEALTHCHECK_URL` if Gunicorn's port, the API base path or the Swagger
UI setting changes. On startup, each Gunicorn worker creates the app and
checks the config (e.g., the request size limit and the custom config);
if this fails, Gunicorn exits.

## Backups

All state is in MongoDB: back up the database (`trsStore`, or the one set in
`MONGO_DBNAME`, e.g., `trs-filer-db` with the Helm chart) with
[`mongodump`](https://www.mongodb.com/docs/database-tools/mongodump/), e.g.,
in the Docker Compose setup:

```bash
docker compose exec -T mongodb mongodump --db trsStore --archive > trs-filer.archive
docker compose exec -T mongodb mongorestore --archive < trs-filer.archive
```

The base config creates unique indexes on the identifiers (`id`) of tools
and tool classes on startup.
