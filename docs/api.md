# API

TRS-Filer implements the [GA4GH Tool Registry Service (TRS)
API](https://github.com/ga4gh/tool-registry-service-schemas) at
`/ga4gh/trs/v2/`, and adds endpoints to register, change and delete tools,
tool versions and tool classes. A deployment's Swagger UI
(`/ga4gh/trs/v2/ui/`) shows all endpoints and lets you try them; the
specification is served at `/ga4gh/trs/v2/openapi.json`.

## Supported TRS version

The served specification is TRS
[`develop` at commit
1dd4bf8](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/api/20230406.1dd4bf8.openapi.yaml)
(April 2023), between the releases 2.0.1 and 2.0.2, with the service info of
the [GA4GH service info
specification](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/trs_filer/api/20200131.11d2c12.service-info.yaml).
The service info reports TRS version 2.0.1 (`type.version`).

## GA4GH TRS endpoints

| Endpoint | Description |
| --- | --- |
| `GET /service-info` | The service info of the deployment (see [Service info](configuration.md#service-info)). |
| `GET /tools` | List tools, without the files of their versions, optionally filtered (e.g., by `toolClass`, `descriptorType`, `organization`, `toolname`), one page at a time (see [Listing tools](#listing-tools)). |
| `GET /tools/{id}` | Get a tool. |
| `GET /tools/{id}/versions` | List the versions of a tool. |
| `GET /tools/{id}/versions/{version_id}` | Get a version of a tool. |
| `GET /tools/{id}/versions/{version_id}/{type}/descriptor` | Get the primary descriptor of a version, for descriptor type `type` (e.g., `CWL`, `WDL`, `NFL`, `GALAXY`). |
| `GET /tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}` | Get another descriptor file of a version, by its path. |
| `GET /tools/{id}/versions/{version_id}/{type}/tests` | List the test files of a version. |
| `GET /tools/{id}/versions/{version_id}/{type}/files` | List the files of a version for descriptor type `type` (descriptors, test files and other files, not container recipe files), or, with `format=zip`, get them as a ZIP archive. |
| `GET /tools/{id}/versions/{version_id}/containerfile` | List the container recipe files (e.g., Dockerfiles) of a version. |
| `GET /toolClasses` | List the tool classes. |

## Listing tools

`GET /tools` returns the tools that match all given filters. Filters of
versions (`descriptorType`, `author`) must match the same version of a tool,
and filters of images (`registry`, `name`) the same image of that version.
Empty values of `descriptorType` and `author` are ignored, and so is the
filter `tags` of the specification, which TRS-Filer doesn't support.

Tools are listed in the order of their database identifiers (roughly the
order they were added), one page at a time:

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
  `current_offset` and `current_limit`.

For example, with 25 tools, `GET /tools?offset=5&limit=10` returns the tools
at indices 5 to 14 (counting from 0), with `next_page` and `last_page` both
at offset 15 (indices 15 to 24).

!!! note
    Known issues: the links of `next_page` and `last_page` have only `offset`
    and `limit`, not the filters of the request: add them again when you
    follow the links. See the [issue
    tracker](https://github.com/elixir-cloud-aai/trs-filer/issues/179) for
    these and the issues above.

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
versions (`versions`), and optionally a `name`, a `description`, `aliases`
and a checker tool (`has_checker`, `checker_url`). Each version lists its
descriptor types (`descriptor_type`), its container images (`images`) and
its files (`files`). Each file has a path and a file type (`tool_file`:
`PRIMARY_DESCRIPTOR`, `SECONDARY_DESCRIPTOR`, `TEST_FILE`, `CONTAINERFILE` or
`OTHER`), its descriptor type or image type (`type`, e.g., `CWL` or
`Docker`), and its content (`file_wrapper.content`) or a URL that the
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
classes](configuration.md#tool-classes)). Replacing tools and versions
increments their `meta_version` (see [Meta
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
