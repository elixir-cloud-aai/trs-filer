"""Checks of GA4GH I/O Schema files (experimental).

The [GA4GH I/O Schema](https://github.com/uniqueg/ga4gh-io-schema) describes
the inputs and outputs of a workflow. It is published in TRS as a file of
type `OTHER` named `ga4gh-io.schema.json`, next to the primary descriptor; it
needs no change of the TRS specification. With `custom.io_schema.validation`,
such files are checked on registration against a vendored copy of the
meta-schema of the profile (see `docs/io-schema.md`).

The meta-schema and its vocabularies are vendored unchanged from
`schemas/` of uniqueg/ga4gh-io-schema at commit 573f65e (2026-11-12, branch
`v0.3`, profile version 0.3.0), licensed under the Apache License 2.0, in
the directory named after the date and commit (`META_SCHEMA_DIR`). Their
references are resolved from these copies; nothing is fetched.
"""

import copy
from functools import cache
import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError, relevance
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from trs_filer.errors.exceptions import InvalidRequest

logger = logging.getLogger(__name__)

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
_PREFIX = f"The I/O Schema file ({IO_SCHEMA_FILE_NAME})"


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
    remote ones) are not resolvable. `format` keywords are asserted, except
    `regex`, as Python can't parse all ECMA-262 patterns (as the validator of
    the profile does).

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
    # a copy of the draft's own checker, without `regex`
    format_checker = copy.copy(Draft202012Validator.FORMAT_CHECKER)
    format_checker.checkers = {
        name: check
        for name, check in format_checker.checkers.items()
        if name != "regex"
    }
    return Draft202012Validator(
        profile, registry=registry, format_checker=format_checker
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


def _names(error: ValidationError) -> list[str]:
    """Get the names of the properties that an error is about.

    Only names that are not values of the I/O Schema: required properties
    (names of the meta-schema) and unexpected `x-ga4gh-*` keywords (all
    other keywords are allowed).

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
        return [
            name
            for name in error.instance
            if isinstance(name, str)
            and name.startswith("x-ga4gh-")
            and repr(name) in error.message
        ]
    return []


def check_io_schema(content: str, descriptor_type: str) -> None:
    """Check an I/O Schema file against the meta-schema of the profile.

    The reasons for rejecting a file say where the file breaks a rule of the
    meta-schema (as a JSON path, and the keyword of the meta-schema), but
    don't contain its values (see `InvalidRequest`).

    Args:
        content: Content of the file.
        descriptor_type: Descriptor type that the file is registered for.

    Raises:
        InvalidRequest: The file is not JSON, not a JSON object, doesn't name
            the meta-schema of the supported version of the profile in
            `$schema`, doesn't validate against it, or names another
            descriptor type in `x-ga4gh-workflow.descriptor_type`.
    """
    try:
        schema = json.loads(content)
    except (ValueError, RecursionError) as exc:
        logger.error("I/O Schema file is not valid JSON.")
        raise InvalidRequest(f"{_PREFIX} is not valid JSON.") from exc
    if not isinstance(schema, dict):
        logger.error("I/O Schema file is not a JSON object.")
        raise InvalidRequest(f"{_PREFIX} must be a JSON object.")
    if schema.get("$schema") != META_SCHEMA_ID:
        logger.error("I/O Schema file names another meta-schema.")
        raise InvalidRequest(
            f"{_PREFIX} must name the meta-schema of the GA4GH I/O Profile that "
            f"TRS-Filer supports in '$schema': '{META_SCHEMA_ID}'."
        )
    errors = list(_validator().iter_errors(schema))
    if errors:
        error = _most_specific(errors)
        location = f"at {error.json_path} (keyword '{error.validator}'"
        names = _names(error)
        if names:
            location += f": {', '.join(repr(name) for name in names)}"
        location += ")"
        logger.error(
            "I/O Schema file is invalid %s, against the meta-schema at '%s'.",
            location,
            "/".join(str(part) for part in error.absolute_schema_path),
        )
        raise InvalidRequest(
            f"{_PREFIX} doesn't validate against the meta-schema of the GA4GH "
            f"I/O Profile {PROFILE_VERSION} {location}."
        )
    workflow = schema.get("x-ga4gh-workflow")
    if isinstance(workflow, dict) and workflow.get("descriptor_type") != (
        descriptor_type
    ):
        logger.error(
            "I/O Schema file of descriptor type '%s' names another one.",
            descriptor_type,
        )
        raise InvalidRequest(
            f"{_PREFIX} of descriptor type {descriptor_type} names another "
            "descriptor type in 'x-ga4gh-workflow.descriptor_type'."
        )
