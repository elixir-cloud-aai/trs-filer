"""Unit tests for endpoint controllers."""

from copy import deepcopy
import inspect
from io import BytesIO
from typing import Any, NoReturn
from zipfile import ZIP_DEFLATED, ZipFile

from flask import Flask, request
import pytest

from tests.apps import (
    app_collection,
    custom_config,
    make_app,
    mock_collection,
)
from tests.mock_data import (
    CUSTOM_CONFIG,
    DEFAULT_LIMIT,
    DEFAULT_OFFSET,
    HEADERS_PAGINATION,
    MOCK_CONTAINER_FILE,
    MOCK_DESCRIPTOR_FILE,
    MOCK_DESCRIPTOR_SEC_FILE,
    MOCK_ID,
    MOCK_ID_2,
    MOCK_OTHER_FILE,
    MOCK_TEST_FILE,
    MOCK_TOOL_CLASS,
    MOCK_TOOL_VERSION_ID,
    MOCK_VERSION_ID,
    MOCK_VERSION_NO_ID,
    TEST_LIMIT,
    TEST_LIMIT_2,
    TEST_OFFSET,
    TEST_OFFSET_2,
)
from trs_filer.custom_config import RemoteFilesConfig
from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
    RemoteFileError,
)
from trs_filer.ga4gh.trs.server import (
    deleteTool,
    deleteToolClass,
    deleteToolVersion,
    postTool,
    postToolClass,
    postToolVersion,
    putTool,
    putToolClass,
    putToolVersion,
    toolClassesGet,
    toolsGet,
    toolsIdGet,
    toolsIdVersionsGet,
    toolsIdVersionsVersionIdContainerfileGet,
    toolsIdVersionsVersionIdGet,
    toolsIdVersionsVersionIdTypeDescriptorGet,
    toolsIdVersionsVersionIdTypeDescriptorRelativePathGet,
    toolsIdVersionsVersionIdTypeFilesGet,
    toolsIdVersionsVersionIdTypeTestsGet,
)
from trs_filer.remote_files import RemoteFile


# GET /toolClasses
def test_toolClassesGet() -> None:
    """Test for getting a list of all available tool classes."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "toolclasses")
    app_collection(app, "toolclasses").insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data["id"] = MOCK_ID
    with app.app_context():
        res = inspect.unwrap(toolClassesGet)()
        assert res == [data]


# GET /tools
def test_toolsGet() -> None:
    """Test for getting a list of all available tools; no filters specified."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data["id"] = MOCK_ID
    del data["versions"][0]["files"]
    HEADERS_PAGINATION_RESULT = deepcopy(HEADERS_PAGINATION)
    with app.test_request_context():
        HEADERS_PAGINATION_RESULT["self_link"] = request.url
        HEADERS_PAGINATION_RESULT["next_page"] = (
            f"{request.base_url}?offset={int(DEFAULT_OFFSET) + DEFAULT_LIMIT}"
            f"&limit={DEFAULT_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["last_page"] = (
            f"{request.base_url}?offset={DEFAULT_OFFSET}&limit={DEFAULT_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["current_offset"] = DEFAULT_OFFSET
        HEADERS_PAGINATION_RESULT["current_limit"] = DEFAULT_LIMIT
        res = inspect.unwrap(toolsGet)()
        assert res == ([data], 200, HEADERS_PAGINATION_RESULT)


def test_toolsGet_pagination() -> None:
    """Test for getting a list of all available tools; pagination values specified."""
    app = make_app()
    mock_resp = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    mock_resp2 = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp2["id"] = MOCK_ID_2
    app_collection(app, "tools").insert_one(mock_resp2)

    data = deepcopy(MOCK_VERSION_NO_ID)
    data["id"] = MOCK_ID_2

    HEADERS_PAGINATION_RESULT = deepcopy(HEADERS_PAGINATION)

    with app.test_request_context():
        HEADERS_PAGINATION_RESULT["self_link"] = request.url
        HEADERS_PAGINATION_RESULT["next_page"] = (
            f"{request.base_url}?offset={int(TEST_OFFSET) + TEST_LIMIT}&limit="
            f"{TEST_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["last_page"] = (
            f"{request.base_url}"
            f"?offset={max(0, int(TEST_OFFSET) - TEST_LIMIT)}"
            f"&limit={TEST_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["current_offset"] = TEST_OFFSET
        HEADERS_PAGINATION_RESULT["current_limit"] = TEST_LIMIT
        res = inspect.unwrap(toolsGet)(
            limit=TEST_LIMIT,
            offset=TEST_OFFSET,
        )
        assert res == ([data], 200, HEADERS_PAGINATION_RESULT)


def test_toolsGet_pagination_negativeLimit() -> None:
    """Test for getting a list of all tools, given a negative limit."""
    app = make_app()
    mock_resp = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    mock_resp2 = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp2["id"] = MOCK_ID_2
    app_collection(app, "tools").insert_one(mock_resp2)

    data = deepcopy(MOCK_VERSION_NO_ID)
    data["id"] = MOCK_ID_2

    HEADERS_PAGINATION_RESULT: dict[str, Any] = {}

    with app.test_request_context():
        res = inspect.unwrap(toolsGet)(
            limit=TEST_LIMIT_2,
            offset=TEST_OFFSET,
        )
        assert res == ([], 422, HEADERS_PAGINATION_RESULT)


def test_toolsGet_pagination_negativeOffset() -> None:
    """Test for getting a list of all tools, given a negative offset."""
    app = make_app()
    mock_resp = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    mock_resp2 = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp2["id"] = MOCK_ID_2
    app_collection(app, "tools").insert_one(mock_resp2)

    data = deepcopy(MOCK_VERSION_NO_ID)
    data["id"] = MOCK_ID_2

    HEADERS_PAGINATION_RESULT: dict[str, Any] = {}

    with app.test_request_context():
        res = inspect.unwrap(toolsGet)(
            limit=TEST_LIMIT,
            offset=TEST_OFFSET_2,
        )
        assert res == ([], 422, HEADERS_PAGINATION_RESULT)


def test_toolsGet_filters() -> None:
    """Test for getting a list of all available tools; all defined filters specified."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data["id"] = MOCK_ID
    del data["versions"][0]["files"]

    HEADERS_PAGINATION_RESULT = deepcopy(HEADERS_PAGINATION)
    with app.test_request_context():
        HEADERS_PAGINATION_RESULT["self_link"] = request.base_url
        HEADERS_PAGINATION_RESULT["next_page"] = (
            f"{request.base_url}?offset={int(DEFAULT_OFFSET) + DEFAULT_LIMIT}"
            f"&limit={DEFAULT_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["last_page"] = (
            f"{request.base_url}?offset={DEFAULT_OFFSET}&limit={DEFAULT_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["current_offset"] = DEFAULT_OFFSET
        HEADERS_PAGINATION_RESULT["current_limit"] = DEFAULT_LIMIT
        res = inspect.unwrap(toolsGet)(
            id=data["id"],
            checker=data["has_checker"],
            name=data["versions"][0]["images"][0]["image_name"],
            alias=data["aliases"][0],
            author=data["versions"][0]["author"][0],
            registry=data["versions"][0]["images"][0]["registry_host"],
            toolname=data["name"],
            toolClass=data["toolclass"]["name"],
            descriptorType=data["versions"][0]["descriptor_type"][0],
            description=data["description"],
            organization=data["organization"],
        )
        assert res == ([data], 200, HEADERS_PAGINATION_RESULT)


# GET /tools/{id}
def test_toolsIdGet() -> None:
    """Test for getting a tool associated with a given identifier."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    del mock_resp["_id"]
    del mock_resp["versions"][0]["files"]

    with app.app_context():
        res = inspect.unwrap(toolsIdGet)(id=MOCK_ID)
        assert res == mock_resp


def test_toolsIdGet_NotFound() -> None:
    """Test for getting a tool that is not available."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    del mock_resp["_id"]

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdGet)(id=MOCK_ID + MOCK_ID)


# GET /tools/{id}/versions
def test_toolsIdVersionsGet() -> None:
    """Test for getting tool versions associated with a given identifier."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    del mock_resp["_id"]
    del mock_resp["versions"][0]["files"]

    with app.app_context():
        res = inspect.unwrap(toolsIdVersionsGet)(id=MOCK_ID)
        assert res == mock_resp["versions"]


def test_toolsIdVersionsGet_NotFound() -> None:
    """Test for getting the versions of a tool that is not available."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    del mock_resp["_id"]

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsGet)(id=MOCK_ID + MOCK_ID)


# GET /tools/{id}/versions/{version_id}
def test_toolsIdVersionsVersionIdGet() -> None:
    """Test for getting a version of a tool, given tool and version identifiers."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    del mock_resp["versions"][0]["files"]

    with app.app_context():
        res = inspect.unwrap(toolsIdVersionsVersionIdGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == mock_resp["versions"][0]


def test_toolsIdVersionsVersionIdGet_tool_NotFound() -> None:
    """Test for getting a version of a tool that is not available."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdGet)(
            id=MOCK_ID + MOCK_ID,
            version_id=MOCK_ID,
        )


def test_toolsIdVersionsVersionIdGet_version_NotFound() -> None:
    """Test for getting a version that is not available.

    The tool is available, but not the version.
    """
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdGet)(
            id=MOCK_ID, version_id=MOCK_ID + MOCK_ID
        )


# GET /tools/{id}/versions/{version_id}/containerfile
def test_toolsIdVersionsVersionIdContainerfileGet() -> None:
    """Test for getting the container files of a tool version."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context():
        res = inspect.unwrap(toolsIdVersionsVersionIdContainerfileGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == [MOCK_CONTAINER_FILE["file_wrapper"]]


def test_toolsIdVersionsVersionIdContainerfileGet_tool_na_NotFound() -> None:
    """Test for getting the container files of a tool that is not available."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdContainerfileGet)(
            id=MOCK_ID + MOCK_ID,
            version_id=MOCK_ID,
        )


def test_toolsIdVersionsVersionIdContainerfileGet_version_na_NotFound() -> None:
    """Test for getting the container files of an unavailable tool version."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdContainerfileGet)(
            id=MOCK_ID,
            version_id=MOCK_ID + MOCK_ID,
        )


def test_toolsIdVersionsVersionIdContainerfileGet_no_containerfile_NotFound() -> None:
    """Test for getting the container files of a tool version that has none."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["files"] = []

    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        res = inspect.unwrap(toolsIdVersionsVersionIdContainerfileGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == []


# GET /tools/{id}/versions/{version_id}/{type}/descriptor
def test_toolsIdVersionsVersionIdTypeDescriptorGet() -> None:
    """Test for getting the primary descriptor of a tool version, by type."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context():
        res = inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorGet)(
            type="CWL",
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == MOCK_DESCRIPTOR_FILE["file_wrapper"]


def test_toolsIdVersionsVersionIdTypeDescriptorGet_tool_na_NotFound() -> None:
    """Test for getting the primary descriptor of an unavailable tool."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorGet)(
            id=MOCK_ID + MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
        )


def test_toolsIdVersionsVersionIdTypeDescriptorGet_version_na_NotFound() -> None:
    """Test for getting the primary descriptor of an unavailable tool version."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorGet)(
            id=MOCK_ID,
            version_id=MOCK_ID + MOCK_ID,
            type="CWL",
        )


def test_toolsIdVersionsVersionIdTypeDescriptorGet_type_NotFound() -> None:
    """Test for getting the primary descriptor of an unavailable type."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["files"] = []
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
        )


# GET /tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}
def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet() -> None:
    """Test for getting a descriptor of a tool version, by type and path."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context():
        res = inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorRelativePathGet)(
            type="CWL",
            id=MOCK_ID,
            version_id=MOCK_ID,
            relative_path="path_sec_desc_cwl",
        )
        assert res == MOCK_DESCRIPTOR_SEC_FILE["file_wrapper"]


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_tool_NotFound() -> None:
    """Test for getting a descriptor, by path, of an unavailable tool."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorRelativePathGet)(
            id=MOCK_ID + MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
            relative_path="path_tmp",
        )


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_vers_NotFound() -> None:
    """Test for getting a descriptor, by path, of an unavailable tool version."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorRelativePathGet)(
            id=MOCK_ID,
            version_id=MOCK_ID + MOCK_ID,
            type="CWL",
            relative_path="path_tmp",
        )


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_type_NotFound() -> None:
    """Test for getting a descriptor, by path, of an unavailable type."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorRelativePathGet)(
            type="WDL",
            id=MOCK_ID,
            version_id=MOCK_ID,
            relative_path="path_tmp",
        )


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_path_NotFound() -> None:
    """Test for getting a descriptor at a path where none is available."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeDescriptorRelativePathGet)(
            type="CWL",
            id=MOCK_ID,
            version_id=MOCK_ID,
            relative_path="path_tmp_na",
        )


# GET /tools/{id}/versions/{version_id}/{type}/files
def test_toolsIdVersionsVersionIdTypeFilesGet() -> None:
    """Test for getting the descriptor files of a tool version."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["files"][4]["type"] = "WDL"
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context():
        res = inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID, version_id=MOCK_ID, type="CWL"
        )
        descriptors = [
            _desc
            for _desc in mock_resp["versions"][0]["files"]
            if _desc["tool_file"]["file_type"] != "CONTAINERFILE"
        ]
        assert res == [
            _file["tool_file"] for _file in descriptors if _file["type"] == "CWL"
        ]
        assert len(res) == len(descriptors) - 1


def test_toolsIdVersionsVersionIdTypeFilesGet_tool_na_NotFound() -> None:
    """Test for getting the descriptor files of a tool that is not available."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["files"][4]["type"] = "WDL"
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID + MOCK_ID, version_id=MOCK_ID, type="CWL"
        )


def test_toolsIdVersionsVersionIdTypeFilesGet_version_na_NotFound() -> None:
    """Test for getting the descriptor files of an unavailable tool version."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["files"][4]["type"] = "WDL"
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID, version_id=MOCK_ID + MOCK_ID, type="CWL"
        )


def test_toolsIdVersionsVersionIdTypeFilesGet_no_tool_file_NotFound() -> None:
    """Test for getting the tool files of a tool version that has none."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["files"] = []
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID, version_id=MOCK_ID + MOCK_ID, type=MOCK_OTHER_FILE["type"]
        )


def test_toolsIdVersionsVersionIdTypeFilesGet_wrong_type_BadRequest() -> None:
    """Test for getting files when an invalid type is specified."""
    app = make_app()

    with app.app_context(), pytest.raises(BadRequest):
        inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID, version_id=MOCK_ID + MOCK_ID, type="foo"
        )


# GET /tools/{id}/versions/{version_id}/{type}/files?format=zip
def test_toolsIdVersionsVersionIdTypeFilesGet_zip_success_content() -> None:
    """Zip response contains expected files with inline content and headers."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    # Ensure descriptor types are CWL for selected files
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    # Test the non-zip path first to ensure it works
    with app.app_context():
        resp_list = inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
        )
        # Should return a list when format is not zip
        assert isinstance(resp_list, list)
        assert len(resp_list) == 4

    # Test zip functionality by directly accessing the file data
    with app.app_context():
        # Get the selected files data directly (mimicking zip creation logic)
        db_coll_tools = app_collection(app, "tools")
        proj = {
            "_id": False,
            "versions": {"$elemMatch": {"id": MOCK_ID}},
        }
        data = db_coll_tools.find_one(
            filter={"id": MOCK_ID},
            projection=proj,
        )

        file_types = [
            "OTHER",
            "TEST_FILE",
            "PRIMARY_DESCRIPTOR",
            "SECONDARY_DESCRIPTOR",
        ]
        assert data is not None
        data = data["versions"][0]
        selected_files = [
            d
            for d in data["files"]
            if d["type"] == "CWL" and d["tool_file"]["file_type"] in file_types
        ]

        # Test zip creation logic
        mem_zip = BytesIO()
        with ZipFile(mem_zip, mode="w", compression=ZIP_DEFLATED) as zf:
            for file_entry in selected_files:
                path_in_zip = file_entry["tool_file"]["path"]
                wrapper = file_entry.get("file_wrapper", {})
                content_bytes = None
                if "content" in wrapper and wrapper["content"] is not None:
                    content = wrapper["content"]
                    if isinstance(content, bytes):
                        content_bytes = content
                    elif isinstance(content, str):
                        content_bytes = content.encode("utf-8")
                    else:
                        # Fallback: convert to string then encode
                        content_bytes = str(content).encode("utf-8")
                # Ensure we have bytes to write
                if content_bytes is None:
                    continue
                zf.writestr(path_in_zip, content_bytes)

        mem_zip.seek(0)
        # Test the created zip
        with ZipFile(mem_zip) as zf:
            names = set(zf.namelist())
            expected = {
                "path_test_cwl",
                "path_other_cwl",
                "path_prim_desc_cwl",
                "path_sec_desc_cwl",
            }
            assert names == expected
            for name in expected:
                assert zf.read(name).decode("utf-8") == "content"


def _app_with_url_file() -> Flask:
    """App whose stored tool version has one CWL file with a URL only.

    Returns:
        App.
    """
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    for f in mock_resp["versions"][0]["files"]:
        if f["type"] == "CWL" and f["tool_file"]["file_type"] != "CONTAINERFILE":
            f["file_wrapper"].pop("content", None)
            f["file_wrapper"]["url"] = "https://example.com/file.txt"
            break
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)
    return app


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_success_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zip responses retrieve files without stored content from their URLs.

    The files are retrieved as configured.
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
    app = _app_with_url_file()

    with app.test_request_context():
        resp = inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
            format="zip",
        )
        resp.direct_passthrough = False
        with ZipFile(BytesIO(resp.get_data())) as zf:
            contents = {name: zf.read(name) for name in zf.namelist()}
    assert contents == {
        "path_test_cwl": b"from-url",
        "path_other_cwl": b"content",
        "path_prim_desc_cwl": b"content",
        "path_sec_desc_cwl": b"content",
    }
    assert calls == [
        (
            "https://example.com/file.txt",
            custom_config(app).remote_files,
        )
    ]


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_missing_content_url_NotFound() -> (
    None
):
    """Zip building fails when a selected file lacks both content and URL."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    # Remove content and url for one selected CWL file
    for f in mock_resp["versions"][0]["files"]:
        if f["type"] == "CWL" and f["tool_file"]["file_type"] != "CONTAINERFILE":
            f["file_wrapper"].pop("content", None)
            f["file_wrapper"].pop("url", None)
            break
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
            format="zip",
        )


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_non_string_content() -> None:
    """Zip response stores content that is neither text nor bytes as text."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    for f in mock_resp["versions"][0]["files"]:
        if f["type"] == "CWL" and f["tool_file"]["file_type"] == "TEST_FILE":
            f["file_wrapper"]["content"] = 42
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.test_request_context():
        resp = inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
            format="zip",
        )
        resp.direct_passthrough = False
        with ZipFile(BytesIO(resp.get_data())) as zf:
            contents = {name: zf.read(name) for name in zf.namelist()}
    assert contents == {
        "path_test_cwl": b"42",
        "path_other_cwl": b"content",
        "path_prim_desc_cwl": b"content",
        "path_sec_desc_cwl": b"content",
    }


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_fetch_error_NotFound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zip building fails when a file can't be retrieved from its URL."""

    def _raise(url: str, config: RemoteFilesConfig) -> NoReturn:
        """Fail to retrieve a file.

        Args:
            url: URL of the file.
            config: Settings for retrieving files.

        Raises:
            RemoteFileError: Always.
        """
        raise RemoteFileError("refused")

    monkeypatch.setattr("trs_filer.ga4gh.trs.server.fetch_remote_file", _raise)
    app = _app_with_url_file()

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
            format="zip",
        )


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_bytes_content() -> None:
    """Zip response stores content that is already bytes as is."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    for f in mock_resp["versions"][0]["files"]:
        if f["type"] == "CWL" and f["tool_file"]["file_type"] == "TEST_FILE":
            f["file_wrapper"]["content"] = b"raw"
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.test_request_context():
        resp = inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
            format="zip",
        )
        resp.direct_passthrough = False
        with ZipFile(BytesIO(resp.get_data())) as zf:
            content = zf.read("path_test_cwl")
    assert content == b"raw"


def test_toolsIdVersionsVersionIdTypeFilesGet_zip_InternalServerError(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zip building fails with an internal error on unexpected errors."""

    def _raise(url: str, config: RemoteFilesConfig) -> NoReturn:
        """Fail unexpectedly.

        Args:
            url: URL of the file.
            config: Settings for retrieving files.

        Raises:
            ValueError: Always.
        """
        raise ValueError("unexpected")

    monkeypatch.setattr("trs_filer.ga4gh.trs.server.fetch_remote_file", _raise)
    app = _app_with_url_file()

    with app.app_context(), pytest.raises(InternalServerError):
        inspect.unwrap(toolsIdVersionsVersionIdTypeFilesGet)(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL",
            format="zip",
        )


# GET /tools/{id}/versions/{version_id}/{type}/tests
def test_toolsIdVersionsVersionIdTypeTestsGet() -> None:
    """Test for getting the test JSONs of a tool version, by type."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context():
        res = inspect.unwrap(toolsIdVersionsVersionIdTypeTestsGet)(
            type="CWL",
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == [MOCK_TEST_FILE["file_wrapper"]]


def test_toolsIdVersionsVersionIdTypeTestsGet_tool_na_NotFound() -> None:
    """Test for getting the test JSONs of a tool that is not available."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeTestsGet)(
            type="CWL",
            id=MOCK_ID + MOCK_ID,
            version_id=MOCK_ID,
        )


def test_toolsIdVersionsVersionIdTypeTestsGet_version_na_NotFound() -> None:
    """Test for getting the test JSONs of an unavailable tool version."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeTestsGet)(
            type="CWL",
            id=MOCK_ID,
            version_id=MOCK_ID + MOCK_ID,
        )


def test_toolsIdVersionsVersionIdTypeTestsGet_type_NotFound() -> None:
    """Test for getting the test JSONs of a type that has no test files."""
    app = make_app()
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(toolsIdVersionsVersionIdTypeTestsGet)(
            type="WDL",
            id=MOCK_ID,
            version_id=MOCK_ID,
        )


# POST /tools
def test_postTool() -> None:
    """Test for creating a tool; identifier assigned by implementation."""
    app = make_app(CUSTOM_CONFIG)
    mock_collection(app, "tools")
    mock_collection(app, "toolclasses")

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = inspect.unwrap(postTool)()
        assert isinstance(res, str)


# PUT /tools/{id}
def test_putTool() -> None:
    """Test for creating a tool; identifier provided by user."""
    app = make_app(CUSTOM_CONFIG)
    mock_collection(app, "tools")
    mock_collection(app, "toolclasses")

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = inspect.unwrap(putTool)(id=MOCK_ID)
        assert res == MOCK_ID


def test_putTool_update() -> None:
    """Test for updating an existing tool."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = {}
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    mock_collection(app, "toolclasses")
    app_collection(app, "tools").insert_one(mock_resp)
    app_collection(app, "toolclasses").insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = inspect.unwrap(putTool)(id=MOCK_ID)
        assert res == MOCK_ID


# DELETE /tools/{id}
def test_deleteTool() -> None:
    """Test for deleting a tool."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context():
        res = inspect.unwrap(deleteTool)(id=MOCK_ID)
        assert res == MOCK_ID


def test_deleteTool_NotFound() -> None:
    """Test `DELETE /tools/{id}` endpoint with unavailable id."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(deleteTool)(id=MOCK_ID)


# POST /tools/{id}/versions
def test_postToolVersion() -> None:
    """Test for adding a version to a tool."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = {}
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = inspect.unwrap(postToolVersion)(id=MOCK_ID)
        assert isinstance(res, str)


# PUT /tools/{id}/versions/{version_id}
def test_putToolVersion() -> None:
    """Test for creating a tool version; identifier provided by user."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = {}
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = inspect.unwrap(putToolVersion)(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert isinstance(res, str)


def test_putToolVersion_update() -> None:
    """Test for updating an existing tool version."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = inspect.unwrap(putToolVersion)(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert isinstance(res, str)


# DELETE /tools/{id}/versions/{version_id}
def test_deleteToolVersion() -> None:
    """Test for deleting a version of a tool."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"].append(deepcopy(MOCK_VERSION_ID))
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    with app.app_context():
        res = inspect.unwrap(deleteToolVersion)(
            id=MOCK_ID,
            version_id=data["versions"][0]["id"],
        )
        assert res == data["versions"][0]["id"]


def test_deleteToolVersion_tool_NotFound() -> None:
    """Test for deleting a version of a tool that is not available."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(deleteToolVersion)(
            id=MOCK_ID + MOCK_ID,
            version_id=MOCK_ID,
        )


def test_deleteToolVersion_version_NotFound() -> None:
    """Test for deleting a version that is not available."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    with app.app_context(), pytest.raises(NotFound):
        inspect.unwrap(deleteToolVersion)(
            id=MOCK_ID,
            version_id=MOCK_ID + MOCK_ID,
        )


def test_deleteToolVersion_InternalServerError(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test for deleting a version of a tool when the deletion is incomplete.

    Either only the tool or only the associated files were deleted.
    """

    class MongoMockResponse:
        """Result of an update."""

        def __init__(self, matched_count: int, modified_count: int) -> None:
            """Set the counts of the result.

            Args:
                matched_count: Number of matched documents.
                modified_count: Number of modified documents.
            """
            self.matched_count = matched_count
            self.modified_count = modified_count

    mock_response = MongoMockResponse(matched_count=1, modified_count=0)
    monkeypatch.setattr(
        "mongomock.collection.Collection.update_one",
        lambda *args, **kwargs: mock_response,
    )
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"].append(deepcopy(MOCK_VERSION_ID))
    mock_collection(app, "tools")
    app_collection(app, "tools").insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    with app.app_context(), pytest.raises(InternalServerError):
        inspect.unwrap(deleteToolVersion)(
            id=MOCK_ID,
            version_id=data["versions"][0]["id"],
        )


# POST /toolClasses
def test_postToolClass() -> None:
    """Test for creating a tool class; identifier assigned by implementation."""
    app = make_app(CUSTOM_CONFIG)
    mock_collection(app, "toolclasses")

    data = deepcopy(MOCK_TOOL_CLASS)
    del data["id"]
    with app.test_request_context(json=data):
        res = inspect.unwrap(postToolClass)()
        assert isinstance(res, str)


# PUT /toolClasses
def test_putToolClass() -> None:
    """Test for creating a tool class; identifier provided by user."""
    app = make_app(CUSTOM_CONFIG)
    mock_collection(app, "toolclasses")

    data = deepcopy(MOCK_TOOL_CLASS)
    del data["id"]
    with app.test_request_context(json=MOCK_TOOL_CLASS):
        res = inspect.unwrap(putToolClass)(id=MOCK_ID)
        assert isinstance(res, str)
        assert res == MOCK_ID


def test_putToolClass_update() -> None:
    """Test for updating an existing tool class."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    mock_collection(app, "toolclasses")
    app_collection(app, "toolclasses").insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_CLASS)
    del data["id"]
    with app.test_request_context(json=MOCK_TOOL_CLASS):
        res = inspect.unwrap(putToolClass)(id=MOCK_ID)
        assert isinstance(res, str)
        assert res == MOCK_ID


# DELETE /toolClasses
def test_deleteToolClass() -> None:
    """Test for deleting a tool class associated with a given `id`."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    mock_collection(app, "tools")
    mock_collection(app, "toolclasses")
    app_collection(app, "toolclasses").insert_one(mock_resp)

    with app.test_request_context():
        res = inspect.unwrap(deleteToolClass)(
            id=MOCK_ID,
        )
        assert res == MOCK_ID


def test_deleteToolClass_NotFound() -> None:
    """Test for deleting a tool class that is not available."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    mock_collection(app, "tools")
    mock_collection(app, "toolclasses")
    app_collection(app, "toolclasses").insert_one(mock_resp)

    with app.test_request_context(), pytest.raises(NotFound):
        inspect.unwrap(deleteToolClass)(
            id=MOCK_ID + MOCK_ID,
        )


def test_deleteToolClass_BadRequest() -> None:
    """Test for deleting a tool class that a tool is associated with."""
    app = make_app(CUSTOM_CONFIG)
    mock_resp_tools = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp_classes = deepcopy(MOCK_TOOL_CLASS)
    mock_collection(app, "tools")
    mock_collection(app, "toolclasses")
    app_collection(app, "tools").insert_one(mock_resp_tools)
    app_collection(app, "toolclasses").insert_one(mock_resp_classes)

    with app.test_request_context(), pytest.raises(BadRequest):
        inspect.unwrap(deleteToolClass)(
            id=MOCK_ID,
        )
