from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
import pytest

from trs_filer.ga4gh.trs.server import (
    addTool,
    toolsIdGet,
)
from trs_filer.errors.exceptions import NotFound  # noqa: F401

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
    "tools": {
        "id_charset": 'string.digits',
        "id_length": 6
    },
    "tool_versions": {
        "id_charset": 'string.digits',
        "id_length": 6
    },
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


def test_addTool():
    """Test add new tool object.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=MOCK_REQUEST_DATA_1):
        res = addTool.__wrapped__()
        assert isinstance(res, str)


def test_toolsIdGet():
    """Test for getting tool object using `tool_id`.
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
        res = toolsIdGet.__wrapped__("TMP001")
        assert res == temp_object


def test_toolsIdGet_object_not_found():
    """Test when requested tool_id is invalid.
    """
    with pytest.raises(NotFound):
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
            toolsIdGet.__wrapped__("TMP002")
