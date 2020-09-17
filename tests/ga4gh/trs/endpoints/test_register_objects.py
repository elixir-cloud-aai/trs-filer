"""Unit tests for `RegisterTool()`, `RegisterToolVersion` controller."""

from copy import deepcopy
import string  # noqa: F401
from unittest.mock import MagicMock

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.errors import DuplicateKeyError
import pytest

from tests.mock_data import (
    ENDPOINT_CONFIG,
    ENDPOINT_CONFIG_CHARSET_LITERAL,
    ENDPOINT_CONFIG_ONE_ID,
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
    generate_id,
)


def test_generate_id_literal():
    """Test for generate_id function."""
    assert generate_id(charset=MOCK_ID_ONE_CHAR, length=6) == "AAAAAA"


def test_generate_id_no_expression():
    """Test for generate_id function; expression supplied."""
    assert isinstance(
        int(generate_id(charset=string.digits, length=6)),
        int,
    )


def test_process_metadata_literal_charset():
    """Test for `RegisterTool.process_metadata()` method."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )

    data = deepcopy(MOCK_TOOL)
    with app.app_context():
        tool = RegisterTool(data)
        tool.process_metadata()
        assert isinstance(
            tool.id_charset,
            str,
        )


def test_create_tool_duplicate_key():
    """Test for valid duplicate key error."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_tools = MagicMock(side_effect=[DuplicateKeyError(''), None])
    mock_files = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client = MagicMock()
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one = mock_tools
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client = MagicMock()
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_many = mock_files

    temp_data = deepcopy(MOCK_TOOL)
    data = temp_data
    with app.app_context():
        tool = RegisterTool(data)
        tool.register_metadata()
        assert isinstance(
            tool.data['id'],
            str,
        )


def test_create_tool_duplicate_version_id_provided():
    """Test for user supplying duplicate ids for multiple versions."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client = MagicMock()
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one = MagicMock()

    data = deepcopy(MOCK_TOOL_DUPLICATE_VERSION_IDS)
    with app.app_context():
        with pytest.raises(BadRequest):
            tool = RegisterTool(data)
            tool.register_metadata()


def test_update_tool():
    """Test for updating tool."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL)
    with app.app_context():
        tool = RegisterTool(data, id=MOCK_ID)
        tool.register_metadata()
        assert isinstance(tool.data, dict)


def test_create_tool_valid_file_data():
    """Test for creating valid tool with file data."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    data = deepcopy(MOCK_TOOL)
    with app.app_context():
        tool = RegisterTool(data)
        tool.register_metadata()
        assert isinstance(
            tool.data['id'],
            str,
        )


def test_create_tool_invalid_file_data():
    """Test for creating tool with url/content missing in file data."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    temp_data = deepcopy(MOCK_TOOL_VERSION_ID)
    temp_data['versions'][0]['files'] = MOCK_FILES_CONTENT_URL_MISSING
    data = temp_data
    with app.app_context():
        with pytest.raises(BadRequest):
            tool = RegisterTool(data)
            tool.register_metadata()


def test_create_tool_invalid_file_data_nochechecksum():
    """Test for valid tool formation when checksum absent in file data."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    temp_data = deepcopy(MOCK_TOOL_VERSION_ID)
    temp_data['versions'][0]['files'] = MOCK_FILES_CHECKSUM_MISSING
    data = temp_data
    with app.app_context():
        with pytest.raises(BadRequest):
            tool = RegisterTool(data)
            tool.register_metadata()


def test_create_tool_replace_files():
    """Test for tool file data replacement."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = MagicMock()
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.replace_one = MagicMock()

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    with app.app_context():
        tool = RegisterTool(data, MOCK_ID)
        tool.register_metadata()
        assert isinstance(
            tool.data['id'],
            str,
        )


def test_update_tool_inf_loop():
    """Test for updating tool; running out of unique identifiers."""
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
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL)
    with app.app_context():
        with pytest.raises(InternalServerError):
            tool = RegisterTool(data)
            tool.register_metadata()
            tool = RegisterTool(data)
            tool.register_metadata()
            print(tool.data['id'])


def test_add_version():
    """Test for adding version."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_VERSION_NO_ID)
    with app.app_context():
        version = RegisterToolVersion(data, id=MOCK_ID)
        version.register_metadata()
        assert isinstance(version.data, dict)


def test_update_version():
    """Test for updating version."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_VERSION_ID)
    with app.app_context():
        version = RegisterToolVersion(data, id=MOCK_ID)
        version.register_metadata()
        assert isinstance(version.data, dict)


def test_update_version_inf_loop():
    """Test for updating version; running out of unique identifiers."""
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
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_VERSION_NO_ID)
    with app.app_context():
        with pytest.raises(InternalServerError):
            version = RegisterToolVersion(data, id=MOCK_ID)
            version.register_metadata()
            version = RegisterToolVersion(data, id=MOCK_ID)
            version.register_metadata()


def test_update_version_tool_na():
    """Test for updating version; tool not available."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_ONE_ID,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = MOCK_ID_ONE_CHAR
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_VERSION_NO_ID)
    with app.app_context():
        with pytest.raises(NotFound):
            version = RegisterToolVersion(data, id=MOCK_ID)
            version.register_metadata()
