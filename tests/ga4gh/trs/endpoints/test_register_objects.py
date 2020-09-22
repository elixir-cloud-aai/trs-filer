"""Tests for setting tools and tool versions."""

from copy import deepcopy
import string  # noqa: F401
from unittest.mock import MagicMock

from flask import Flask
from foca.models.config import (Config, MongoConfig)
import mongomock
from pymongo.errors import DuplicateKeyError
import pytest

from tests.mock_data import (
    ENDPOINT_CONFIG,
    ENDPOINT_CONFIG_CHARSET_LITERAL,
    ENDPOINT_CONFIG_ONE_ID,
    ENDPOINT_CONFIG_TOOL_CLASS_VALIDATION,
    MOCK_TEST_FILE_INVALID,
    MOCK_OTHER_FILE_INVALID,
    MOCK_CONTAINER_FILE_INVALID,
    MOCK_DESCRIPTOR_FILE_INVALID,
    MOCK_FILES_TOOL_FILE_MISSING,
    MOCK_FILE_TYPE_MISSING,
    MOCK_FILES_CHECKSUM_MISSING,
    MOCK_FILES_CONTENT_URL_MISSING,
    MOCK_ID,
    MOCK_ID_ONE_CHAR,
    MOCK_TOOL,
    MOCK_TOOL_VERSION_ID,
    MOCK_TOOL_DUPLICATE_VERSION_IDS,
    MOCK_VERSION_ID,
    MOCK_VERSION_NO_ID,
    MONGO_CONFIG,
)
from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)
from trs_filer.ga4gh.trs.endpoints.register_objects import (
    RegisterTool,
    RegisterToolVersion,
)


class TestRegisterTool:
    """Tests for `RegisterTool` class."""

    def test_init(self):
        """Test for constructing class."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )

        data = deepcopy(MOCK_TOOL)
        with app.app_context():
            tool = RegisterTool(data=data)
            assert tool.data['description'] == MOCK_TOOL['description']
            assert tool.data['id'] is None

    def test_process_metadata(self):
        """Test for processing metadata."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_TOOL)
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.process_metadata()
            assert isinstance(tool.id_charset, str)

    def test_register_metadata(self):
        """Test for creating a tool with a randomly assigned identifier."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.register_metadata()
            assert isinstance(tool.data['id'], str)

    def test_register_metadata_with_id(self):
        """Test for creating a tool with a user-supplied identifier."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data, id=MOCK_ID)
            tool.register_metadata()
            assert tool.data['id'] == MOCK_ID

    def test_register_metadata_with_id_replace(self):
        """Test for updating an existing tool."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data, id=MOCK_ID)
            tool.register_metadata()
            assert tool.data['id'] == MOCK_ID

    def test_register_metadata_duplicate_version_ids_BadRequest(self):
        """Test for creating a tool; duplicate version identifiers supplied."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'] \
            .collections['tools'].client.insert_one = MagicMock()

        data = deepcopy(MOCK_TOOL_DUPLICATE_VERSION_IDS)
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterTool(data=data)
                tool.register_metadata()

    def test_create_tool_invalid_file_data_no_content_or_url_BadRequest(self):
        """Test for creating a tool; both file `content` and `url` fields
        missing.
        """
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()

        temp_data = deepcopy(MOCK_TOOL_VERSION_ID)
        temp_data['versions'][0]['files'] = MOCK_FILES_CONTENT_URL_MISSING
        data = temp_data
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterTool(data=data)
                tool.register_metadata()

    def test_create_tool_invalid_file_data_no_checksum_BadRequest(self):
        """Test for creating a tool; file `checksum` field missing although
        production tool.
        """
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        data['versions'][0]['files'] = MOCK_FILES_CHECKSUM_MISSING
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterTool(data=data)
                tool.register_metadata()

    def test_register_metadata_with_tool_class_validation(self):
        """Test for creating a tool with tool class validation passing."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_TOOL_CLASS_VALIDATION,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client.replace_one = MagicMock()

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.register_metadata()
            assert isinstance(tool.data['id'], str)

    def test_register_metadata_with_tool_class_validation_BadRequest(self):
        """Test for creating a tool with tool class validation failing."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_TOOL_CLASS_VALIDATION,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client.replace_one = MagicMock()

        data = deepcopy(MOCK_TOOL_VERSION_ID)
        data['toolclass']['id'] = MOCK_ID + MOCK_ID
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterTool(data=data)
                tool.register_metadata()

    def test_register_metadata_tool_duplicate_key(self):
        """Test for creating a tool; duplicate key error occurs."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )
        mock_resp = MagicMock(side_effect=[DuplicateKeyError(''), None])
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one = mock_resp

        temp_data = deepcopy(MOCK_TOOL)
        data = temp_data
        with app.app_context():
            tool = RegisterTool(data=data)
            tool.register_metadata()
            assert isinstance(tool.data['id'], str)

    def test_register_metadata_duplicate_keys_repeated(self):
        """Test for creating a tool; running out of unique identifiers."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_ONE_ID,
        )
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID_ONE_CHAR
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL)
        with app.app_context():
            with pytest.raises(InternalServerError):
                tool = RegisterTool(data=data)
                tool.register_metadata()
                tool = RegisterTool(data=data)
                tool.register_metadata()
                print(tool.data['id'])


class TestRegisterToolVersion:
    """Tests for `RegisterToolVersion` class."""

    def test_init(self):
        """Test for constructing class."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            assert tool.data['name'] == MOCK_VERSION_NO_ID['name']
            assert tool.id == MOCK_ID

    def test_process_metadata(self):
        """Test for processing metadata."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.process_metadata()
            assert isinstance(tool.id_charset, str)

    def test_process_metadata_empty_file_object(self):
        """Test for processing metadata with one empty file object."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        data['files'][0] = {}
        with app.app_context():
            tool = RegisterToolVersion(data=data, id=MOCK_ID)
            tool.process_metadata()
            assert isinstance(tool.id_charset, str)

    def test_process_file_type_register_invalid_descriptor_type(self):
        """Test for processing metadata with one invalid `descriptors` type."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterToolVersion(data=data, id=MOCK_ID)
                tool.process_file_type_register(
                    file_data=MOCK_DESCRIPTOR_FILE_INVALID
                )

    def test_process_file_type_register_invalid_container_type(self):
        """Test for processing metadata with one invalid `containers` type."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterToolVersion(data=data, id=MOCK_ID)
                tool.process_file_type_register(
                    file_data=MOCK_CONTAINER_FILE_INVALID
                )

    def test_process_file_type_register_invalid_test_type(self):
        """Test for processing metadata with one invalid `tests` type."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterToolVersion(data=data, id=MOCK_ID)
                tool.process_file_type_register(
                    file_data=MOCK_TEST_FILE_INVALID
                )

    def test_process_file_type_register_invalid_other_type(self):
        """Test for processing metadata with one invalid `others` type."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterToolVersion(data=data, id=MOCK_ID)
                tool.process_file_type_register(
                    file_data=MOCK_OTHER_FILE_INVALID
                )

    def test_process_files_tool_file_not_present(self):
        """Test for processing metadata with invalid file object with
        `tool_file` absent.
        """
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )

        data = deepcopy(MOCK_VERSION_NO_ID)
        data['files'] = MOCK_FILES_TOOL_FILE_MISSING
        with app.app_context():
            with pytest.raises(BadRequest):
                tool = RegisterToolVersion(data=data, id=MOCK_ID)
                tool.process_files()

    def test_register_metadata(self):
        """Test for creating a version with a randomly assigned identifier."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one(mock_resp)
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()
            assert isinstance(version.data, dict)

    def test_register_metadata_with_id(self):
        """Test for creating a version with a user-supplied identifier."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            version = RegisterToolVersion(
                data=data,
                id=MOCK_ID,
                version_id=MOCK_ID,
            )
            version.register_metadata()
            assert isinstance(version.data, dict)

    def test_register_metadata_with_id_replace(self):
        """Test for updating an existing version."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one(mock_resp)
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_ID)
        with app.app_context():
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()
            assert isinstance(version.data, dict)

    def test_register_metadata_duplicate_keys_repeated(self):
        """Test for creating a version; running out of unique identifiers."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_ONE_ID,
        )
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        mock_resp["versions"][0]["id"] = MOCK_ID_ONE_CHAR
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one(mock_resp)
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            with pytest.raises(InternalServerError):
                version = RegisterToolVersion(data=data, id=MOCK_ID)
                version.register_metadata()
                version = RegisterToolVersion(data=data, id=MOCK_ID)
                version.register_metadata()

    def test_register_metadata_tool_na(self):
        """Test for creating/updating a version; tool not available."""
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_ONE_ID,
        )
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID_ONE_CHAR
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = mongomock.MongoClient().db.collection
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_NO_ID)
        with app.app_context():
            with pytest.raises(NotFound):
                version = RegisterToolVersion(data=data, id=MOCK_ID)
                version.register_metadata()

    def test_register_metadata_file_type_not_given(self):
        """Test for creating a version when `file_type` not provided in
        `tool_file`.
        """
        app = Flask(__name__)
        app.config['FOCA'] = Config(
            db=MongoConfig(**MONGO_CONFIG),
            endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
        )
        mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
        mock_resp["id"] = MOCK_ID
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client = MagicMock()
        app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
            .client.insert_one(mock_resp)
        app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_VERSION_NO_ID)
        data['files'] = MOCK_FILE_TYPE_MISSING
        with app.app_context():
            version = RegisterToolVersion(data=data, id=MOCK_ID)
            version.register_metadata()
            assert isinstance(version.data, dict)
