"""Tests of the checks of GA4GH I/O Schema files (`trs_filer.io_schema`)."""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import resource
import subprocess
import sys
import threading
from typing import Any, NoReturn

import pytest

from trs_filer import io_schema
from trs_filer.custom_config import IoSchemaConfig
from trs_filer.errors.exceptions import InternalServerError, InvalidRequest
from trs_filer.io_schema import (
    IO_SCHEMA_FILE_NAME,
    META_SCHEMA_DIR,
    META_SCHEMA_FORMATS,
    META_SCHEMA_ID,
    find_problem,
    is_io_schema_file,
    main,
)
from trs_filer.io_schema import check as check_module
import trs_filer.io_schema.__main__  # noqa: F401 (covered by imports)
from trs_filer.io_schema.check import check_io_schema

# Time limit of the checks of the tests, in seconds
TIMEOUT = 60

ROOT = Path(__file__).resolve().parents[1]
# The example of `docs/io-schema.md`: a WDL workflow, its I/O Schema and the
# registration payload with both
EXAMPLE = ROOT / "docs" / "examples" / "io-schema"
# The vendored meta-schema of the profile, by path relative to
# `META_SCHEMA_DIR`, with the SHA-256 checksums of the files of
# uniqueg/ga4gh-io-schema (`schemas/`) at commit d44e8d4
VENDORED = {
    "ga4gh-io-profile.schema.json": (
        "96b86700af3b0179ce1a3987716e044203c47a351cb3ac5300cb18e4c418ab2f"
    ),
    "vocabularies/annotations.schema.json": (
        "01f80107c0f40d96f78849fabcfbd618f1fff33c762d9c4f41cab086a8d8e43c"
    ),
    "vocabularies/file.schema.json": (
        "064ad2f640e4e5b79fce7ceb1558ee7078773cf6230f1bdeebb70c32004d97b8"
    ),
    "vocabularies/outputs.schema.json": (
        "2bcf4d16f4b6d6e7190537a58d12919620cfa2af2b2de2d381bc52a3f267c103"
    ),
    "vocabularies/parameter.schema.json": (
        "f0e25228d50b73168039a7b7c424b460c0f8882fa6eb53d0886a3fd086cf0870"
    ),
    "vocabularies/ui-widgets.schema.json": (
        "0fdb3d3b0989b4f719ad737a8364bc8f5af4e9774a3393d8ec0418a5dc395ed1"
    ),
    "vocabularies/workflow.schema.json": (
        "f362277ba39661fb4ebf35909f1f523b0dc8eda81b7e856e83dd7ffa1e2822f8"
    ),
}


def _schema() -> dict[str, Any]:
    """Get the I/O Schema of the example.

    Returns:
        The I/O Schema.
    """
    schema: dict[str, Any] = json.loads(
        (EXAMPLE / IO_SCHEMA_FILE_NAME).read_text(encoding="utf-8")
    )
    return schema


def _detail(content: str, descriptor_type: str = "WDL") -> str:
    """Get the reason why an I/O Schema file is rejected.

    Args:
        content: Content of the file.
        descriptor_type: Descriptor type of the file.

    Returns:
        The description of the exception, as sent to clients.
    """
    with pytest.raises(InvalidRequest) as exc_info:
        check_io_schema(content, descriptor_type, timeout=TIMEOUT)
    assert exc_info.value.description is not None
    return exc_info.value.description


def test_meta_schema_vendored_unchanged() -> None:
    """The meta-schema is vendored as published, and complete."""
    paths = sorted(
        str(path.relative_to(META_SCHEMA_DIR))
        for path in META_SCHEMA_DIR.rglob("*.json")
    )
    assert paths == sorted(VENDORED)
    for name, checksum in VENDORED.items():
        content = (META_SCHEMA_DIR / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == checksum
    # The only vendored version
    assert sorted(p.name for p in META_SCHEMA_DIR.parent.glob("2*")) == [
        META_SCHEMA_DIR.name
    ]


def test_meta_schema_id() -> None:
    """The I/O Schemas checked name the vendored meta-schema of profile 0.3.0."""
    profile = json.loads(
        (META_SCHEMA_DIR / "ga4gh-io-profile.schema.json").read_text(encoding="utf-8")
    )
    assert profile["$id"] == META_SCHEMA_ID
    assert profile["properties"]["$schema"]["const"] == META_SCHEMA_ID
    assert "/v0.3.0/" in META_SCHEMA_ID


@pytest.mark.parametrize(
    ("tool_file", "expected"),
    [
        ({"file_type": "OTHER", "path": "ga4gh-io.schema.json"}, True),
        ({"file_type": "OTHER", "path": "wdl/ga4gh-io.schema.json"}, True),
        ({"file_type": "OTHER", "path": "other.json"}, False),
        ({"file_type": "OTHER", "path": "ga4gh-io.schema.json.bak"}, False),
        ({"file_type": "OTHER", "path": "GA4GH-IO.schema.json"}, False),
        ({"file_type": "TEST_FILE", "path": "ga4gh-io.schema.json"}, False),
        ({"file_type": "PRIMARY_DESCRIPTOR", "path": "ga4gh-io.schema.json"}, False),
    ],
)
def test_is_io_schema_file(tool_file: dict[str, str], expected: bool) -> None:
    """I/O Schema files are files of type `OTHER` named `ga4gh-io.schema.json`.

    Args:
        tool_file: File type and path of a file.
        expected: Whether the file is an I/O Schema file.
    """
    assert is_io_schema_file(tool_file) is expected


def test_check_io_schema_valid() -> None:
    """The I/O Schema of the example is valid."""
    content = (EXAMPLE / IO_SCHEMA_FILE_NAME).read_text(encoding="utf-8")
    check_io_schema(content, "WDL", timeout=TIMEOUT)
    assert find_problem(json.loads(content)) is None


def test_check_io_schema_without_workflow() -> None:
    """I/O Schemas without `x-ga4gh-workflow` are valid for any descriptor type."""
    schema = _schema()
    del schema["x-ga4gh-workflow"]
    check_io_schema(json.dumps(schema), "CWL", timeout=TIMEOUT)


@pytest.mark.parametrize(
    "content", ["", "{", "not JSON", "[1,", '{"a": NaN}', '{"a": -Infinity}']
)
def test_check_io_schema_not_json(content: str) -> None:
    """Files that are not JSON are rejected.

    Args:
        content: Content of the file.
    """
    assert _detail(content) == (
        "The I/O Schema file (ga4gh-io.schema.json) is not valid JSON."
    )


@pytest.mark.parametrize("content", ["[]", "1", '"schema"', "null"])
def test_check_io_schema_not_object(content: str) -> None:
    """JSON documents other than objects are rejected.

    Args:
        content: Content of the file.
    """
    assert _detail(content) == (
        "The I/O Schema file (ga4gh-io.schema.json) must be a JSON object."
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.2.0/"
        "schemas/ga4gh-io-profile.schema.json",
        "https://json-schema.org/draft/2020-12/schema",
    ],
)
def test_check_io_schema_other_meta_schema(value: str | None) -> None:
    """I/O Schemas must name the supported version of the profile.

    Args:
        value: `$schema` of the I/O Schema; missing if `None`.
    """
    schema = _schema()
    if value is None:
        del schema["$schema"]
    else:
        schema["$schema"] = value
    assert _detail(json.dumps(schema)) == (
        "The I/O Schema file (ga4gh-io.schema.json) must name the meta-schema "
        f"of the GA4GH I/O Profile that TRS-Filer supports in '$schema': "
        f"'{META_SCHEMA_ID}'."
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        # `inputs` is required
        (
            lambda s: s["properties"].pop("inputs"),
            "at $.properties (keyword 'required': 'inputs')",
        ),
        # unknown `x-ga4gh-*` keywords are rejected, also nested
        (
            lambda s: s["properties"]["inputs"]["properties"]["name"].update(
                {"x-ga4gh-fa-icon": "user"}
            ),
            "at $.properties.inputs.properties.name (keyword "
            "'unevaluatedProperties': 'x-ga4gh-fa-icon')",
        ),
        # `x-ga4gh-workflow` is allowed at the top level only
        (
            lambda s: s["properties"]["inputs"].update(
                {"x-ga4gh-workflow": {"descriptor_type": "WDL"}}
            ),
            "at $.properties.inputs (keyword 'unevaluatedProperties': "
            "'x-ga4gh-workflow')",
        ),
        # values of keywords are checked
        (
            lambda s: s["properties"]["inputs"]["properties"]["times"].update(
                {"x-ga4gh-ui-widget": "wheel"}
            ),
            "at $.properties.inputs.properties.times['x-ga4gh-ui-widget'] "
            "(keyword 'anyOf')",
        ),
        # `$id` must be absolute
        (
            lambda s: s.update({"$id": "hello/1.0.0"}),
            "at $['$id'] (keyword 'format')",
        ),
        # other fields of `x-ga4gh-workflow` are rejected (without names)
        (
            lambda s: s["x-ga4gh-workflow"].update({"version": "1.0.0"}),
            "at $['x-ga4gh-workflow'] (keyword 'additionalProperties')",
        ),
        # formats are checked
        (
            lambda s: s.update({"$id": "https://exa mple.org/hello"}),
            "at $['$id'] (keyword 'format')",
        ),
        # names that could be values are not repeated
        (
            lambda s: s["properties"]["inputs"]["properties"].update(
                {"https://user:pass@example.org/": {"type": "text"}}
            ),
            "at $.properties.inputs.properties[*].type (keyword 'anyOf')",
        ),
        (
            lambda s: s["properties"]["inputs"].update({"x-ga4gh-" + "a" * 100: True}),
            "at $.properties.inputs (keyword 'unevaluatedProperties')",
        ),
        (
            lambda s: s["properties"]["inputs"].update({"x-ga4gh-Pass:word": True}),
            "at $.properties.inputs (keyword 'unevaluatedProperties')",
        ),
        # array items are named by index
        (
            lambda s: s["properties"]["inputs"].update({"required": ["name", 1]}),
            "at $.properties.inputs.required[1] (keyword 'type')",
        ),
        # nested schemas must be valid JSON Schema
        (
            lambda s: s["properties"]["inputs"]["properties"]["times"].update(
                {"minimum": "one"}
            ),
            "at $.properties.inputs.properties.times.minimum (keyword 'type')",
        ),
    ],
)
def test_check_io_schema_invalid(change: Any, expected: str) -> None:
    """I/O Schemas that don't validate against the meta-schema are rejected.

    The reason names where and how, but not the submitted values.

    Args:
        change: Change of the valid I/O Schema that makes it invalid.
        expected: End of the reason.
    """
    schema = _schema()
    change(schema)
    detail = (
        "The I/O Schema file (ga4gh-io.schema.json) doesn't validate against "
        "the meta-schema of the GA4GH I/O Profile 0.3.0 " + expected + "."
    )
    assert find_problem(schema) == detail
    assert _detail(json.dumps(schema)) == detail


def test_check_io_schema_invalid_no_values() -> None:
    """The reason doesn't contain submitted values (e.g., URLs with user info)."""
    schema = _schema()
    value = "https://user:pass@example.org/"
    schema["properties"]["inputs"]["properties"]["times"]["minimum"] = value
    detail = _detail(json.dumps(schema))
    assert "example.org" not in detail
    assert detail.endswith("times.minimum (keyword 'type').")


def test_check_io_schema_descriptor_type_mismatch() -> None:
    """I/O Schemas must be registered for the descriptor type they name."""
    content = (EXAMPLE / IO_SCHEMA_FILE_NAME).read_text(encoding="utf-8")
    assert _detail(content, "CWL") == (
        "The I/O Schema file (ga4gh-io.schema.json) of descriptor type CWL "
        "names another descriptor type in 'x-ga4gh-workflow.descriptor_type'."
    )


def test_example_payload() -> None:
    """The registration payload of the example has the files of the example.

    Their checksums are correct, and the I/O Schema names the primary
    descriptor by its checksum.
    """
    tool = json.loads((EXAMPLE / "tool.json").read_text(encoding="utf-8"))
    (version,) = tool["versions"]
    files = {f["tool_file"]["path"]: f for f in version["files"]}
    assert sorted(files) == ["ga4gh-io.schema.json", "hello.wdl"]
    for path, file in files.items():
        content = (EXAMPLE / path).read_text(encoding="utf-8")
        wrapper = file["file_wrapper"]
        assert wrapper["content"] == content
        assert wrapper["checksum"] == [
            {
                "type": "sha-256",
                "checksum": hashlib.sha256(content.encode()).hexdigest(),
            }
        ]
        assert file["type"] == "WDL"
    assert files["hello.wdl"]["tool_file"]["file_type"] == "PRIMARY_DESCRIPTOR"
    assert is_io_schema_file(files[IO_SCHEMA_FILE_NAME]["tool_file"])
    workflow = _schema()["x-ga4gh-workflow"]
    assert workflow["trs_version_id"] == version["id"]
    assert workflow["primary_descriptor_path"] == "hello.wdl"
    assert workflow["checksum"] == files["hello.wdl"]["file_wrapper"]["checksum"]
    assert (
        workflow["descriptor_type_version"]
        in (version["descriptor_type_version"]["WDL"])
    )


def test_check_io_schema_repeated() -> None:
    """Checks don't depend on earlier ones (the validator is reused)."""
    content = json.dumps(_schema())
    invalid = deepcopy(_schema())
    invalid["properties"].pop("inputs")
    _detail(json.dumps(invalid))
    check_io_schema(content, "WDL", timeout=TIMEOUT)


def test_find_problem_nested_too_deeply(monkeypatch: pytest.MonkeyPatch) -> None:
    """Schemas nested too deeply for the validator are rejected.

    Args:
        monkeypatch: Patches of the validator.
    """

    class _Validator:
        """Validator that recurses too deeply."""

        def iter_errors(self, schema: object) -> NoReturn:
            """Fail like the validator for schemas nested too deeply.

            Args:
                schema: Schema.

            Raises:
                RecursionError: Always.
            """
            raise RecursionError

    monkeypatch.setattr(io_schema, "_validator", _Validator)
    assert find_problem(_schema()) == (
        "The I/O Schema file (ga4gh-io.schema.json) is nested too deeply to be checked."
    )


def test_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """The validator reads a schema from standard input and writes the result.

    It limits its CPU time first.

    Args:
        monkeypatch: Patches of standard input and output, and of the limits
            of the process.
    """
    limits: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        io_schema.resource,
        "setrlimit",
        lambda which, limit: limits.append((which, limit)),
    )
    invalid = _schema()
    invalid["properties"].pop("inputs")
    for schema, problem in ((_schema(), None), (invalid, find_problem(invalid))):
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(schema).encode("utf-8")))
        stdout = io.TextIOWrapper(io.BytesIO())
        monkeypatch.setattr(sys, "stdin", stdin)
        monkeypatch.setattr(sys, "stdout", stdout)
        main(["7"])
        assert json.loads(stdout.buffer.getvalue()) == {"problem": problem}
    assert limits == [(resource.RLIMIT_CPU, (7, 7))] * 2


def test_main_module() -> None:
    """The validator runs as a module (`python -m trs_filer.io_schema`)."""
    result = subprocess.run(
        [sys.executable, "-I", "-m", "trs_filer.io_schema", "60"],
        input=json.dumps(_schema()).encode("utf-8"),
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"problem": None}


def test_check_io_schema_not_utf8() -> None:
    """Contents that can't be encoded in UTF-8 (lone surrogates) are rejected."""
    schema = _schema()
    schema["title"] = "\ud800"
    content = json.dumps(schema, ensure_ascii=False)
    assert json.loads(content)["title"] == "\ud800"
    assert _detail(content) == (
        "The I/O Schema file (ga4gh-io.schema.json) is not valid JSON."
    )


def test_check_io_schema_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checks wait for each other, which counts against the time limit.

    Args:
        monkeypatch: Patches of the slot of the validation.
    """
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(check_module, "_SLOTS", slots)
    slots.acquire()
    try:
        with pytest.raises(InvalidRequest) as exc_info:
            check_io_schema(json.dumps(_schema()), "WDL", timeout=0.01)
    finally:
        slots.release()
    assert exc_info.value.description is not None
    assert "could not be checked within the time limit" in (exc_info.value.description)
    # the slot is free again after checks
    check_io_schema(json.dumps(_schema()), "WDL", timeout=TIMEOUT)
    assert slots.acquire(blocking=False)
    slots.release()


def test_check_io_schema_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validations killed by a signal (e.g., at their CPU limit) are too slow.

    Args:
        monkeypatch: Patches of the process of the validation.
    """

    def run(*args: Any, **kwargs: Any) -> NoReturn:
        """Fail like a process killed by `SIGXCPU`.

        Args:
            args: Positional arguments of `subprocess.run()`.
            kwargs: Keyword arguments of `subprocess.run()`.

        Raises:
            subprocess.CalledProcessError: Always.
        """
        raise subprocess.CalledProcessError(-24, "python")

    monkeypatch.setattr(check_module.subprocess, "run", run)
    with pytest.raises(InvalidRequest) as exc_info:
        check_io_schema(json.dumps(_schema()), "WDL", timeout=TIMEOUT)
    assert exc_info.value.description is not None
    assert "could not be checked within the time limit" in (exc_info.value.description)


def test_validator_formats() -> None:
    """The formats of the meta-schema are asserted, and only these."""
    paths = META_SCHEMA_DIR.rglob("*.json")
    formats = {
        match
        for path in paths
        for match in re.findall(r'"format": "([^"]+)"', path.read_text())
    }
    assert formats == set(META_SCHEMA_FORMATS)
    checker = io_schema._validator().format_checker
    assert checker is not None
    assert sorted(checker.checkers) == sorted(META_SCHEMA_FORMATS)


def _nested_arrays(depth: int) -> dict[str, Any]:
    """Get the schema of an input of nested arrays (e.g., CWL's `File[][]`).

    Args:
        depth: Number of nested arrays.

    Returns:
        The schema, with a file as the innermost items.
    """
    schema: dict[str, Any] = {
        "type": "string",
        "x-ga4gh-file": {"kind": "file"},
        "x-ga4gh-parameter": {"type": "File"},
    }
    for _ in range(depth):
        schema = {
            "type": "array",
            "items": schema,
            "x-ga4gh-parameter": {"type": "File[]"},
        }
    return schema


def _nested_records(depth: int, width: int) -> dict[str, Any]:
    """Get the schema of an input of nested records.

    Args:
        depth: Number of nested records.
        width: Number of fields of each record.

    Returns:
        The schema, with strings as the innermost fields.
    """
    schema: dict[str, Any] = {"type": "string"}
    for _ in range(depth):
        schema = {
            "type": "object",
            "properties": {f"field_{index}": schema for index in range(width)},
        }
    return schema


@pytest.mark.parametrize(
    "parameter",
    [_nested_arrays(10), _nested_records(4, 3)],
    ids=["arrays-10", "records-4x3"],
)
def test_check_io_schema_nested(parameter: dict[str, Any]) -> None:
    """Nested schemas are checked within the default time limit.

    Regression test of uniqueg/ga4gh-io-schema #47: against the meta-schema
    of commit 573f65e, validating either schema took more than 70 s (time
    exponential in the depth of nesting); against that of commit d44e8d4,
    each is checked well within the time limit (about 0.2 s, including the
    start of the process).

    Args:
        parameter: Schema of the only input.
    """
    schema = {
        "$schema": META_SCHEMA_ID,
        "type": "object",
        "properties": {
            "inputs": {"type": "object", "properties": {"parameter": parameter}},
        },
    }
    check_io_schema(json.dumps(schema), "CWL", timeout=IoSchemaConfig().timeout)


def test_check_io_schema_timeout() -> None:
    """Schemas not checked within the time limit are rejected."""
    content = json.dumps(_schema())
    with pytest.raises(InvalidRequest) as exc_info:
        check_io_schema(content, "WDL", timeout=0.001)
    assert exc_info.value.description == (
        "The I/O Schema file (ga4gh-io.schema.json) could not be checked within "
        "the time limit of 0.001 s; simplify it (e.g., make it smaller)."
    )


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CalledProcessError(1, "python"),
        subprocess.CompletedProcess("python", 0, stdout=b"not JSON"),
        subprocess.CompletedProcess("python", 0, stdout=b"{}"),
        subprocess.CompletedProcess("python", 0, stdout=b"[]"),
        subprocess.CompletedProcess("python", 0, stdout=b'{"problem": 1}'),
    ],
)
def test_check_io_schema_validation_fails(
    monkeypatch: pytest.MonkeyPatch, result: object
) -> None:
    """Failures of the validation are internal server errors.

    Args:
        monkeypatch: Patches of the process of the validation.
        result: Result (or exception) of the process.
    """

    def run(*args: Any, **kwargs: Any) -> object:
        """Return the result of the process, or raise it.

        Args:
            args: Positional arguments of `subprocess.run()`.
            kwargs: Keyword arguments of `subprocess.run()`.

        Returns:
            The result.

        Raises:
            subprocess.CalledProcessError: The process failed.
        """
        if isinstance(result, subprocess.CalledProcessError):
            raise result
        return result

    monkeypatch.setattr(check_module.subprocess, "run", run)
    with pytest.raises(InternalServerError):
        check_io_schema(json.dumps(_schema()), "WDL", timeout=TIMEOUT)


def test_find_problem_bounded_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """At most `MAX_ERRORS` errors are considered.

    Args:
        monkeypatch: Patches of the limit.
    """
    monkeypatch.setattr(io_schema, "MAX_ERRORS", 1)
    schema = _schema()
    schema["properties"].pop("inputs")
    schema["$id"] = "hello/1.0.0"
    # without the limit, the error of `required` would be chosen
    assert find_problem(schema) == (
        "The I/O Schema file (ga4gh-io.schema.json) doesn't validate against "
        "the meta-schema of the GA4GH I/O Profile 0.3.0 at $['$id'] (keyword "
        "'format')."
    )
