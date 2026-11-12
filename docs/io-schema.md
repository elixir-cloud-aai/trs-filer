# I/O Schemas

!!! warning "Experimental"

    Support for I/O Schemas follows a draft of the GA4GH I/O Schema, the
    [profile version
    0.3.0](https://github.com/uniqueg/ga4gh-io-schema/tree/v0.3), which may
    still change; so may this support, also in minor releases of TRS-Filer.
    The [check](#checking-io-schemas) is off by default.

The [GA4GH I/O Schema](https://github.com/uniqueg/ga4gh-io-schema) describes
the inputs and outputs of a workflow as a JSON Schema, with keywords for
forms (titles, widgets, files) and for the workflow engine (which tool
version and descriptor it belongs to, and the names and types of the
engine's parameters). Portals generate forms from it and turn what users
enter into the parameters of a run (e.g., via WES).

An I/O Schema is published in TRS as a file of the tool version, as the
[TRS convention of the
profile](https://github.com/uniqueg/ga4gh-io-schema/blob/v0.3/docs/adoption/trs.md)
defines; the TRS specification is not changed. TRS-Filer stores and serves
such files like any other file, with or without the
[check](#checking-io-schemas).

## Publishing an I/O Schema

For each descriptor type of a tool version, register the I/O Schema as a
file with:

- the file type `OTHER` (`tool_file.file_type`);
- the path `ga4gh-io.schema.json` in the directory of the primary descriptor
  (`tool_file.path`, e.g., `ga4gh-io.schema.json` for the primary descriptor
  `hello.wdl`, or `wdl/ga4gh-io.schema.json` for `wdl/main.wdl`);
- the descriptor type that it describes (`type`, e.g., `WDL`), the one
  that its `x-ga4gh-workflow.descriptor_type` names;
- its content (`file_wrapper.content`), or a URL that TRS-Filer retrieves it
  from (`file_wrapper.url`, see [Remote
  files](configuration.md#remote-files)).

The schema names the meta-schema of the profile in `$schema`, and the tool
version and the checksum of its primary descriptor in `x-ga4gh-workflow`, so
that clients can check that it belongs to the version they fetched it for.
Choose the identifiers of the tool and the version (`PUT`), so that the
schema can name them; generated identifiers are not known before the
registration.

For example, the I/O Schema of a WDL workflow `hello.wdl`
([`hello.wdl`](examples/io-schema/hello.wdl)), which greets someone once or
several times:

```json
--8<-- "docs/examples/io-schema/ga4gh-io.schema.json"
```

[`tool.json`](examples/io-schema/tool.json) registers the workflow with its
I/O Schema as version `1.0.0` of the tool `HELLO` (with an access token of
an admin, see [Access control](access-control.md)):

```bash
curl -X PUT "http://localhost:8080/ga4gh/trs/v2/tools/HELLO" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @docs/examples/io-schema/tool.json
```

## Fetching an I/O Schema

Clients find the I/O Schema of a tool version among its files, and fetch it
by its path:

1. List the files of the tool version for the descriptor type: `GET
   /tools/HELLO/versions/1.0.0/WDL/files` lists, e.g., `{"path":
   "ga4gh-io.schema.json", "file_type": "OTHER"}` next to the primary
   descriptor.
2. Fetch it: `GET
   /tools/HELLO/versions/1.0.0/WDL/descriptor/ga4gh-io.schema.json` returns
   it in a `FileWrapper`, as `content`, with its `checksum`; `PLAIN_WDL` in
   place of `WDL` returns it as is (see [Descriptor
   types](api.md#descriptor-types)).
3. Check it as the profile describes: against the meta-schema, and its
   `x-ga4gh-workflow` against the tool version and the checksum of the
   primary descriptor.

## Checking I/O Schemas

With `custom.io_schema.validation` (`false` by default), TRS-Filer checks
I/O Schema files when tools and versions are registered, and rejects
invalid ones with `400 Bad Request`:

```yaml
custom:
    io_schema:
        validation: true
```

I/O Schema files are files of type `OTHER` named `ga4gh-io.schema.json`, in
any directory; other files aren't checked. A file is invalid if it:

- is not a JSON object;
- names another meta-schema than that of profile version 0.3.0 in `$schema`
  (`https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json`),
  e.g., of another version of the profile;
- doesn't validate against that meta-schema; or
- names another descriptor type than its own in
  `x-ga4gh-workflow.descriptor_type`.

The `detail` of the response says why, and, for schemas that don't validate,
where (as a JSON path) and which keyword of the meta-schema they break, but
not their values, e.g.:

```json
{
  "title": "Bad request",
  "status": 400,
  "detail": "The I/O Schema file (ga4gh-io.schema.json) doesn't validate against the meta-schema of the GA4GH I/O Profile 0.3.0 at $.properties (keyword 'required': 'inputs')."
}
```

The [validator of the
profile](https://github.com/uniqueg/ga4gh-io-schema/blob/v0.3/docs/tools/validator.md)
reports all errors with their values; check schemas with it before
registering them. Files retrieved from their URLs are checked once
retrieved.

The meta-schema of profile version 0.3.0 and its vocabularies are vendored
unchanged in
[`trs_filer/io_schema/`](https://github.com/elixir-cloud-aai/trs-filer/tree/dev/trs_filer/io_schema),
from commit `573f65e` of the profile's `v0.3` branch; nothing is fetched.
TRS-Filer doesn't check the identifiers and the checksum of
`x-ga4gh-workflow` against the tool version (identifiers may be generated
on registration). Tool versions stored before the check was enabled are not
checked.

In the Helm chart, set the option in `trs_filer.config` (see the chart's
[Configuration](deployment.md#configuration)):

```yaml
trs_filer:
  config:
    custom:
      io_schema:
        validation: true
```
