"""Validation of GA4GH I/O Schema files (experimental).

The [GA4GH I/O Schema](https://github.com/uniqueg/ga4gh-io-schema) describes
the inputs and outputs of a workflow. It is published in TRS as a file of
type `OTHER` named `ga4gh-io.schema.json`, next to the primary descriptor; it
needs no change of the TRS specification. With `custom.io_schema.validation`,
such files are checked on registration against a vendored copy of the
meta-schema of the profile (`trs_filer.io_schema.check`, see
`docs/io-schema.md`).

The meta-schema and its vocabularies are vendored unchanged from
`schemas/` of uniqueg/ga4gh-io-schema at commit 573f65e (2026-11-12, branch
`v0.3`, profile version 0.3.0), licensed under the Apache License 2.0, in
the directory named after the date and commit (`META_SCHEMA_DIR`). Their
references are resolved from these copies; nothing is fetched.

Validating against the meta-schema takes time that grows steeply with the
nesting of a schema (its `unevaluatedProperties` are checked at every
level), so it runs in a process of its own, with a time limit
(`python -m trs_filer.io_schema`, see `main()`). This module imports only
the validator's packages, so that the process starts quickly.
"""

from functools import cache
import json
from pathlib import Path, PurePosixPath
import re
import resource
import sys
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError, relevance
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

#: File name of I/O Schema files (`ToolFile.path`, in any directory).
IO_SCHEMA_FILE_NAME = "ga4gh-io.schema.json"
#: TRS file type of I/O Schema files (`ToolFile.file_type`).
IO_SCHEMA_FILE_TYPE = "OTHER"
#: Version of the GA4GH I/O Profile that I/O Schemas are checked against.
PROFILE_VERSION = "0.3.0"
#: Directory of the vendored meta-schema and its vocabularies.
META_SCHEMA_DIR = Path(__file__).resolve().parent / "20261112.573f65e"
#: Identifier of the meta-schema, which I/O Schemas name in `$schema`.
META_SCHEMA_ID = (
    "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/"
    f"v{PROFILE_VERSION}/schemas/ga4gh-io-profile.schema.json"
)
#: Formats that the meta-schema uses (`format`), which are asserted.
META_SCHEMA_FORMATS = ["uri"]
#: Beginning of the reasons for rejecting an I/O Schema file.
PREFIX = f"The I/O Schema file ({IO_SCHEMA_FILE_NAME})"
# Names of properties that reasons may contain: short, without characters of
# URLs with credentials (e.g., `:`, `/`, `@`); others are replaced by `*`
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_NAME = re.compile(r"[A-Za-z0-9_$.-]{1,64}")
_KEYWORD = re.compile(r"x-ga4gh-[a-z0-9-]{1,56}")


def is_io_schema_file(tool_file: dict[str, Any]) -> bool:
    """Check whether a file of a tool version is an I/O Schema file.

    Args:
        tool_file: File type and path of the file (`ToolFile`).

    Returns:
        Whether the file has type `OTHER` and the name `ga4gh-io.schema.json`
        (case-sensitive), in any directory.
    """
    return (
        tool_file.get("file_type") == IO_SCHEMA_FILE_TYPE
        and PurePosixPath(str(tool_file.get("path", ""))).name == IO_SCHEMA_FILE_NAME
    )


@cache
def _validator() -> Draft202012Validator:
    """Get the validator of I/O Schemas, from the vendored meta-schema.

    Created once; validators are not changed by validation. References
    between the vendored files are resolved by their `$id`s; others (e.g.,
    remote ones) are not resolvable. The formats of the meta-schema
    (`META_SCHEMA_FORMATS`) are asserted, as by the validator of the profile
    (`uri` with `rfc3986-validator`).

    Returns:
        The validator.
    """
    registry: Registry[Any] = Registry()
    profile: dict[str, Any] = {}
    for path in sorted(META_SCHEMA_DIR.rglob("*.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            uri=contents["$id"],
            resource=Resource.from_contents(
                contents, default_specification=DRAFT202012
            ),
        )
        if contents["$id"] == META_SCHEMA_ID:
            profile = contents
    Draft202012Validator.check_schema(profile)
    return Draft202012Validator(
        profile,
        registry=registry,
        format_checker=FormatChecker(formats=META_SCHEMA_FORMATS),
    )


def _most_specific(errors: list[ValidationError]) -> ValidationError:
    """Choose the error to report of those of an I/O Schema.

    A keyword with an invalid value is unevaluated, too, so the error of its
    schema (`unevaluatedProperties`) is reported only if there is no other.

    Args:
        errors: Errors of the I/O Schema (at least one).

    Returns:
        The most relevant error (cf. `jsonschema`'s `relevance()`; errors
        of applicators such as `anyOf` themselves, not those of their
        subschemas).
    """
    specific = [error for error in errors if error.validator != "unevaluatedProperties"]
    return max(specific or errors, key=relevance)


def _path(error: ValidationError) -> str:
    """Get the location of an error in the I/O Schema, as a JSON path.

    Names that could be values (e.g., URLs) are replaced by `*`.

    Args:
        error: Error of the I/O Schema.

    Returns:
        The JSON path (e.g., `$.properties.inputs.properties.name`).
    """
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        elif _IDENTIFIER.fullmatch(part):
            path += f".{part}"
        elif _NAME.fullmatch(part):
            path += f"['{part}']"
        else:
            path += "[*]"
    return path


def _names(error: ValidationError) -> list[str]:
    """Get the names of the properties that an error is about.

    Only names that are not values of the I/O Schema: required properties
    (names of the meta-schema) and unexpected `x-ga4gh-*` keywords of the
    form of the profile's keywords (all other keywords are allowed).

    Args:
        error: Error of the I/O Schema.

    Returns:
        The names of the missing properties of a `required` error, or of the
        unexpected keywords of an `unevaluatedProperties` error; none for
        other errors.
    """
    if not isinstance(error.instance, dict):
        return []
    if error.validator == "required" and isinstance(error.validator_value, list):
        return [
            name
            for name in error.validator_value
            if isinstance(name, str) and name not in error.instance
        ]
    if error.validator == "unevaluatedProperties":
        # jsonschema names the unexpected properties in its message only
        return [
            name
            for name in error.instance
            if isinstance(name, str)
            and _KEYWORD.fullmatch(name)
            and repr(name) in error.message
        ]
    return []


def find_problem(schema: dict[str, Any]) -> str | None:
    """Validate an I/O Schema against the meta-schema of the profile.

    The reason says where the schema breaks a rule of the meta-schema (as a
    JSON path, and the keyword of the meta-schema), but doesn't contain its
    values (cf. `trs_filer.errors.exceptions.InvalidRequest`).

    Args:
        schema: The I/O Schema, which names the meta-schema in `$schema`.

    Returns:
        Why the schema is invalid, or `None` if it is valid.
    """
    try:
        errors = list(_validator().iter_errors(schema))
        if not errors:
            return None
        error = _most_specific(errors)
        location = f"at {_path(error)} (keyword '{error.validator}'"
        names = _names(error)
    except RecursionError:
        # e.g., deeply nested arrays, which the validator compares
        return f"{PREFIX} is nested too deeply to be checked."
    if names:
        location += f": {', '.join(repr(name) for name in names)}"
    return (
        f"{PREFIX} doesn't validate against the meta-schema of the GA4GH I/O "
        f"Profile {PROFILE_VERSION} {location})."
    )


def main(argv: list[str] | None = None) -> None:
    """Validate an I/O Schema from standard input.

    Reads the schema as UTF-8 from standard input and writes the result to
    standard output, as a JSON object with the reason why the schema is
    invalid (`problem`, cf. `find_problem()`), or `null` if it is valid. Run
    with `python -m trs_filer.io_schema <seconds>` by
    `trs_filer.io_schema.check.check_io_schema()`.

    Args:
        argv: Arguments: the limit of the CPU time of the process, in whole
            seconds (`RLIMIT_CPU`; the process is killed when it is reached);
            `sys.argv[1:]` if not given.
    """
    (seconds,) = sys.argv[1:] if argv is None else argv
    limit = int(seconds)
    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
    schema = json.load(sys.stdin.buffer)
    sys.stdout.buffer.write(
        json.dumps({"problem": find_problem(schema)}).encode("utf-8")
    )
