# API

TRS-Filer implements the [GA4GH Tool Registry Service (TRS)
API](https://github.com/ga4gh/tool-registry-service-schemas) at
`/ga4gh/trs/v2/`, and adds endpoints to register, change and delete tools,
tool versions and tool classes. A deployment's Swagger UI
(`/ga4gh/trs/v2/ui/`) shows all endpoints and lets you try them; the
specification is served at `/ga4gh/trs/v2/openapi.json`.

## Supported TRS version

TRS-Filer implements [TRS
2.0.2](https://github.com/ga4gh/tool-registry-service-schemas/releases/tag/2.0.2),
with the service info of the [GA4GH service info specification
1.0.0](https://github.com/ga4gh-discovery/ga4gh-service-info/releases/tag/v1.0.0).
The service info reports TRS version 2.0.2 (`type.version`); the
specification itself says `info.version: 2.1.0`, as published.

Both specifications are vendored unchanged
([`20250902.4854e2f.openapi.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/api/20250902.4854e2f.openapi.yaml),
[`20200131.11d2c12.service-info.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/api/20200131.11d2c12.service-info.yaml),
named after the date and commit of their source, which the comments of
`api.specs.trs` in `config.yaml` name). TRS-Filer's changes and extensions
are merged into them from
[`additions.openapi.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/api/additions.openapi.yaml),
where `null` removes a key of the vendored files (FOCA's
`merge_null_removes`):

- The app's info: title, description, license and contact (`info.version`
  stays the specification's, not the app's).
- The read operations of TRS (all `GET` endpoints below) and the service
  info are public (`security: []`), so that no token is needed to read (see
  [Access control](access-control.md)).
- TRS's security scheme `BEARER` is an HTTP bearer scheme (`type: http`,
  `scheme: bearer`), as on the TRS `develop` branch, instead of the API key
  scheme of TRS 2.0.2; the service info specification's own scheme
  (`bearerAuth`) and its global security requirement are removed.
- `GET /service-info` is the operation of the service info specification,
  served by FOCA from the config, instead of TRS's reference to the
  published service info specification (which would be fetched on every
  start).
- The registration endpoints and their schemas, and the `tags` of tools
  (see [Registering tools](#registering-tools)).

## GA4GH TRS endpoints

| Endpoint | Description |
| --- | --- |
| `GET /service-info` | The service info of the deployment (see [Service info](configuration.md#service-info)). |
| `GET /tools` | List tools, without the files of their versions, optionally filtered (e.g., by `toolClass`, `descriptorType`, `tags`, `organization`, `toolname`), one page at a time (see [Listing tools](#listing-tools)). |
| `GET /tools/{id}` | Get a tool. |
| `GET /tools/{id}/versions` | List the versions of a tool. |
| `GET /tools/{id}/versions/{version_id}` | Get a version of a tool. |
| `GET /tools/{id}/versions/{version_id}/{type}/descriptor` | Get the primary descriptor of a version, for descriptor type `type` (see [Descriptor types](#descriptor-types)). |
| `GET /tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}` | Get another descriptor file of a version, by its path. |
| `GET /tools/{id}/versions/{version_id}/{type}/tests` | List the test files of a version. |
| `GET /tools/{id}/versions/{version_id}/{type}/files` | List the files of a version for descriptor type `type` (descriptors, test files and other files, not container recipe files), or, with `format=zip`, get them as a ZIP archive. |
| `GET /tools/{id}/versions/{version_id}/containerfile` | List the container recipe files (e.g., Dockerfiles) of a version. |
| `GET /toolClasses` | List the tool classes. |

## Descriptor types

TRS-Filer supports all descriptor types of the specification: `CWL`,
`WDL`, `NFL`, `GALAXY` and `SMK` (Snakemake).

The specification also defines `PLAIN_` types (`PLAIN_CWL`, `PLAIN_WDL`,
`PLAIN_NFL`, `PLAIN_GALAXY`, `PLAIN_SMK`). They are not descriptor types of
files or versions, but output types: values of `{type}` in the paths of the
descriptor and test endpoints (`{type}/descriptor`,
`{type}/descriptor/{relative_path}`, `{type}/tests`), which ask for the bare
files rather than the files wrapped with metadata. So:

- Registering tools or versions with a `PLAIN_` type, as the type of a file
  (`type`) or a descriptor type of a version (`descriptor_type`), gives
  `400 Bad Request`; use the descriptor type without the prefix (e.g., `CWL`
  for `PLAIN_CWL`).
- TRS-Filer doesn't serve plain files yet: requests with the `PLAIN_` form
  of a supported type find no files (`404 Not Found`), and `{type}/files`
  doesn't take `PLAIN_` types (`400 Bad Request`), as in the specification.

## Listing tools

`GET /tools` returns the tools that match all given filters. Filters of
versions (`descriptorType`, `author`) must match the same version of a tool,
and filters of images (`registry`, `name`) the same image of that version.
Empty values match only empty values, like other values (e.g., `author=`
lists the tools with an empty author in one of their versions; an empty
`descriptorType` is not a valid descriptor type and gives `400 Bad
Request`).

The filter `tags` lists the tools that have all given tags (see
[Registering tools](#registering-tools)), in any order; tags are separated
by commas, also encoded ones (`tags=a,b` or `tags=a%2Cb`: tools with both
`a` and `b`), as the specification declares the parameter with `explode:
false`. Repeated parameters apply too (`tags=a&tags=b` is `tags=a,b`).
Tools without tags don't match any `tags` filter, and `tags=` only tools
with an empty tag.

Tools are listed in the order of their database identifiers, one page at a
time. That is roughly the order they were added (tools added by different
processes within the same second may be listed in another order), and
replaced tools keep their place. The order is stable, so pages don't overlap
while no tools are added or deleted.

- `offset` (default 0) is the index of the first tool of the page, and
  `limit` (default 1000) the number of tools per page. Limits above 1000 are
  reduced to 1000.
- An `offset` that is not a non-negative integer, or a `limit` below 1 (also
  `limit=0`), gives `400 Bad Request`.
- The response headers link to pages, with the limit actually used:
  `self_link` (this page), `next_page` (the next one; omitted on the last
  page) and `last_page` (the page with the last tool, in steps of `limit`
  from the requested `offset`, so that following `next_page` ends on it;
  for offsets beyond the last tool, in steps of `limit` from 0), and
  `current_offset` and `current_limit`. The links keep the filters of the
  request.

For example, with 25 tools, `GET /tools?offset=5&limit=10` returns the tools
at indices 5 to 14 (counting from 0), with `next_page` and `last_page` both
at offset 15 (indices 15 to 24).

## Registering tools

These endpoints are TRS-Filer's own, in
[`additions.openapi.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/api/additions.openapi.yaml):

| Endpoint | Description |
| --- | --- |
| `POST /tools` | Register a tool, with its versions and their files; returns the new identifier of the tool (see [Identifiers](configuration.md#identifiers)). |
| `PUT /tools/{id}` | Register a tool with the given identifier, or replace the tool with that identifier. |
| `DELETE /tools/{id}` | Delete a tool, with its versions. |
| `POST /tools/{id}/versions` | Add a version to a tool; returns the new identifier of the version. |
| `PUT /tools/{id}/versions/{version_id}` | Add a version with the given identifier to a tool, or replace the version with that identifier. |
| `DELETE /tools/{id}/versions/{version_id}` | Delete a version of a tool; the last version of a tool can't be deleted (`400 Bad Request`; delete the tool instead). |
| `POST /toolClasses` | Register a tool class; returns its new identifier. |
| `PUT /toolClasses/{id}` | Register a tool class with the given identifier, or replace the tool class with that identifier. |
| `DELETE /toolClasses/{id}` | Delete a tool class; tool classes that tools use can't be deleted (`400 Bad Request`). |

A tool has an `organization`, a tool class (`toolclass`) and a list of
versions (`versions`), and optionally a `name`, a `description`, `aliases`,
`tags` and a checker tool (`has_checker`, `checker_url`). Tags are
registry-specific strings without commas (e.g., `genomics`), by which
`GET /tools` filters (see [Listing tools](#listing-tools)); they are an
extension of TRS-Filer to the `Tool` schema of the specification, which
declares the filter but not where tools keep their tags, and are returned
with the tool. Each version lists its descriptor types (`descriptor_type`),
its container images (`images`) and its files (`files`), and optionally has
a `description` and the versions of its languages (`descriptor_type_version`,
by descriptor type, e.g., `{"CWL": ["v1.2"], "WDL": ["1.0", "1.1"]}`; the
keys should be descriptor types of the version, which TRS-Filer doesn't
check). Each file has a path and a file type (`tool_file`:
`PRIMARY_DESCRIPTOR`, `SECONDARY_DESCRIPTOR`, `TEST_FILE`, `CONTAINERFILE` or
`OTHER`), its descriptor type or image type (`type`: one of the supported
[descriptor types](#descriptor-types) for descriptors, test files and other
files, and `Docker`, `Singularity` or `Conda` for containerfiles), and its
content (`file_wrapper.content`) or a URL that the
content is retrieved from (`file_wrapper.url`, see [Remote
files](configuration.md#remote-files)), and optionally its checksums
(`file_wrapper.checksum`). The schemas (`ToolRegister`,
`ToolVersionRegister`, `FilesRegister`, `ToolClassRegister`) are in the
specification and the Swagger UI; [Getting started](getting-started.md#usage)
has an example.

Registering an object with the identifier of a stored one (`PUT`) replaces
it, also with identical content. Tools store a copy of their tool class: of
the stored tool class, if one with the identifier of `toolclass.id` exists
(the tool class is not changed), or else of the one sent, which is then
created, unless tool classes are validated (see [Tool
classes](configuration.md#tool-classes)). Who may add tool classes is
configured (see [Adding tool
classes](configuration.md#adding-tool-classes)). Replacing tools and
versions increments their `meta_version`, and adding, replacing or
deleting a version increments that of its tool, by default (see [Meta
versions](configuration.md#meta-versions)).

Anybody who can reach the API can use these endpoints (see [Access
control](access-control.md)).

## Errors

Errors are returned as problem details ([RFC
9457](https://www.rfc-editor.org/rfc/rfc9457)), with the members `title`,
`status` and `detail`, as `application/json` (the media type of the error
responses of the TRS specification), e.g.:

```json
{
  "title": "Not found",
  "status": 404,
  "detail": "The requested resource wasn't found."
}
```

Every response of the app, including error responses, has the header
`X-Request-ID`, which the app generates for each request (a request ID set
by a proxy in front of the app isn't used, see [Upgrading](upgrading.md));
log records carry it as a field, which the default log format doesn't
show. Responses to requests that Gunicorn refuses before they reach the
app (e.g., with a malformed request line or oversized headers) don't have
it.

Requests that don't match the API specification (e.g., an unknown
descriptor type, or a body without required properties) get `400 Bad
Request` with the reason of the validation as `detail` (see the setting
[`exceptions`](configuration.md#errors)). So do query parameters that an
operation doesn't declare, on all operations (e.g., `GET /tools?x=1`, and
also `GET /service-info?x=1`, `GET /toolClasses?x=1` and `POST /tools?x=1`,
whose operations have no parameters), and JSON bodies with unpaired
surrogates (e.g., `"\ud800"`), for which `detail` names neither the field
nor the value.

Where the invalid fields are known (not for bodies that aren't valid JSON
or have unpaired surrogates, which get only `title`, `status` and
`detail`), these responses have FOCA's problem type of invalid requests:
besides `title`, `status` and `detail`, the members `type` (a URL ending in
`/problems/invalid-request/`), `code` (`invalid-request`) and `errors`,
which lists the invalid fields, each with `detail`, `code` and either
`parameter` (a path or query parameter) or `pointer` (a JSON Pointer into
the body), without the values sent, e.g.:

```json
{
  "title": "Bad request",
  "status": 400,
  "detail": "'FOO' is not one of ['CWL', 'WDL', ...]",
  "type": "https://foca.readthedocs.io/en/latest/problems/invalid-request/",
  "code": "invalid-request",
  "errors": [
    {"detail": "...", "parameter": "type", "code": "invalid-value"}
  ]
}
```

Requests that match the specification but that TRS-Filer refuses get `400
Bad Request` with `title`, `status` and the reason as `detail` only, which
names the rule but not the values sent (they may hold credentials, e.g., in
URLs). Only the first reason found is given:

| Request | Reason |
| --- | --- |
| `GET /tools` | The `offset` is not a non-negative integer; the `limit` is below 1. |
| `POST`, `PUT` of tools | The tool class doesn't exist while tool classes are validated (see [Tool classes](configuration.md#tool-classes)); the versions have duplicate identifiers; a version is invalid (see below). |
| `POST`, `PUT` of versions | The paths of the files of a version are not unique per type; a descriptor type has more than one `PRIMARY_DESCRIPTOR` file, or `SECONDARY_DESCRIPTOR` files but none; a file has neither `file_wrapper.content` nor `file_wrapper.url`; a file of a production version (`is_production`) has no checksums (`file_wrapper.checksum`); the type of a descriptor, test or other file is not a supported descriptor type, or that of a containerfile not a supported image type. |
| `DELETE /tools/{id}/versions/{version_id}` | The version is the last one of the tool (delete the tool instead). |
| `DELETE /toolClasses/{id}` | Tools use the tool class. |

Files whose content can't be retrieved from their URL get `400 Bad Request`
with a fixed `detail` that lists the possible causes; the reason is only
logged, as it may reveal details of the destination (see [Remote
files](configuration.md#remote-files)).
