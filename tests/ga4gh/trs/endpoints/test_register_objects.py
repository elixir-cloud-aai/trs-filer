"""Tests for setting tools and tool versions."""

from copy import deepcopy
import string  # noqa: F401
from typing import NoReturn
from unittest.mock import MagicMock

from pymongo.errors import DuplicateKeyError
import pytest

from tests.apps import (
    app_collection,
    custom_config,
    make_app,
    mock_collection,
    mock_unset_collections,
    set_client,
)
from tests.mock_data import (
    CUSTOM_CONFIG,
    CUSTOM_CONFIG_CHARSET_LITERAL,
    CUSTOM_CONFIG_ONE_ID,
    CUSTOM_CONFIG_TOOL_CLASS_VALIDATION,
    MOCK_CONTAINER_FILE,
    MOCK_DESCRIPTOR_FILE,
    MOCK_DESCRIPTOR_SEC_FILE,
    MOCK_FILES_CHECKSUM_MISSING,
    MOCK_FILES_CONTENT_URL_MISSING,
    MOCK_ID,
    MOCK_ID_ONE_CHAR,
    MOCK_TOOL,
    MOCK_TOOL_DUPLICATE_VERSION_IDS,
    MOCK_TOOL_VERSION_ID,
    MOCK_VERSION_ID,
    MOCK_VERSION_NO_ID,
)
from trs_filer.custom_config import RemoteFilesConfig
from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
    RemoteFileError,
)
from trs_filer.ga4gh.trs.endpoints.register_objects import (
    RegisterTool,
    RegisterToolVersion,
    next_meta_version,
)
from trs_filer.remote_files import RemoteFile


def _raise(exception: Exception) -> NoReturn:
    """General purpose exception raiser.

    Args:
        exception: Exception to raise.

    Raises:
        Exception: Always, the given one.
    """
    raise exception


@pytest.mark.parametrize(
    ("previous", "expected"),
    [("1", "3"), (4, "6"), (None, "1"), ("abc", "1")],
)
def test_next_meta_version(previous: object, expected: str) -> None:
    """Meta versions are incremented; invalid ones restart at the initial one.

    Args:
        previous: Stored meta version.
        expected: Next meta version.
    """
    assert next_meta_version(previous, init=1, increment=2) == expected


class TestRegisterTool:
    """Tests for `RegisterTool` class."""

    def test_init(self) -> None:
        """Test for constructing class."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)

        data = deepcopy(MOCK_TOOL)
        with app.app_context():
            tool = RegisterTool(data=data)
            assert tool.data["description"] == MOCK_TOOL["description"]
            assert tool.data["id"] is None

    def test_process_metadata(self) -> None:
        """Test for processing metadata."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        data = deepcopy(MOCK_TOOL)
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.process_metadata()
            assert isinstance(tool.id_charset, str)

    def test_register_metadata(self) -> None:
        """Test for creating a tool with a randomly assigned identifier."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock())
        set_client(app, "toolclasses", MagicMock())

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.register_metadata()
            assert isinstance(tool.data["id"], str)

    def test_register_metadata_with_id(self) -> None:
        """Test for creating a tool with a user-supplied identifier."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock())
        set_client(app, "toolclasses", MagicMock())

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data, id=MOCK_ID)
            tool.register_metadata()
            assert tool.data["id"] == MOCK_ID

    def test_register_metadata_with_id_replace(self) -> None:
        """Test for updating an existing tool."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        set_client(app, "tools", MagicMock())
        set_client(app, "toolclasses", MagicMock())
        app_collection(app, "tools").insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data, id=MOCK_ID)
            tool.register_metadata()
            assert tool.data["id"] == MOCK_ID

    def test_register_metadata_duplicate_version_ids_BadRequest(self) -> None:
        """Test for creating a tool; duplicate version identifiers supplied."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock(insert_one=MagicMock()))

        data = deepcopy(MOCK_TOOL_DUPLICATE_VERSION_IDS)
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterTool(data=data)
            tool.register_metadata()

    def test_create_tool_invalid_file_data_no_content_or_url_BadRequest(self) -> None:
        """Test for creating a tool; both file `content` and `url` fields missing."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock())
        set_client(app, "toolclasses", MagicMock())

        temp_data = deepcopy(MOCK_TOOL_VERSION_ID)
        temp_data["versions"][0]["files"] = MOCK_FILES_CONTENT_URL_MISSING
        data = temp_data
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterTool(data=data)
            tool.register_metadata()

    def test_create_tool_invalid_file_data_no_checksum_BadRequest(self) -> None:
        """Test for creating a production tool whose file lacks a `checksum`."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock())
        set_client(app, "toolclasses", MagicMock())

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        data["versions"][0]["files"] = MOCK_FILES_CHECKSUM_MISSING
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterTool(data=data)
            tool.register_metadata()

    def test_register_metadata_with_tool_class_validation(self) -> None:
        """Test for creating a tool with tool class validation passing."""
        app = make_app(CUSTOM_CONFIG_TOOL_CLASS_VALIDATION)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock())
        set_client(app, "toolclasses", MagicMock())

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.register_metadata()
            assert isinstance(tool.data["id"], str)

    def test_register_metadata_with_tool_class_validation_BadRequest(self) -> None:
        """Test for creating a tool with tool class validation failing."""
        app = make_app(CUSTOM_CONFIG_TOOL_CLASS_VALIDATION)
        mock_unset_collections(app)
        mock_collection(app, "tools")
        mock_collection(app, "toolclasses")

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        data["toolclass"]["id"] = MOCK_ID + MOCK_ID
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterTool(data=data)
            tool.register_metadata()

    def test_register_metadata_without_tool_class_identifier(self) -> None:
        """Test for creating a tool with tool class without an identifier."""
        app = make_app(CUSTOM_CONFIG_TOOL_CLASS_VALIDATION)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock())
        set_client(app, "toolclasses", MagicMock())

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        data["toolclass"].pop("id")
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.register_metadata()
            assert isinstance(tool.data["id"], str)

    def test_register_metadata_tool_duplicate_key(self) -> None:
        """Test for creating a tool; duplicate key error occurs."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        mock_resp = MagicMock(side_effect=[DuplicateKeyError(""), None])
        set_client(app, "tools", MagicMock(insert_one=mock_resp))
        set_client(app, "toolclasses", MagicMock())

        temp_data = deepcopy(MOCK_TOOL)
        data = temp_data
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.register_metadata()
            assert isinstance(tool.data["id"], str)

    def test_register_metadata_duplicate_keys_repeated(self) -> None:
        """Test for creating a tool; running out of unique identifiers."""
        app = make_app(CUSTOM_CONFIG_ONE_ID)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID_ONE_CHAR
        mock_collection(app, "tools")
        mock_collection(app, "toolclasses")
        app_collection(app, "tools").insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL)
        with app.app_context(), pytest.raises(InternalServerError):
            RegisterTool(data=data).register_metadata()


class TestRegisterToolVersion:
    """Tests for `RegisterToolVersion` class."""

    def test_init(self) -> None:
        """Test for constructing class."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            assert tool.data["name"] == MOCK_VERSION_NO_ID["name"]
            assert tool.id == MOCK_ID

    def test_process_metadata(self) -> None:
        """Test for processing metadata."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.process_metadata()
            assert isinstance(tool.id_charset, str)

    def test_process_files_invalid_descriptor_type(self) -> None:
        """Test for processing files with an invalid descriptor type."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        data = deepcopy(MOCK_VERSION_NO_ID)
        mock_file = deepcopy(MOCK_DESCRIPTOR_FILE)
        mock_file["type"] = "invalid"
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.data["files"] = [mock_file]
            tool.process_files()

    def test_process_files_multiple_primary_descriptors(self) -> None:
        """Test for processing files with more than one primary descriptor."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        data = deepcopy(MOCK_VERSION_NO_ID)
        mock_descriptor = deepcopy(MOCK_DESCRIPTOR_FILE)
        mock_descriptor["tool_file"]["path"] = "random_path"
        data["files"].append(mock_descriptor)
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.data["files"] = data["files"]
            tool.process_files()

    def test_process_files_secondary_but_not_primary_descriptor(self) -> None:
        """Test for processing files with a secondary but no primary descriptor."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        data = deepcopy(MOCK_VERSION_NO_ID)
        data["files"] = [MOCK_DESCRIPTOR_SEC_FILE]
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.data["files"] = data["files"]
            tool.process_files()

    def test_process_files_invalid_container_type(self) -> None:
        """Test for processing files with an invalid container type."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        data = deepcopy(MOCK_VERSION_NO_ID)
        mock_file = deepcopy(MOCK_CONTAINER_FILE)
        mock_file["type"] = "invalid"
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.data["files"] = [mock_file]
            tool.process_files()

    def test_process_files_non_unique_paths(self) -> None:
        """Test for processing files of a descriptor type that share a path."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        data = deepcopy(MOCK_VERSION_NO_ID)
        tmp_file_obj1 = deepcopy(MOCK_DESCRIPTOR_FILE)
        tmp_file_obj2 = deepcopy(MOCK_DESCRIPTOR_SEC_FILE)
        tmp_file_obj1["tool_file"]["path"] = "tmp_url"
        tmp_file_obj2["tool_file"]["path"] = "tmp_url"
        data["files"] = [tmp_file_obj1, tmp_file_obj2]
        with app.app_context(), pytest.raises(BadRequest):
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.data["files"] = data["files"]
            tool.process_files()

    def test_process_files_no_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test for processing files with no content provided."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

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
            return RemoteFile(content=MOCK_ID.encode())

        monkeypatch.setattr(
            "trs_filer.ga4gh.trs.endpoints.register_objects.fetch_remote_file",
            _fetch,
        )
        data = deepcopy(MOCK_VERSION_NO_ID)
        mock_file = deepcopy(MOCK_CONTAINER_FILE)
        del mock_file["file_wrapper"]["content"]
        mock_file["file_wrapper"]["url"] = "https://example.com/Dockerfile"
        with app.app_context():
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.data["files"] = [mock_file]
            tool.process_files()
            assert tool.data["files"][0]["file_wrapper"]["content"] == (MOCK_ID)
            assert calls == [
                (
                    "https://example.com/Dockerfile",
                    custom_config(app).remote_files,
                )
            ]

    def test_process_files_no_content_invalid_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test for processing files with no content provided and an invalid URL."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)

        monkeypatch.setattr(
            "trs_filer.ga4gh.trs.endpoints.register_objects.fetch_remote_file",
            lambda *args, **kwargs: _raise(RemoteFileError("refused")),
        )
        data = deepcopy(MOCK_VERSION_NO_ID)
        mock_file = deepcopy(MOCK_CONTAINER_FILE)
        del mock_file["file_wrapper"]["content"]
        mock_file["file_wrapper"]["url"] = "https://example.com/Dockerfile"
        with app.app_context(), pytest.raises(RemoteFileError):
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.data["files"] = [mock_file]
            tool.process_files()

    def test_register_metadata(self) -> None:
        """Test for creating a version with a randomly assigned identifier."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        set_client(app, "tools", MagicMock())
        app_collection(app, "tools").insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()
            assert isinstance(version.data, dict)

    def test_register_metadata_with_id(self) -> None:
        """Test for creating a version with a user-supplied identifier."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)
        set_client(app, "tools", MagicMock())

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            version = RegisterToolVersion(
                data=data,
                id=MOCK_ID,
                version_id=MOCK_ID,
            )
            version.register_metadata()
            assert isinstance(version.data, dict)

    def test_register_metadata_with_id_replace(self) -> None:
        """Test for updating an existing version."""
        app = make_app(CUSTOM_CONFIG_CHARSET_LITERAL)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        set_client(app, "tools", MagicMock())
        app_collection(app, "tools").insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_ID)
        with app.app_context():
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()
            assert isinstance(version.data, dict)

    def test_register_metadata_duplicate_keys(self) -> None:
        """Test for creating a version; running out of unique identifiers."""
        app = make_app(CUSTOM_CONFIG_ONE_ID)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        mock_resp["versions"][0]["id"] = MOCK_ID_ONE_CHAR
        mock_collection(app, "tools")
        mock_collection(app, "toolclasses")
        app_collection(app, "tools").insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context(), pytest.raises(InternalServerError):
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()

    def test_register_metadata_tool_na(self) -> None:
        """Test for creating/updating a version; tool not available."""
        app = make_app(CUSTOM_CONFIG_ONE_ID)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID_ONE_CHAR
        mock_collection(app, "tools")
        app_collection(app, "tools").insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context(), pytest.raises(NotFound):
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()
