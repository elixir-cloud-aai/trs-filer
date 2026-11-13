"""Tests of GA4GH I/O Schema files via the API (experimental).

I/O Schemas are registered and served as files of type `OTHER`; with
`custom.io_schema.validation`, they are checked on registration (see
`docs/io-schema.md`).
"""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

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
            "'$schema': 'https://raw.githubusercontent.com/uniqueg/"
            "ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json'.",
        ),
        (
            json.dumps(
                {
                    "$schema": "https://raw.githubusercontent.com/uniqueg/"
                    "ga4gh-io-schema/v0.3.0/schemas/ga4gh-io-profile.schema.json",
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
