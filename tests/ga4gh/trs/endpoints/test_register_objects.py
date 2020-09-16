"""Unit tests for `RegisterTool()`, `RegisterToolVersion` controller."""

from copy import deepcopy
import string  # noqa: F401
from unittest.mock import MagicMock

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
from pymongo.errors import DuplicateKeyError
import pytest

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

MOCK_ID = "mock_id"
MOCK_ID_2 = "A"
INDEX_CONFIG = {
    'keys': [('id', 1)]
}
COLLECTION_CONFIG = {
    'indexes': [INDEX_CONFIG],
}
FILE_INDEX_CONFIG = {
    'keys': [('id', 1)]
}
FILES_CONFIG = {
    'indexes': [FILE_INDEX_CONFIG],
}
DB_CONFIG = {
    'collections': {
        'tools': COLLECTION_CONFIG,
        'files': FILES_CONFIG,
    },
}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'trsStore': DB_CONFIG,
    },
}
ENDPOINT_CONFIG_CHARSET_EXPRESSION = {
    "tool": {
        "id": {
            "charset": 'string.digits',
            "length": 6,
        },
        "meta_version": {
            "init": 1,
            "increment": 1,
        },
    },
    "version": {
        "id": {
            "charset": 'string.digits',
            "length": 6,
        },
        "meta_version": {
            "init": 1,
            "increment": 1,
        },
    },
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 80,
    "api_path": "ga4gh/trs/v2",
}
ENDPOINT_CONFIG_CHARSET_LITERAL = {
    "tool": {
        "id": {
            "charset": '0a123456789',
            "length": 6,
        },
        "meta_version": {
            "init": 1,
            "increment": 1,
        },
    },
    "version": {
        "id": {
            "charset": '0a123456789',
            "length": 6,
        },
        "meta_version": {
            "init": 1,
            "increment": 1,
        },
    },
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 80,
    "api_path": "ga4gh/trs/v2",
}
ENDPOINT_CONFIG_ONE_ID = {
    "tool": {
        "id": {
            "charset": MOCK_ID_2,
            "length": 1,
        },
        "meta_version": {
            "init": 1,
            "increment": 1,
        },
    },
    "version": {
        "id": {
            "charset": MOCK_ID_2,
            "length": 1,
        },
        "meta_version": {
            "init": 1,
            "increment": 1,
        },
    },
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 80,
    "api_path": "ga4gh/trs/v2",
}
MOCK_REQUEST_DATA_VALID = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
    "meta_version": "0.0.0",
    "name": "string",
    "organization": "string",
    "versions": [
        {
            "author": [
                "string"
            ],
            "descriptor_type": [
                "CWL"
            ],
            "included_apps": [
                "https://bio.tools/tool/mytum.de/SNAP2/1",
                "https://bio.tools/bioexcel_seqqc"
            ],
            "is_production": True,
            "meta_version": "string",
            "name": "string",
            "signed": True,
            "verified_source": [
                "string"
            ]
        }
    ]
}
MOCK_REQUEST_DATA_SAME_VERSION_ID = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
    "meta_version": "0.0.0",
    "name": "string",
    "organization": "string",
    "versions": [
        {
            "id": "same",
            "author": [
                "string"
            ],
            "descriptor_type": [
                "CWL"
            ],
            "included_apps": [
                "https://bio.tools/tool/mytum.de/SNAP2/1",
                "https://bio.tools/bioexcel_seqqc"
            ],
            "is_production": True,
            "meta_version": "string",
            "name": "string",
            "signed": True,
            "verified_source": [
                "string"
            ]
        },
        {
            "id": "same",
            "author": [
                "string"
            ],
            "descriptor_type": [
                "CWL"
            ],
            "included_apps": [
                "https://bio.tools/tool/mytum.de/SNAP2/1",
                "https://bio.tools/bioexcel_seqqc"
            ],
            "is_production": True,
            "meta_version": "string",
            "name": "string",
            "signed": True,
            "verified_source": [
                "string"
            ]
        },
    ]
}
MOCK_REQUEST_DATA_VERSION_UPDATE = {
    "id": MOCK_ID,
    "author": [
        "string"
    ],
    "descriptor_type": [
        "CWL"
    ],
    "included_apps": [
        "https://bio.tools/tool/mytum.de/SNAP2/1",
        "https://bio.tools/bioexcel_seqqc"
    ],
    "is_production": True,
    "meta_version": "string",
    "name": "string",
    "signed": True,
    "verified_source": [
        "string"
    ]
}
MOCK_REQUEST_DATA_VERSION_UPDATE_2 = {
    "author": [
        "string"
    ],
    "descriptor_type": [
        "CWL"
    ],
    "included_apps": [
        "https://bio.tools/tool/mytum.de/SNAP2/1",
        "https://bio.tools/bioexcel_seqqc"
    ],
    "is_production": True,
    "meta_version": "string",
    "name": "string",
    "signed": True,
    "verified_source": [
        "string"
    ]
}
MOCK_CORRECT_FILE_DATA = [
    {
        "fileWrapper": {
            "checksum": [
                {
                    "checksum": "ea2a5db69bd20a42976838790bc29294df3af02b",
                    "type": "sha1"
                }
            ],
            "content": "string",
            "url": "sfdlmedl"
        },
        "toolFile": {
            "file_type": "TEST_FILE",
            "path": "string"
        }
    },
]
MOCK_INCORRECT_FILE_DATA_MISSING = [
    {
        "fileWrapper": {
            "checksum": [
                {
                    "checksum": "ea2a5db69bd20a42976838790bc29294df3af02b",
                    "type": "sha1"
                }
            ],
        },
        "toolFile": {
            "file_type": "TEST_FILE",
            "path": "string"
        }
    },
]
MOCK_INCORRECT_FILE_DATA_MISSING_1 = [
    {
        "fileWrapper": {
            "content": "string",
            "url": "sfdlmedl"
        },
        "toolFile": {
            "file_type": "TEST_FILE",
            "path": "string"
        }
    },
]


def test_generate_id_literal():
    """Test for generate_id function."""
    assert generate_id(charset=MOCK_ID_2, length=6) == "AAAAAA"


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

    temp_data = deepcopy(MOCK_REQUEST_DATA_VALID)
    temp_data['versions'][0]['files'] = MOCK_CORRECT_FILE_DATA
    data = temp_data
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
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client = MagicMock()
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one = mock

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client = MagicMock()
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_many = mock

    temp_data = deepcopy(MOCK_REQUEST_DATA_VALID)
    temp_data['versions'][0]['files'] = MOCK_CORRECT_FILE_DATA
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
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client = MagicMock()
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one = MagicMock()

    data = MOCK_REQUEST_DATA_SAME_VERSION_ID
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
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    mock_resp = deepcopy(MOCK_REQUEST_DATA_VALID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["id"] = "old"

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = MOCK_REQUEST_DATA_VALID
    with app.app_context():
        tool = RegisterTool(data, id=MOCK_ID)
        tool.register_metadata()
        assert isinstance(tool.data, dict)


def test_create_tool_valid_file_data():
    """Test for creating valid tool with file data."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )

    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    temp_data = deepcopy(MOCK_REQUEST_DATA_VALID)
    temp_data['versions'][0]['files'] = MOCK_CORRECT_FILE_DATA
    data = temp_data
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
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )

    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    temp_data = deepcopy(MOCK_REQUEST_DATA_VALID)
    temp_data['versions'][0]['files'] = MOCK_INCORRECT_FILE_DATA_MISSING
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
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )

    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    temp_data = deepcopy(MOCK_REQUEST_DATA_VALID)
    temp_data['versions'][0]['files'] = MOCK_INCORRECT_FILE_DATA_MISSING_1
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
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )

    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = MagicMock()
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.replace_one = MagicMock()

    temp_data = deepcopy(MOCK_REQUEST_DATA_VALID)
    temp_data['versions'][0]['files'] = MOCK_CORRECT_FILE_DATA
    data = temp_data
    with app.app_context():
        tool = RegisterTool(data, MOCK_ID)
        tool.register_metadata()
        assert isinstance(
            tool.data['id'],
            str,
        )


def test_update_tool_version():
    """Test for updating version."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    mock_resp = deepcopy(MOCK_REQUEST_DATA_VALID)
    mock_resp["id"] = MOCK_ID
    mock_resp["versions"][0]["id"] = MOCK_ID

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = MOCK_REQUEST_DATA_VERSION_UPDATE
    with app.app_context():
        version = RegisterToolVersion(data, id=MOCK_ID)
        version.register_metadata()
        assert isinstance(version.data, dict)


def test_update_tool_inf_loop():
    """Test for updating tool; running out of unique identifiers."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_ONE_ID,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    mock_resp = deepcopy(MOCK_REQUEST_DATA_VALID)
    mock_resp["id"] = MOCK_ID_2
    mock_resp["versions"][0]["id"] = MOCK_ID_2

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = MOCK_REQUEST_DATA_VALID
    with app.app_context():
        with pytest.raises(InternalServerError):
            tool = RegisterTool(data)
            tool.register_metadata()
            tool = RegisterTool(data)
            tool.register_metadata()
            print(tool.data['id'])


def test_update_version_inf_loop():
    """Test for updating version; running out of unique identifiers."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_ONE_ID,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    mock_resp = deepcopy(MOCK_REQUEST_DATA_VALID)
    mock_resp["id"] = MOCK_ID_2
    mock_resp["versions"][0]["id"] = MOCK_ID_2

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    data = MOCK_REQUEST_DATA_VERSION_UPDATE_2
    with app.app_context():
        with pytest.raises(InternalServerError):
            version = RegisterToolVersion(data, id=MOCK_ID_2)
            version.register_metadata()
            version = RegisterToolVersion(data, id=MOCK_ID_2)
            version.register_metadata()


def test_update_version_tool_na():
    """Test for updating version; tool not available."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_ONE_ID,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection

    mock_resp = deepcopy(MOCK_REQUEST_DATA_VALID)
    mock_resp["id"] = MOCK_ID_2
    mock_resp["versions"][0]["id"] = MOCK_ID_2

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)

    data = MOCK_REQUEST_DATA_VERSION_UPDATE_2
    with app.app_context():
        with pytest.raises(NotFound):
            version = RegisterToolVersion(data, id=MOCK_ID)
            version.register_metadata()
