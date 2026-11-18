"""Tests of GA4GH I/O Schema files via the API (experimental).

I/O Schemas are registered and served as files of type `IO_SCHEMA` (an
extension of TRS) or `OTHER`; with `custom.io_schema.validation`, they are
checked on registration (see `docs/io-schema.md`).
"""

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from flask.testing import FlaskClient
from pymongo import MongoClient
import pytest

from tests.conftest import admin_client
from tests.mock_data import BASE_PATH, MOCK_TOOL_VERSION_ID
from trs_filer.app import create_app
from trs_filer.custom_config import IoSchemaConfig
from trs_filer.utils import DB, get_custom_config

EXAMPLE = Path(__file__).resolve().parents[3] / "docs" / "examples" / "io-schema"
TOOL_PATH = f"{BASE_PATH}/tools/HELLO"
VERSION_PATH = f"{TOOL_PATH}/versions/1.0.0"
SCHEMA_PATH = "ga4gh-io.schema.json"


def _example() -> dict[str, Any]:
    """Get the registration payload of the example of `docs/io-schema.md`.

    Returns:
        The payload: tool `HELLO` with version `1.0.0`, with a WDL workflow
        and its I/O Schema.
    """
    tool: dict[str, Any] = json.loads(
        (EXAMPLE / "tool.json").read_text(encoding="utf-8")
    )
    return tool


def _schema_file(tool: dict[str, Any]) -> dict[str, Any]:
    """Get the I/O Schema file of the payload of the example.

    Args:
        tool: Payload (cf. `_example()`).

    Returns:
        The file, as registered.
    """
    (file,) = (
        f for f in tool["versions"][0]["files"] if f["tool_file"]["path"] == SCHEMA_PATH
    )
    return file


def _client(overlay: Path, validation: bool, timeout: float = 60) -> FlaskClient:
    """Get a test client of an app with the I/O Schema options set.

    Args:
        overlay: Config overlay.
        validation: Value of `custom.io_schema.validation`.
        timeout: Value of `custom.io_schema.timeout`.

    Returns:
        Test client, whose requests carry an access token of an admin.
    """
    overlay.write_text(
        "custom:\n  io_schema:\n"
        f"    validation: {str(validation).lower()}\n"
        f"    timeout: {timeout}\n"
    )
    client = admin_client(create_app())
    assert get_custom_config().io_schema.validation is validation
    return client


def test_io_schema_config_default(client: FlaskClient) -> None:
    """I/O Schemas are not checked by default.

    Args:
        client: Test client (of an app with the default config).
    """
    assert get_custom_config().io_schema == IoSchemaConfig(validation=False, timeout=10)


def test_io_schema_timeout(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """I/O Schemas not checked within the time limit are rejected.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True, timeout=0.001)
    response = client.put(TOOL_PATH, json=_example())
    assert response.status_code == 400
    assert response.get_json()["detail"].startswith(
        "The I/O Schema file (ga4gh-io.schema.json) could not be checked within "
        "the time limit of 0.001 s"
    )


@pytest.mark.parametrize("validation", [False, True])
def test_io_schema_example_registered_and_served(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path, validation: bool
) -> None:
    """The example registers and its I/O Schema is served, with either setting.

    Clients find it among the files of the descriptor type and fetch it by
    its path.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        validation: Value of `custom.io_schema.validation`.
    """
    client = _client(overlay, validation)
    tool = _example()
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 200, response.get_json()

    response = client.get(f"{VERSION_PATH}/WDL/files")
    assert response.status_code == 200
    assert {"path": SCHEMA_PATH, "file_type": "OTHER"} in response.get_json()

    response = client.get(f"{VERSION_PATH}/WDL/descriptor/{SCHEMA_PATH}")
    assert response.status_code == 200
    wrapper = _schema_file(tool)["file_wrapper"]
    assert response.get_json()["content"] == wrapper["content"]
    assert response.get_json()["checksum"] == wrapper["checksum"]
    schema = json.loads(response.get_json()["content"])
    assert schema["x-ga4gh-workflow"]["trs_tool_id"] == "HELLO"

    # also for versions registered on their own
    version = deepcopy(tool["versions"][0])
    del version["id"]
    response = client.put(f"{TOOL_PATH}/versions/1.0.1", json=version)
    assert response.status_code == 200, response.get_json()


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (
            "not JSON",
            "The I/O Schema file (ga4gh-io.schema.json) is not valid JSON.",
        ),
        (
            json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}),
            "The I/O Schema file (ga4gh-io.schema.json) must name the "
            "meta-schema of the GA4GH I/O Profile that TRS-Filer supports in "
            "'$schema': 'https://raw.githubusercontent.com/elixir-cloud-aai/"
            "ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json'.",
        ),
        (
            json.dumps(
                {
                    "$schema": "https://raw.githubusercontent.com/elixir-cloud-aai/"
                    "ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json",
                    "properties": {},
                }
            ),
            "The I/O Schema file (ga4gh-io.schema.json) doesn't validate "
            "against the meta-schema of the GA4GH I/O Profile 0.3.0 at "
            "$.properties (keyword 'required': 'inputs').",
        ),
    ],
)
def test_io_schema_invalid(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    content: str,
    detail: str,
) -> None:
    """Invalid I/O Schemas are rejected only if they are checked.

    For tools and for versions registered on their own; nothing is stored.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        content: Content of the I/O Schema file.
        detail: Reason of the refusal.
    """
    tool = _example()
    wrapper = _schema_file(tool)["file_wrapper"]
    wrapper["content"] = content
    del wrapper["checksum"]

    client = _client(overlay, validation=True)
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 400
    assert response.get_json() == {
        "title": "Bad request",
        "status": 400,
        "detail": detail,
    }
    tools = mongo_client[DB]["tools"]
    assert tools.find_one({"id": "HELLO"}) is None
    # a version of another tool
    response = client.put(
        f"{BASE_PATH}/tools/OTHER", json=deepcopy(MOCK_TOOL_VERSION_ID)
    )
    assert response.status_code == 200
    version = deepcopy(tool["versions"][0])
    del version["id"]
    response = client.post(f"{BASE_PATH}/tools/OTHER/versions", json=version)
    assert response.status_code == 400
    assert response.get_json()["detail"] == detail

    client = _client(overlay, validation=False)
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 200
    response = client.get(f"{VERSION_PATH}/WDL/descriptor/{SCHEMA_PATH}")
    assert response.get_json()["content"] == content


def test_io_schema_other_files_not_checked(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Only files of type `OTHER` named `ga4gh-io.schema.json` are checked.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True)
    tool = _example()
    file = _schema_file(tool)
    file["file_wrapper"] = {"content": "not JSON"}
    file["tool_file"]["path"] = "notes.json"
    test_file = deepcopy(file)
    test_file["tool_file"] = {"path": SCHEMA_PATH, "file_type": "TEST_FILE"}
    tool["versions"][0]["files"].append(test_file)
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 200, response.get_json()


def test_io_schema_descriptor_type_mismatch(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """I/O Schemas registered for another descriptor type are rejected.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True)
    tool = _example()
    tool["versions"][0]["descriptor_type"] = ["WDL", "CWL"]
    file = deepcopy(_schema_file(tool))
    file["type"] = "CWL"
    tool["versions"][0]["files"].append(file)
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 400
    assert response.get_json()["detail"] == (
        "The I/O Schema file (ga4gh-io.schema.json) of descriptor type CWL "
        "names another descriptor type in 'x-ga4gh-workflow.descriptor_type'."
    )


def test_io_schema_remote_file_checked(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I/O Schemas registered by URL are checked once retrieved.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        monkeypatch: Patches of the retrieval of remote files.
    """
    from trs_filer.ga4gh.trs.endpoints import register_objects  # noqa: PLC0415

    class _Retrieved:
        """Retrieved remote file."""

        text = "not JSON"

    monkeypatch.setattr(
        register_objects, "fetch_remote_file", lambda url, config: _Retrieved()
    )
    client = _client(overlay, validation=True)
    tool = _example()
    _schema_file(tool)["file_wrapper"] = {
        "url": "https://example.org/ga4gh-io.schema.json"
    }
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 400
    assert response.get_json()["detail"] == (
        "The I/O Schema file (ga4gh-io.schema.json) is not valid JSON."
    )


@pytest.mark.parametrize("validation", [False, True])
def test_io_schema_file_type_registered_and_served(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path, validation: bool
) -> None:
    """I/O Schemas of type `IO_SCHEMA` are registered, listed and served.

    The file type is an extension of TRS (experimental): the file is listed
    with the files of its descriptor type, fetched by its path (also in the
    ZIP archive of the files), and checked like files of type `OTHER`.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        validation: Value of `custom.io_schema.validation`.
    """
    client = _client(overlay, validation)
    tool = _example()
    _schema_file(tool)["tool_file"]["file_type"] = "IO_SCHEMA"
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 200, response.get_json()

    response = client.get(f"{VERSION_PATH}/WDL/files")
    assert response.status_code == 200
    assert {"path": SCHEMA_PATH, "file_type": "IO_SCHEMA"} in response.get_json()

    wrapper = _schema_file(tool)["file_wrapper"]
    response = client.get(f"{VERSION_PATH}/WDL/descriptor/{SCHEMA_PATH}")
    assert response.status_code == 200
    assert response.get_json()["content"] == wrapper["content"]
    response = client.get(f"{VERSION_PATH}/PLAIN_WDL/descriptor/{SCHEMA_PATH}")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == wrapper["content"]

    response = client.get(f"{VERSION_PATH}/WDL/files?format=zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.data)) as archive:
        assert archive.read(SCHEMA_PATH).decode() == wrapper["content"]

    # not a test file (the version has none)
    response = client.get(f"{VERSION_PATH}/WDL/tests")
    assert response.status_code == 404


def test_io_schema_file_type_checked_at_any_path(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Files of type `IO_SCHEMA` are checked whatever their path.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True)
    tool = _example()
    file = _schema_file(tool)
    file["tool_file"] = {"path": "schemas/inputs.json", "file_type": "IO_SCHEMA"}
    content = file["file_wrapper"]["content"]
    file["file_wrapper"] = {"content": "not JSON"}
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 400
    # named by its type, not by its path, which isn't echoed
    assert response.get_json()["detail"] == (
        "The I/O Schema file (IO_SCHEMA) is not valid JSON."
    )
    assert client.get(TOOL_PATH).status_code == 404

    # errors of the meta-schema, found in a process of its own, too
    file["file_wrapper"] = {"content": json.dumps({**json.loads(content), "type": 1})}
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 400
    assert response.get_json()["detail"].startswith(
        "The I/O Schema file (IO_SCHEMA) doesn't validate against the meta-schema"
    )

    # a valid one is accepted there, and served by its path
    file["file_wrapper"] = {"content": content}
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 200, response.get_json()
    response = client.get(f"{VERSION_PATH}/WDL/descriptor/schemas%2Finputs.json")
    assert response.status_code == 200
    assert response.get_json()["content"] == content


def test_io_schema_file_type_descriptor_type_mismatch(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Files of type `IO_SCHEMA` for another descriptor type are rejected.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True)
    tool = _example()
    tool["versions"][0]["descriptor_type"] = ["WDL", "CWL"]
    file = deepcopy(_schema_file(tool))
    file["tool_file"] = {"path": "cwl/inputs.json", "file_type": "IO_SCHEMA"}
    file["type"] = "CWL"
    tool["versions"][0]["files"].append(file)
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 400
    assert response.get_json()["detail"] == (
        "The I/O Schema file (IO_SCHEMA) of descriptor type CWL "
        "names another descriptor type in 'x-ga4gh-workflow.descriptor_type'."
    )
    assert client.get(TOOL_PATH).status_code == 404


def test_io_schema_file_type_next_to_other(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """A version may have an `IO_SCHEMA` file and the `OTHER` file, both checked.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True)
    tool = _example()
    file = deepcopy(_schema_file(tool))
    file["tool_file"] = {"path": "io/inputs.json", "file_type": "IO_SCHEMA"}
    tool["versions"][0]["files"].append(file)
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 200, response.get_json()
    listed = client.get(f"{VERSION_PATH}/WDL/files").get_json()
    assert {"path": SCHEMA_PATH, "file_type": "OTHER"} in listed
    assert {"path": "io/inputs.json", "file_type": "IO_SCHEMA"} in listed

    # the `OTHER` file is still checked
    _schema_file(tool)["file_wrapper"] = {"content": "not JSON"}
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 400
    assert response.get_json()["detail"] == (
        "The I/O Schema file (ga4gh-io.schema.json) is not valid JSON."
    )


def test_io_schema_file_type_once_per_descriptor_type(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """A descriptor type of a version has at most one file of type `IO_SCHEMA`.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=False)
    tool = _example()
    file = _schema_file(tool)
    file["tool_file"]["file_type"] = "IO_SCHEMA"
    second = deepcopy(file)
    second["tool_file"]["path"] = "other/ga4gh-io.schema.json"
    tool["versions"][0]["files"].append(second)
    response = client.put(TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 400
    assert response.get_json()["detail"] == (
        "Each descriptor type of a version must have at most one IO_SCHEMA file."
    )
    # nothing is stored
    assert client.get(TOOL_PATH).status_code == 404

    # one per descriptor type
    tool["versions"][0]["descriptor_type"] = ["WDL", "CWL"]
    second["type"] = "CWL"
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 200, response.get_json()


def test_io_schema_file_type_needs_descriptor_type(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Files of type `IO_SCHEMA` belong to a descriptor type, not an image type.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=False)
    tool = _example()
    file = _schema_file(tool)
    file["tool_file"]["file_type"] = "IO_SCHEMA"
    file["type"] = "Docker"
    response = client.put(TOOL_PATH, json=tool)
    assert response.status_code == 400
    assert response.get_json()["detail"].startswith(
        "The type of descriptor, test, I/O Schema and other files must be a "
        "supported descriptor type: "
    )


# The registration of the demo of ga4gh-io-schema (`examples/demo/` at commit
# e80692a), as built by its `register.py` (`--revision <e80692a, in full>
# --repository https://github.com/elixir-cloud-aai/ga4gh-io-schema --dry-run`)
DEMO = Path(__file__).resolve().parents[2] / "data" / "io-schema-demo" / "tool.json"
DEMO_TOOL_PATH = f"{BASE_PATH}/tools/ga4gh-io-schema-demo"
# Identifier of the meta-schema of profile 0.3.0 before ga4gh-io-schema moved
# to elixir-cloud-aai (ga4gh-io-schema #78), which images from `dev` required
# before #312
OLD_META_SCHEMA_ID = (
    "https://raw.githubusercontent.com/uniqueg/ga4gh-io-schema/v0.3.0/"
    "schemas/ga4gh-io-profile.schema.json"
)


def _demo() -> tuple[dict[str, Any], dict[str, Any]]:
    """Get the registration of the demo of ga4gh-io-schema.

    Returns:
        The payload (tool `ga4gh-io-schema-demo` with version `1.0.0`, with
        a WDL workflow and its I/O Schema, of type `OTHER`), and the file of
        its I/O Schema in it.
    """
    tool: dict[str, Any] = json.loads(DEMO.read_text(encoding="utf-8"))
    (file,) = (
        f for f in tool["versions"][0]["files"] if f["tool_file"]["path"] == SCHEMA_PATH
    )
    return tool, file


def test_io_schema_demo_registered(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The demo of ga4gh-io-schema passes the check and is served.

    Regression test of trs-filer #312: its I/O Schema names the meta-schema
    by its URI in elixir-cloud-aai, which was rejected.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True)
    tool, file = _demo()
    response = client.put(DEMO_TOOL_PATH, json=deepcopy(tool))
    assert response.status_code == 200, response.get_json()
    response = client.get(
        f"{DEMO_TOOL_PATH}/versions/1.0.0/WDL/descriptor/{SCHEMA_PATH}"
    )
    assert response.status_code == 200
    assert response.get_json()["content"] == file["file_wrapper"]["content"]


def test_io_schema_old_meta_schema_rejected(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """I/O Schemas naming the meta-schema by its old URI are rejected.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = _client(overlay, validation=True)
    tool, file = _demo()
    schema = json.loads(file["file_wrapper"]["content"])
    schema["$schema"] = OLD_META_SCHEMA_ID
    file["file_wrapper"] = {"content": json.dumps(schema)}
    response = client.put(DEMO_TOOL_PATH, json=tool)
    assert response.status_code == 400
    assert response.get_json()["detail"] == (
        "The I/O Schema file (ga4gh-io.schema.json) must name the meta-schema "
        "of the GA4GH I/O Profile that TRS-Filer supports in '$schema': "
        "'https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/"
        "main/schemas/ga4gh-io-profile.schema.json'."
    )
    assert client.get(DEMO_TOOL_PATH).status_code == 404
