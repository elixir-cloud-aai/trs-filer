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
    toolsGet,
    toolsIdGet,
    getServiceInfo,
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
        'service_info': COLLECTION_CONFIG,
    },
}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'trsStore': DB_CONFIG,
    },
}
SERVICE_INFO_CONFIG = {
    "contactUrl": "mailto:support@example.com",
    "createdAt": "2019-06-04T12:58:19Z",
    "description": "This service provides...",
    "documentationUrl": "https://docs.myservice.example.com",
    "environment": "test",
    "id": "org.ga4gh.myservice",
    "name": "My project",
    "organization": {
        "name": "My organization",
        "url": "https://example.com"
    },
    "type": {
        "artifact": "beacon",
        "group": "org.ga4gh",
        "version": "1.0.0"
    },
    "updatedAt": "2019-06-04T12:58:19Z",
    "version": "1.0.0"
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
    "external_host": "1.2.3.4",
    "external_port": 80,
    "api_path": "ga4gh/trs/v2",
    "service_info": deepcopy(SERVICE_INFO_CONFIG),
}
MOCK_REQUEST_DATA_1 = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
    "has_checker": True,
    "meta_version": "0.0.0",
    "name": "string",
    "organization": "string",
    "toolclass": {
        "description": "string",
        "id": "string",
        "name": "string"
    },
    "versions": [
        {
            "author": [
                "string"
            ],
            "descriptor_type": [
                "CWL"
            ],
            "id": "v1",
            "images": [
                {
                    "checksum": [
                        {
                            "checksum": (
                                "77af4d6b9913e693e8d0b4b294fa62ade6054e6b2f1f"
                                "fb617ac955dd63fb0182"
                            ),
                            "type": "sha256"
                        }
                    ],
                    "image_name": "string",
                    "image_type": "Docker",
                    "registry_host": "string",
                    "size": 0,
                    "updated": "string"
                }
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
HEADER_CONFIG_1 = {
    'next_page': None,
    'last_page': None,
    'self_link': None,
    'current_offset': None,
    'current_limit': None,
}


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


def test_toolsGet():
    """Test for getting filter based tool list(filters present)."""
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
        res = toolsGet.__wrapped__(
            limit=1,
            offset=0,
            id="TMP001",
            checker=True,
            name="string",
            author="string",
            registry="string",
            toolname="string",
            toolClass="string",
            descriptorType="CWL",
            description=temp_object['description'],
            organization=temp_object['organization'],
            alias="630d31c3-381e-488d-b639-ce5d047a0142",
        )
        assert res == ([temp_object], '200', HEADER_CONFIG_1)


def test_toolsGet_nofilters():
    """Test for getting filter based tool list(no filters applied)."""
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
        res = toolsGet.__wrapped__()
        assert res == ([temp_object], '200', HEADER_CONFIG_1)


def test_getServiceInfo():
    """Test for getting service info config."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )

    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        res = getServiceInfo.__wrapped__()
        assert res == SERVICE_INFO_CONFIG
