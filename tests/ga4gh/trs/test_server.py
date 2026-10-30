"""Tests of the endpoint controllers, through the app's test client.

Tools are registered via the API (`PUT /tools/{id}` with the mock tool), so
that they are stored as the app stores them; tests that need other stored
data change the stored tool directly.
"""

from collections.abc import Callable
from copy import deepcopy
from io import BytesIO
from typing import Any, NoReturn
from zipfile import ZipFile

from connexion import App
from flask.testing import FlaskClient
from pymongo.collection import Collection
from pymongo.results import UpdateResult
import pytest

from tests.conftest import COLLECTION_CLASS
from tests.mock_data import (
    BASE_PATH,
    MOCK_ID,
    MOCK_TOOL_CLASS,
    MOCK_TOOL_VERSION_ID,
    MOCK_VERSION_NO_ID,
)
from trs_filer.custom_config import RemoteFilesConfig
from trs_filer.errors.exceptions import RemoteFileError
from trs_filer.remote_files import RemoteFile
from trs_filer.utils import get_custom_config

TOOL_ID = "TOOL01"
VERSION_ID = MOCK_TOOL_VERSION_ID["versions"][0]["id"]
TOOL_URL = f"http://localhost:8080{BASE_PATH}/tools/{TOOL_ID}"
VERSION_PATH = f"{BASE_PATH}/tools/{TOOL_ID}/versions/{VERSION_ID}"
UNKNOWN = "UNKNOWN"
# Paths of the CWL files of the mock tool version (all but the containerfile)
CWL_PATHS = {
    "path_test_cwl",
    "path_other_cwl",
    "path_prim_desc_cwl",
    "path_sec_desc_cwl",
}
NOT_FOUND = {
    "title": "Not found",
    "status": 404,
    "detail": "The requested resource wasn't found.",
}
BAD_REQUEST = {
    "title": "Bad request",
    "status": 400,
    "detail": "The request is malformed.",
}
FileChange = Callable[[dict[str, Any]], None]


def _without_files(tool: dict[str, Any]) -> dict[str, Any]:
    """Get a tool as served, without the files of its versions.

    Args:
        tool: Tool, as stored.

    Returns:
        Copy of the tool, without `_id` and files.
    """
    served = deepcopy(tool)
    served.pop("_id", None)
    for version in served["versions"]:
        version.pop("files", None)
    return served


def _stored(collection: Collection[dict[str, Any]], obj_id: str) -> dict[str, Any]:
    """Get a stored object by its identifier, without `_id`.

    Args:
        collection: Collection of the object.
        obj_id: Identifier of the object.

    Returns:
        The object.
    """
    obj = collection.find_one({"id": obj_id}, projection={"_id": False})
    assert obj is not None
    return obj


def _cwl_files(tool: dict[str, Any]) -> list[dict[str, Any]]:
    """Get the CWL files of the first version of a tool, but containerfiles.

    Args:
        tool: Tool, as stored.

    Returns:
        The files, the test file first.
    """
    return [
        file
        for file in tool["versions"][0]["files"]
        if file["type"] == "CWL" and file["tool_file"]["file_type"] != "CONTAINERFILE"
    ]


@pytest.fixture
def tool(client: FlaskClient, tools: Collection[dict[str, Any]]) -> dict[str, Any]:
    """Tool registered via the API (the mock tool, with identifier `TOOL_ID`).

    Args:
        client: Test client.
        tools: Collection `tools`.

    Returns:
        The tool, as stored.
    """
    response = client.put(
        f"{BASE_PATH}/tools/{TOOL_ID}", json=deepcopy(MOCK_TOOL_VERSION_ID)
    )
    assert response.status_code == 200
    assert response.get_json() == TOOL_ID
    return _stored(tools, TOOL_ID)


@pytest.fixture
def set_file(
    tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> Callable[[FileChange], None]:
    """Change the stored CWL test file of the registered tool version.

    Args:
        tool: Registered tool.
        tools: Collection `tools`.

    Returns:
        Function that applies a change to the stored CWL test file.
    """

    def _set(change: FileChange) -> None:
        """Apply a change to the stored CWL test file.

        Args:
            change: Function changing a file in place.
        """
        stored = deepcopy(tool)
        file = _cwl_files(stored)[0]
        assert file["tool_file"]["file_type"] == "TEST_FILE"
        change(file)
        tools.replace_one({"id": TOOL_ID}, stored)

    return _set


def _zip_contents(client: FlaskClient) -> dict[str, bytes]:
    """Get the CWL files of the registered tool version as a ZIP archive.

    Args:
        client: Test client.

    Returns:
        The contents of the files in the archive, by path.
    """
    response = client.get(f"{VERSION_PATH}/CWL/files?format=zip")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    with ZipFile(BytesIO(response.get_data())) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


# GET /toolClasses
def test_toolClassesGet_empty(client: FlaskClient) -> None:
    """Without tool classes, the list is empty.

    Args:
        client: Test client.
    """
    response = client.get(f"{BASE_PATH}/toolClasses")
    assert response.status_code == 200
    assert response.get_json() == []


def test_toolClassesGet(client: FlaskClient, tool: dict[str, Any]) -> None:
    """Tool classes created with tools are listed.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{BASE_PATH}/toolClasses")
    assert response.status_code == 200
    assert response.get_json() == [MOCK_TOOL_CLASS]


# GET /tools
def test_toolsGet(client: FlaskClient, tool: dict[str, Any]) -> None:
    """Tools are listed without the files of their versions, with page links.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{BASE_PATH}/tools")
    assert response.status_code == 200
    assert response.get_json() == [_without_files(tool)]
    base_url = f"http://localhost{BASE_PATH}/tools"
    assert response.headers["next_page"] == f"{base_url}?offset=1000&limit=1000"
    assert response.headers["last_page"] == f"{base_url}?offset=0&limit=1000"
    assert response.headers["self_link"] == base_url
    assert response.headers["current_offset"] == "0"
    assert response.headers["current_limit"] == "1000"


def test_toolsGet_pagination(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Pages of tools start at the offset and have at most `limit` tools.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    data = deepcopy(MOCK_TOOL_VERSION_ID)
    # Another tool class: registering one identical to a stored one fails
    # (#148)
    data["toolclass"]["id"] = "other"
    response = client.put(f"{BASE_PATH}/tools/TOOL02", json=data)
    assert response.status_code == 200
    response = client.get(f"{BASE_PATH}/tools?offset=1&limit=1")
    assert response.status_code == 200
    assert response.get_json() == [_without_files(_stored(tools, "TOOL02"))]
    base_url = f"http://localhost{BASE_PATH}/tools"
    assert response.headers["next_page"] == f"{base_url}?offset=2&limit=1"
    assert response.headers["last_page"] == f"{base_url}?offset=0&limit=1"
    assert response.headers["self_link"] == f"{base_url}?offset=1&limit=1"
    assert response.headers["current_offset"] == "1"
    assert response.headers["current_limit"] == "1"


@pytest.mark.parametrize("query", ["limit=-1", "offset=-1"])
def test_toolsGet_pagination_negative(
    client: FlaskClient, tool: dict[str, Any], query: str
) -> None:
    """Negative offsets and limits are refused.

    Args:
        client: Test client.
        tool: Registered tool.
        query: Query string with a negative value.
    """
    response = client.get(f"{BASE_PATH}/tools?{query}")
    assert response.status_code == 422


def test_toolsGet_filters(client: FlaskClient, tool: dict[str, Any]) -> None:
    """Tools matching all filters are listed.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    version = tool["versions"][0]
    image = version["images"][0]
    response = client.get(
        f"{BASE_PATH}/tools",
        query_string={
            "id": TOOL_ID,
            "alias": tool["aliases"][0],
            "toolClass": tool["toolclass"]["name"],
            "descriptorType": version["descriptor_type"][0],
            "registry": image["registry_host"],
            "organization": tool["organization"],
            "name": image["image_name"],
            "toolname": tool["name"],
            "description": tool["description"],
            "author": version["author"][0],
            "checker": "true",
        },
    )
    assert response.status_code == 200
    assert response.get_json() == [_without_files(tool)]


@pytest.mark.parametrize(
    "query",
    [
        "id=OTHER",
        "alias=other",
        "toolClass=other",
        "descriptorType=WDL",
        "registry=other",
        "organization=other",
        "name=other",
        "toolname=other",
        "description=other",
        "author=other",
        "checker=false",
    ],
)
def test_toolsGet_filters_no_match(
    client: FlaskClient, tool: dict[str, Any], query: str
) -> None:
    """Tools not matching a filter are not listed.

    Args:
        client: Test client.
        tool: Registered tool.
        query: Query string with a filter that the tool doesn't match.
    """
    response = client.get(f"{BASE_PATH}/tools?{query}")
    assert response.status_code == 200
    assert response.get_json() == []


# GET /tools/{id}
def test_toolsIdGet(client: FlaskClient, tool: dict[str, Any]) -> None:
    """A tool is served without the files of its versions.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{BASE_PATH}/tools/{TOOL_ID}")
    assert response.status_code == 200
    assert response.get_json() == _without_files(tool)
    assert tool["url"] == TOOL_URL


def test_toolsIdGet_NotFound(client: FlaskClient) -> None:
    """Unknown tools are not found.

    Args:
        client: Test client.
    """
    response = client.get(f"{BASE_PATH}/tools/{UNKNOWN}")
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND


# GET /tools/{id}/versions
def test_toolsIdVersionsGet(client: FlaskClient, tool: dict[str, Any]) -> None:
    """The versions of a tool are served without their files.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{BASE_PATH}/tools/{TOOL_ID}/versions")
    assert response.status_code == 200
    assert response.get_json() == _without_files(tool)["versions"]


def test_toolsIdVersionsGet_NotFound(client: FlaskClient) -> None:
    """Versions of unknown tools are not found.

    Args:
        client: Test client.
    """
    response = client.get(f"{BASE_PATH}/tools/{UNKNOWN}/versions")
    assert response.status_code == 404


# GET /tools/{id}/versions/{version_id}
def test_toolsIdVersionsVersionIdGet(client: FlaskClient, tool: dict[str, Any]) -> None:
    """A tool version is served without its files.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(VERSION_PATH)
    assert response.status_code == 200
    assert response.get_json() == _without_files(tool)["versions"][0]
    assert response.get_json()["url"] == f"{TOOL_URL}/versions/{VERSION_ID}"


UNKNOWN_VERSIONS = pytest.mark.parametrize(
    "version_path",
    [
        f"{BASE_PATH}/tools/{UNKNOWN}/versions/{VERSION_ID}",
        f"{BASE_PATH}/tools/{TOOL_ID}/versions/{UNKNOWN}",
    ],
    ids=["tool", "version"],
)


@UNKNOWN_VERSIONS
def test_toolsIdVersionsVersionIdGet_NotFound(
    client: FlaskClient, tool: dict[str, Any], version_path: str
) -> None:
    """Unknown versions, and versions of unknown tools, are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        version_path: Path of an unknown version.
    """
    response = client.get(version_path)
    assert response.status_code == 404


# GET /tools/{id}/versions/{version_id}/containerfile
def test_toolsIdVersionsVersionIdContainerfileGet(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """The containerfiles of a version are served.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/containerfile")
    assert response.status_code == 200
    assert response.get_json() == [
        file["file_wrapper"]
        for file in tool["versions"][0]["files"]
        if file["tool_file"]["file_type"] == "CONTAINERFILE"
    ]


@UNKNOWN_VERSIONS
def test_toolsIdVersionsVersionIdContainerfileGet_NotFound(
    client: FlaskClient, tool: dict[str, Any], version_path: str
) -> None:
    """Containerfiles of unknown versions are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        version_path: Path of an unknown version.
    """
    response = client.get(f"{version_path}/containerfile")
    assert response.status_code == 404


def test_toolsIdVersionsVersionIdContainerfileGet_none_NotFound(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Containerfiles of versions without containerfiles are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    stored = deepcopy(tool)
    stored["versions"][0]["files"] = _cwl_files(tool)
    tools.replace_one({"id": TOOL_ID}, stored)
    response = client.get(f"{VERSION_PATH}/containerfile")
    assert response.status_code == 404


# GET /tools/{id}/versions/{version_id}/{type}/descriptor
def test_toolsIdVersionsVersionIdTypeDescriptorGet(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """The primary descriptor of a type is served.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/CWL/descriptor")
    assert response.status_code == 200
    (descriptor,) = (
        file
        for file in _cwl_files(tool)
        if file["tool_file"]["file_type"] == "PRIMARY_DESCRIPTOR"
    )
    assert response.get_json() == descriptor["file_wrapper"]


@UNKNOWN_VERSIONS
def test_toolsIdVersionsVersionIdTypeDescriptorGet_NotFound(
    client: FlaskClient, tool: dict[str, Any], version_path: str
) -> None:
    """Descriptors of unknown versions are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        version_path: Path of an unknown version.
    """
    response = client.get(f"{version_path}/CWL/descriptor")
    assert response.status_code == 404


def test_toolsIdVersionsVersionIdTypeDescriptorGet_type_NotFound(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """Descriptors of types without a primary descriptor are not found.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/WDL/descriptor")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "path", ["descriptor", "descriptor/path_other_cwl", "tests", "files"]
)
@pytest.mark.parametrize("descriptor_type", ["FOO", "SMK"])
def test_type_BadRequest(
    client: FlaskClient, tool: dict[str, Any], path: str, descriptor_type: str
) -> None:
    """Unknown and unsupported descriptor types are refused.

    `FOO` is refused by the validation of requests, `SMK` (in the spec, but
    not supported by the app) by the controllers.

    Args:
        client: Test client.
        tool: Registered tool.
        path: Path below the type.
        descriptor_type: Descriptor type.
    """
    response = client.get(f"{VERSION_PATH}/{descriptor_type}/{path}")
    assert response.status_code == 400
    assert response.get_json() == BAD_REQUEST


# GET /tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}
@pytest.mark.parametrize("path", sorted(CWL_PATHS))
def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet(
    client: FlaskClient, tool: dict[str, Any], path: str
) -> None:
    """Files of a type are served by their paths.

    Args:
        client: Test client.
        tool: Registered tool.
        path: Path of a file.
    """
    response = client.get(f"{VERSION_PATH}/CWL/descriptor/{path}")
    assert response.status_code == 200
    (file,) = (file for file in _cwl_files(tool) if file["tool_file"]["path"] == path)
    assert response.get_json() == file["file_wrapper"]


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_encoded(
    client: FlaskClient, set_file: Callable[[FileChange], None]
) -> None:
    """Relative paths are percent-decoded once more, as the spec requires.

    Args:
        client: Test client.
        set_file: Changes the stored test file.
    """
    set_file(lambda file: file["tool_file"].update(path="dir/a b.cwl"))
    response = client.get(f"{VERSION_PATH}/CWL/descriptor/dir%252Fa%2520b.cwl")
    assert response.status_code == 200
    assert response.get_json()["content"] == "content"


@pytest.mark.parametrize(
    "path",
    [
        f"/tools/{UNKNOWN}/versions/{VERSION_ID}/CWL/descriptor/path_other_cwl",
        f"/tools/{TOOL_ID}/versions/{UNKNOWN}/CWL/descriptor/path_other_cwl",
        f"/tools/{TOOL_ID}/versions/{VERSION_ID}/WDL/descriptor/path_other_cwl",
        f"/tools/{TOOL_ID}/versions/{VERSION_ID}/CWL/descriptor/unknown",
    ],
    ids=["tool", "version", "type", "path"],
)
def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_NotFound(
    client: FlaskClient, tool: dict[str, Any], path: str
) -> None:
    """Unknown files are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        path: Path of an unknown file.
    """
    response = client.get(f"{BASE_PATH}{path}")
    assert response.status_code == 404


# GET /tools/{id}/versions/{version_id}/{type}/tests
def test_toolsIdVersionsVersionIdTypeTestsGet(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """The test files of a type are served.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/CWL/tests")
    assert response.status_code == 200
    assert response.get_json() == [
        file["file_wrapper"]
        for file in _cwl_files(tool)
        if file["tool_file"]["file_type"] == "TEST_FILE"
    ]


@UNKNOWN_VERSIONS
def test_toolsIdVersionsVersionIdTypeTestsGet_NotFound(
    client: FlaskClient, tool: dict[str, Any], version_path: str
) -> None:
    """Test files of unknown versions are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        version_path: Path of an unknown version.
    """
    response = client.get(f"{version_path}/CWL/tests")
    assert response.status_code == 404


def test_toolsIdVersionsVersionIdTypeTestsGet_type_NotFound(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """Test files of types without any are not found.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/WDL/tests")
    assert response.status_code == 404


# GET /tools/{id}/versions/{version_id}/{type}/files
def test_toolsIdVersionsVersionIdTypeFilesGet(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """The files of a type are listed, without containerfiles.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/CWL/files")
    assert response.status_code == 200
    assert response.get_json() == [file["tool_file"] for file in _cwl_files(tool)]


def test_toolsIdVersionsVersionIdTypeFilesGet_other_type(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """Versions without files of a type list none.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/WDL/files")
    assert response.status_code == 200
    assert response.get_json() == []


@UNKNOWN_VERSIONS
def test_toolsIdVersionsVersionIdTypeFilesGet_NotFound(
    client: FlaskClient, tool: dict[str, Any], version_path: str
) -> None:
    """Files of unknown versions are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        version_path: Path of an unknown version.
    """
    response = client.get(f"{version_path}/CWL/files")
    assert response.status_code == 404


# GET /tools/{id}/versions/{version_id}/{type}/files?format=zip
def test_toolsIdVersionsVersionIdTypeFilesGet_zip(
    client: FlaskClient, tool: dict[str, Any]
) -> None:
    """The files of a type are served as a ZIP archive, by path.

    Args:
        client: Test client.
        tool: Registered tool.
    """
    response = client.get(f"{VERSION_PATH}/CWL/files?format=zip")
    assert response.headers["Content-Disposition"] == (
        f"attachment; filename={TOOL_ID}_{VERSION_ID}_CWL.zip"
    )
    assert _zip_contents(client) == dict.fromkeys(CWL_PATHS, b"content")


@pytest.mark.parametrize(
    ("content", "expected"), [(42, b"42"), (b"raw", b"raw")], ids=["int", "bytes"]
)
def test_toolsIdVersionsVersionIdTypeFilesGet_zip_content_types(
    client: FlaskClient,
    set_file: Callable[[FileChange], None],
    content: object,
    expected: bytes,
) -> None:
    """Stored content that is not text is archived as is, or as text.

    Args:
        client: Test client.
        set_file: Changes the stored test file.
        content: Stored content.
        expected: Archived content.
    """
    set_file(lambda file: file["file_wrapper"].update(content=content))
    assert _zip_contents(client)["path_test_cwl"] == expected


def _url_only(file: dict[str, Any]) -> None:
    """Remove the content of a file, keeping a URL.

    Args:
        file: The file.
    """
    file["file_wrapper"].pop("content")
    file["file_wrapper"]["url"] = "https://example.com/file.txt"


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_url(
    app: App,
    client: FlaskClient,
    set_file: Callable[[FileChange], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files without stored content are retrieved from their URLs, as configured.

    Args:
        app: FOCA app.
        client: Test client.
        set_file: Changes the stored test file.
        monkeypatch: Patches of the retrieval of files.
    """
    calls: list[tuple[str, RemoteFilesConfig]] = []

    def _fetch(url: str, config: RemoteFilesConfig) -> RemoteFile:
        """Record the call and return content.

        Args:
            url: URL of the file.
            config: Settings for retrieving files.

        Returns:
            Retrieved content.
        """
        calls.append((url, config))
        return RemoteFile(content=b"from-url")

    monkeypatch.setattr("trs_filer.ga4gh.trs.server.fetch_remote_file", _fetch)
    set_file(_url_only)
    contents = _zip_contents(client)
    assert contents == {
        **dict.fromkeys(CWL_PATHS, b"content"),
        "path_test_cwl": b"from-url",
    }
    with app.app.app_context():
        assert calls == [
            ("https://example.com/file.txt", get_custom_config().remote_files)
        ]


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_no_content_NotFound(
    client: FlaskClient, set_file: Callable[[FileChange], None]
) -> None:
    """Archives with files without content and URL are not found.

    Args:
        client: Test client.
        set_file: Changes the stored test file.
    """
    set_file(lambda file: file["file_wrapper"].clear())
    response = client.get(f"{VERSION_PATH}/CWL/files?format=zip")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("error", "status"),
    [(RemoteFileError("refused"), 404), (ValueError("unexpected"), 500)],
    ids=["retrieval", "unexpected"],
)
def test_toolsIdVersionsVersionIdTypeFilesGet_zip_errors(
    client: FlaskClient,
    set_file: Callable[[FileChange], None],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
) -> None:
    """Archives of files that can't be retrieved are not found; other errors fail.

    Args:
        client: Test client.
        set_file: Changes the stored test file.
        monkeypatch: Patches of the retrieval of files.
        error: Error of the retrieval.
        status: Expected status code.
    """

    def _raise(url: str, config: RemoteFilesConfig) -> NoReturn:
        """Fail to retrieve a file.

        Args:
            url: URL of the file.
            config: Settings for retrieving files.

        Raises:
            Exception: Always, `error`.
        """
        raise error

    monkeypatch.setattr("trs_filer.ga4gh.trs.server.fetch_remote_file", _raise)
    set_file(_url_only)
    response = client.get(f"{VERSION_PATH}/CWL/files?format=zip")
    assert response.status_code == status


# POST /tools
def test_postTool(client: FlaskClient, tools: Collection[dict[str, Any]]) -> None:
    """Tools are registered with generated identifiers, URLs and meta versions.

    Args:
        client: Test client.
        tools: Collection `tools`.
    """
    response = client.post(f"{BASE_PATH}/tools", json=deepcopy(MOCK_TOOL_VERSION_ID))
    assert response.status_code == 200
    tool_id = response.get_json()
    stored = _stored(tools, tool_id)
    assert stored["url"] == f"http://localhost:8080{BASE_PATH}/tools/{tool_id}"
    assert stored["meta_version"] == "1"
    assert stored["name"] == MOCK_TOOL_VERSION_ID["name"]
    response = client.get(f"{BASE_PATH}/tools/{tool_id}")
    assert response.get_json() == _without_files(stored)


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_tool_invalid(client: FlaskClient, method: str) -> None:
    """Invalid tools are refused.

    Args:
        client: Test client.
        method: Method of the request.
    """
    path = f"{BASE_PATH}/tools" + ("" if method == "POST" else f"/{TOOL_ID}")
    response = client.open(path, method=method, json={"versions": "none"})
    assert response.status_code == 400


# PUT /tools/{id}
def test_putTool(tool: dict[str, Any]) -> None:
    """Tools are registered with the given identifiers.

    Args:
        tool: Registered tool.
    """
    assert tool["id"] == TOOL_ID
    assert tool["url"] == TOOL_URL
    assert tool["versions"][0]["id"] == VERSION_ID


def test_putTool_update(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Tools are replaced.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data["name"] = "other"
    response = client.put(f"{BASE_PATH}/tools/{TOOL_ID}", json=data)
    assert response.status_code == 200
    assert response.get_json() == TOOL_ID
    assert _stored(tools, TOOL_ID)["name"] == "other"
    assert tools.count_documents({}) == 1


# DELETE /tools/{id}
def test_deleteTool(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Tools are deleted.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    response = client.delete(f"{BASE_PATH}/tools/{TOOL_ID}")
    assert response.status_code == 200
    assert response.get_json() == TOOL_ID
    assert tools.count_documents({}) == 0
    assert client.get(f"{BASE_PATH}/tools/{TOOL_ID}").status_code == 404


def test_deleteTool_NotFound(client: FlaskClient) -> None:
    """Unknown tools are not found.

    Args:
        client: Test client.
    """
    response = client.delete(f"{BASE_PATH}/tools/{UNKNOWN}")
    assert response.status_code == 404


# POST /tools/{id}/versions
def test_postToolVersion(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Versions are added with generated identifiers.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    response = client.post(
        f"{BASE_PATH}/tools/{TOOL_ID}/versions", json=deepcopy(MOCK_VERSION_NO_ID)
    )
    assert response.status_code == 200
    version_id = response.get_json()
    versions = _stored(tools, TOOL_ID)["versions"]
    assert [version["id"] for version in versions] == [VERSION_ID, version_id]
    assert versions[1]["url"] == f"{TOOL_URL}/versions/{version_id}"


def test_postToolVersion_NotFound(client: FlaskClient) -> None:
    """Versions of unknown tools are not found.

    Args:
        client: Test client.
    """
    response = client.post(
        f"{BASE_PATH}/tools/{UNKNOWN}/versions", json=deepcopy(MOCK_VERSION_NO_ID)
    )
    assert response.status_code == 404


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_toolVersion_invalid(
    client: FlaskClient, tool: dict[str, Any], method: str
) -> None:
    """Invalid versions are refused.

    Args:
        client: Test client.
        tool: Registered tool.
        method: Method of the request.
    """
    path = f"{BASE_PATH}/tools/{TOOL_ID}/versions" + (
        "" if method == "POST" else f"/{VERSION_ID}"
    )
    response = client.open(path, method=method, json={"files": "none"})
    assert response.status_code == 400


# PUT /tools/{id}/versions/{version_id}
def test_putToolVersion(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Versions are added with the given identifiers.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    response = client.put(
        f"{BASE_PATH}/tools/{TOOL_ID}/versions/other",
        json=deepcopy(MOCK_VERSION_NO_ID),
    )
    assert response.status_code == 200
    assert response.get_json() == "other"
    versions = _stored(tools, TOOL_ID)["versions"]
    assert [version["id"] for version in versions] == [VERSION_ID, "other"]


def test_putToolVersion_update(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Versions are replaced.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    data = deepcopy(MOCK_VERSION_NO_ID)
    data["name"] = "other"
    response = client.put(VERSION_PATH, json=data)
    assert response.status_code == 200
    assert response.get_json() == VERSION_ID
    versions = _stored(tools, TOOL_ID)["versions"]
    assert [(version["id"], version["name"]) for version in versions] == [
        (VERSION_ID, "other")
    ]


# DELETE /tools/{id}/versions/{version_id}
def test_deleteToolVersion(
    client: FlaskClient, tool: dict[str, Any], tools: Collection[dict[str, Any]]
) -> None:
    """Versions are deleted.

    Args:
        client: Test client.
        tool: Registered tool.
        tools: Collection `tools`.
    """
    response = client.delete(VERSION_PATH)
    assert response.status_code == 200
    assert response.get_json() == VERSION_ID
    assert _stored(tools, TOOL_ID)["versions"] == []


@UNKNOWN_VERSIONS
def test_deleteToolVersion_NotFound(
    client: FlaskClient, tool: dict[str, Any], version_path: str
) -> None:
    """Unknown versions are not found.

    Args:
        client: Test client.
        tool: Registered tool.
        version_path: Path of an unknown version.
    """
    response = client.delete(version_path)
    assert response.status_code == 404


def test_deleteToolVersion_InternalServerError(
    client: FlaskClient, tool: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deletions that find the version but don't remove it fail.

    Args:
        client: Test client.
        tool: Registered tool.
        monkeypatch: Patches of the update of the collection.
    """
    monkeypatch.setattr(
        COLLECTION_CLASS,
        "update_one",
        lambda *args, **kwargs: UpdateResult(
            {"n": 1, "nModified": 0}, acknowledged=True
        ),
    )
    response = client.delete(VERSION_PATH)
    assert response.status_code == 500


# POST /toolClasses
def test_postToolClass(
    client: FlaskClient, toolclasses: Collection[dict[str, Any]]
) -> None:
    """Tool classes are registered with generated identifiers.

    Args:
        client: Test client.
        toolclasses: Collection `toolclasses`.
    """
    data = {"name": "Workflow", "description": "A workflow."}
    response = client.post(f"{BASE_PATH}/toolClasses", json=data)
    assert response.status_code == 200
    tool_class_id = response.get_json()
    assert _stored(toolclasses, tool_class_id) == {**data, "id": tool_class_id}


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_toolClass_invalid(client: FlaskClient, method: str) -> None:
    """Invalid tool classes are refused.

    Args:
        client: Test client.
        method: Method of the request.
    """
    path = f"{BASE_PATH}/toolClasses" + ("" if method == "POST" else f"/{MOCK_ID}")
    response = client.open(path, method=method, json={"name": 1})
    assert response.status_code == 400


# PUT /toolClasses/{id}
def test_putToolClass(
    client: FlaskClient, toolclasses: Collection[dict[str, Any]]
) -> None:
    """Tool classes are registered with the given identifiers, and replaced.

    Args:
        client: Test client.
        toolclasses: Collection `toolclasses`.
    """
    for description in ["A workflow.", "Another workflow."]:
        data = {"name": "Workflow", "description": description}
        response = client.put(f"{BASE_PATH}/toolClasses/{MOCK_ID}", json=data)
        assert response.status_code == 200
        assert response.get_json() == MOCK_ID
        assert _stored(toolclasses, MOCK_ID) == {**data, "id": MOCK_ID}
    assert toolclasses.count_documents({}) == 1


# DELETE /toolClasses/{id}
def test_deleteToolClass(
    client: FlaskClient, toolclasses: Collection[dict[str, Any]]
) -> None:
    """Tool classes are deleted.

    Args:
        client: Test client.
        toolclasses: Collection `toolclasses`.
    """
    data = {"name": "Workflow", "description": "A workflow."}
    response = client.put(f"{BASE_PATH}/toolClasses/{MOCK_ID}", json=data)
    assert response.status_code == 200
    response = client.delete(f"{BASE_PATH}/toolClasses/{MOCK_ID}")
    assert response.status_code == 200
    assert response.get_json() == MOCK_ID
    assert toolclasses.count_documents({}) == 0


def test_deleteToolClass_NotFound(client: FlaskClient) -> None:
    """Unknown tool classes are not found.

    Args:
        client: Test client.
    """
    response = client.delete(f"{BASE_PATH}/toolClasses/{UNKNOWN}")
    assert response.status_code == 404


def test_deleteToolClass_BadRequest(
    client: FlaskClient, tool: dict[str, Any], toolclasses: Collection[dict[str, Any]]
) -> None:
    """Tool classes of tools are not deleted.

    Args:
        client: Test client.
        tool: Registered tool, whose tool class was created with it.
        toolclasses: Collection `toolclasses`.
    """
    response = client.delete(f"{BASE_PATH}/toolClasses/{MOCK_TOOL_CLASS['id']}")
    assert response.status_code == 400
    assert toolclasses.count_documents({}) == 1
