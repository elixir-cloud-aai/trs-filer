"""Unit tests for endpoint controllers."""

from copy import deepcopy

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
import pytest

from trs_filer.ga4gh.trs.server import (
    deleteTool,
    postTool,
    putTool,
    toolsIdGet,
    toolsIdVersionsGet,
    toolsIdVersionsVersionIdGet,
)
from trs_filer.errors.exceptions import NotFound

INDEX_CONFIG = {
    'keys': [('id', 1)]
}
COLLECTION_CONFIG = {
    'indexes': [INDEX_CONFIG],
}
DB_CONFIG = {
    'collections': {
        'objects': COLLECTION_CONFIG,
    },
}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'trsStore': DB_CONFIG,
    },
}
ENDPOINT_CONFIG = {
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
    "tool_version": {
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
    "external_port": 80,
    "api_path": "ga4gh/trs/v2",
}
MOCK_REQUEST_DATA_1 = {
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
MOCK_ID = "mock_id"


def test_postTool():
    """Test `POST /tools` endpoint."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=MOCK_REQUEST_DATA_1):
        res = postTool.__wrapped__()
        assert isinstance(res, str)


def test_putTool():
    """Test `PUT /tools/{id}` endpoint."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=MOCK_REQUEST_DATA_1):
        res = putTool.__wrapped__("TMP001")
        assert isinstance(res, str)


def test_deleteTool():
    """Test `DELETE /tools/{id}` endpoint."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )
    data = deepcopy(MOCK_REQUEST_DATA_1)
    data['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['objects'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['objects'] \
        .client.insert_one(data).inserted_id
    del data['_id']
    with app.app_context():
        res = deleteTool.__wrapped__(MOCK_ID)
        assert res == MOCK_ID


def test_deleteTool_NotFound():
    """Test `DELETE /tools/{id}` endpoint with unavailable id."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )
    data = deepcopy(MOCK_REQUEST_DATA_1)
    app.config['FOCA'].db.dbs['trsStore'].collections['objects'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['objects'] \
        .client.insert_one(data).inserted_id
    del data['_id']
    with app.app_context():
        with pytest.raises(NotFound):
            deleteTool.__wrapped__(MOCK_ID)


def test_toolsIdGet():
    """Test for getting tool object using `tool_id`."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection
    temp_object = MOCK_REQUEST_DATA_1
    temp_object['id'] = "TMP001"
    temp_object['_id'] = app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one(temp_object).inserted_id
    del temp_object['_id']

    with app.app_context():
        res = toolsIdGet.__wrapped__("TMP001")
        assert res == temp_object


def test_toolsIdGet_object_not_found():
    """Test when requested `tool_id` is invalid."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient() \
        .db.collection
    temp_object = MOCK_REQUEST_DATA_1
    temp_object['id'] = "TMP001"
    temp_object['_id'] = app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one(temp_object).inserted_id
    del temp_object['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdGet.__wrapped__("TMP002")


def test_toolsIdVersionsGet():
    """Test for getting tool object versions associated with
    a given `tool_id`.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection
    temp_object = MOCK_REQUEST_DATA_1
    temp_object['id'] = "TMP001"
    temp_object['_id'] = app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one(temp_object).inserted_id
    del temp_object['_id']

    with app.app_context():
        res = toolsIdVersionsGet.__wrapped__("TMP001")
        assert res == temp_object["versions"]


def test_toolsIdVersionsGet_object_not_found():
    """Test when requested `tool_id` is invalid."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient() \
        .db.collection
    temp_object = MOCK_REQUEST_DATA_1
    temp_object['id'] = "TMP001"
    temp_object['_id'] = app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one(temp_object).inserted_id
    del temp_object['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsGet.__wrapped__("TMP002")


def test_toolsIdVersionsVersionIdGet():
    """Test for getting a specific version with given `version_id` from tool
    object associated with given `tool_id`.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection
    temp_object = MOCK_REQUEST_DATA_1
    temp_object['id'] = "TMP001"

    version_counter = 0
    for ver in range(0, len(temp_object["versions"])):
        temp_object["versions"][ver]['id'] = str(version_counter)
        version_counter = version_counter + 1

    temp_object['_id'] = app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one(temp_object).inserted_id
    del temp_object['_id']

    with app.app_context():
        res = toolsIdVersionsVersionIdGet.__wrapped__("TMP001", str(0))
        assert res == temp_object["versions"][0]


def test_toolsIdVersionsVersionIdGet_object_not_found():
    """Test when requested `tool_id` is valid but `version_id` is invalid."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient() \
        .db.collection
    temp_object = MOCK_REQUEST_DATA_1
    temp_object['id'] = "TMP001"

    version_counter = 0
    for ver in range(0, len(temp_object["versions"])):
        temp_object["versions"][ver]['id'] = str(version_counter)
        version_counter = version_counter + 1

    temp_object['_id'] = app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one(temp_object).inserted_id
    del temp_object['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdGet.__wrapped__("TMP001", str(99))
