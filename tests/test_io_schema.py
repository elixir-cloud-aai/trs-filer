"""Tests of the checks of GA4GH I/O Schema files (`trs_filer.io_schema`)."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, NoReturn

import pytest

from trs_filer import io_schema
from trs_filer.errors.exceptions import InternalServerError, InvalidRequest
from trs_filer.io_schema import (
    IO_SCHEMA_FILE_NAME,
    META_SCHEMA_DIR,
    META_SCHEMA_ID,
    find_problem,
    is_io_schema_file,
    main,
)
from trs_filer.io_schema import check as check_module
from trs_filer.io_schema.check import check_io_schema

# Time limit of the checks of the tests, in seconds
TIMEOUT = 60

ROOT = Path(__file__).resolve().parents[1]
# The example of `docs/io-schema.md`: a WDL workflow, its I/O Schema and the
# registration payload with both
EXAMPLE = ROOT / "docs" / "examples" / "io-schema"
# The vendored meta-schema of the profile, by path relative to
# `META_SCHEMA_DIR`, with the SHA-256 checksums of the files of
# uniqueg/ga4gh-io-schema (`schemas/`) at commit 573f65e
VENDORED = {
    "ga4gh-io-profile.schema.json": (
        "65e0971a61ea57c8f0a4e50c5127089fd9fc3ae7385ce8788bdc05a822bf315f"
    ),
    "vocabularies/annotations.schema.json": (
        "8a479bc5adc05b84eed171954484fb2caf2746b6a2f681e366519dba95101dc5"
    ),
    "vocabularies/file.schema.json": (
        "71c35c70e852385d9b07cdf5388164827ccf168cabf069f2a437e7a7d1790908"
    ),
    "vocabularies/outputs.schema.json": (
        "258378e87087f1a8122a22df192b1d33e225fafdfd01705c4a69da168329dfcc"
    ),
    "vocabularies/parameter.schema.json": (
        "f0e25228d50b73168039a7b7c424b460c0f8882fa6eb53d0886a3fd086cf0870"
    ),
    "vocabularies/ui-widgets.schema.json": (
        "23829092a9b661903213ab6505df00549ea96806f0c5666c6a7bd0b149c56cc1"
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


@pytest.mark.parametrize("content", ["", "{", "not JSON", "[1,"])
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


def test_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The validator reads a schema from standard input and writes the result.

    Args:
        monkeypatch: Patches of standard input.
        capsys: Captured standard output.
    """
    invalid = _schema()
    invalid["properties"].pop("inputs")
    for schema, problem in ((_schema(), None), (invalid, find_problem(invalid))):
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps(schema)))
        main()
        assert json.loads(capsys.readouterr().out) == {"problem": problem}


def test_main_module() -> None:
    """The validator runs as a module (`python -m trs_filer.io_schema`)."""
    import trs_filer.io_schema.__main__  # noqa: F401, PLC0415

    result = subprocess.run(
        [sys.executable, "-I", "-m", "trs_filer.io_schema"],
        input=json.dumps(_schema()),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"problem": None}


def test_check_io_schema_timeout() -> None:
    """Schemas not checked within the time limit are rejected."""
    content = json.dumps(_schema())
    with pytest.raises(InvalidRequest) as exc_info:
        check_io_schema(content, "WDL", timeout=0.001)
    assert exc_info.value.description == (
        "The I/O Schema file (ga4gh-io.schema.json) could not be checked within "
        "the time limit of 0.001 s; simplify it (e.g., nest its schemas less "
        "deeply)."
    )


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CalledProcessError(1, "python"),
        subprocess.CompletedProcess("python", 0, stdout="not JSON"),
        subprocess.CompletedProcess("python", 0, stdout="{}"),
        subprocess.CompletedProcess("python", 0, stdout="[]"),
        subprocess.CompletedProcess("python", 0, stdout='{"problem": 1}'),
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
