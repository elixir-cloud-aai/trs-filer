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

`mongodump` reads the collections one after the other, without a
point-in-time snapshot, so a registration during the dump can leave the
archive inconsistent: stop writes (e.g., stop the app with
`docker compose stop trs-filer`) while dumping, or use a backup method of
MongoDB that takes consistent snapshots.

The base config creates unique indexes on the identifiers (`id`) of tools
and tool classes on startup.

## Verifying images and charts

From the first release on, images on Docker Hub (`elixircloud/trs-filer`)
are built by this repository's workflows on GitHub Actions, with an SBOM and
the build provenance attached as attestations, a [GitHub artifact
attestation](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
of their provenance, and a keyless [Sigstore](https://www.sigstore.dev/)
signature. To check that an image was built by the release workflow, run
(with the [GitHub CLI](https://cli.github.com/) or
[cosign](https://docs.sigstore.dev/cosign/system_config/installation/) 3 or
later, which reads the signatures in the Sigstore bundle format):

```bash
gh attestation verify oci://docker.io/elixircloud/trs-filer:{{ version }} \
    --repo elixir-cloud-aai/trs-filer \
    --signer-workflow elixir-cloud-aai/trs-filer/.github/workflows/release.yml \
    --source-ref refs/tags/v{{ version }}
cosign verify docker.io/elixircloud/trs-filer:{{ version }} \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity https://github.com/elixir-cloud-aai/trs-filer/.github/workflows/release.yml@refs/tags/v{{ version }}
```

These are the commands for the latest release, `{{ version }}`: replace it
with the version to verify. `--source-ref` and the ref in
`--certificate-identity` check that the workflow ran for the release tag,
not for another branch. Images of commits on `dev` (`dev`, `sha-<commit>`)
are signed and attested by the CI workflow instead: use `--signer-workflow
elixir-cloud-aai/trs-filer/.github/workflows/ci.yml`,
`--source-ref refs/heads/dev` and `--certificate-identity
https://github.com/elixir-cloud-aai/trs-filer/.github/workflows/ci.yml@refs/heads/dev`.
Images published before the workflows signed them (the dated tags and the
`latest` image of earlier versions, and `dev` and `sha-<commit>` images
built before signing was added, see
[#134](https://github.com/elixir-cloud-aai/trs-filer/issues/134)) have no
signature or attestation. To show an image's SBOM or
provenance, run:

```bash
docker buildx imagetools inspect docker.io/elixircloud/trs-filer:{{ version }} \
    --format '{{ json .SBOM }}'
docker buildx imagetools inspect docker.io/elixircloud/trs-filer:{{ version }} \
    --format '{{ json .Provenance }}'
```

The Helm chart attached to a release (`trs-filer-{{ chart_version }}.tgz`)
has a GitHub artifact attestation of its provenance and a Sigstore bundle
with its signature (`trs-filer-{{ chart_version }}.tgz.sigstore.json`,
attached too):

```bash
gh release download v{{ version }} --repo elixir-cloud-aai/trs-filer \
    --pattern 'trs-filer-{{ chart_version }}.tgz*'
gh attestation verify trs-filer-{{ chart_version }}.tgz \
    --repo elixir-cloud-aai/trs-filer \
    --signer-workflow elixir-cloud-aai/trs-filer/.github/workflows/release.yml \
    --source-ref refs/tags/v{{ version }}
cosign verify-blob trs-filer-{{ chart_version }}.tgz \
    --bundle trs-filer-{{ chart_version }}.tgz.sigstore.json \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    --certificate-identity https://github.com/elixir-cloud-aai/trs-filer/.github/workflows/release.yml@refs/tags/v{{ version }}
```

Images are scanned for known vulnerabilities with [Trivy](https://trivy.dev/)
in CI and again before a release is published (both fail on fixable
critical and high vulnerabilities), and the `latest` image weekly. The
repository's code scanning alerts show the findings that have a fix, which
the maintainers can act on; findings without a fix (often OS packages of
the base image) appear there once a fix is released. The weekly scan also
keeps a full report, those findings included, as a workflow artifact of
each run. The published images (releases and `dev`) are the scanned ones:
the workflows push each image by digest, untagged, scan exactly that
digest, and only if the scan passes (no fixable critical or high
vulnerabilities, except accepted ones) sign and tag it (see [Versioning and
releases](development.md#versioning-and-releases)).

Images published to another Docker Hub organization (forks that set
`DOCKERHUB_ORG`) are verified the same way, with that organization and the
fork's repository in place of `elixircloud` and `elixir-cloud-aai/trs-filer`.
