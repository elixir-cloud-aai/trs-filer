"""Unit tests for `RegisterService()` controller."""

import string  # noqa: F401
from copy import deepcopy

from pymongo.errors import DuplicateKeyError

from flask import Flask
from foca.models.config import Config, MongoConfig
from unittest.mock import MagicMock
import mongomock

from trs_filer.ga4gh.trs.endpoints.service_info import (
    RegisterService
)


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


def test_get_service_info():
    """Test for getting correct service info config (new config added)."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )

    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        get_service_info = RegisterService().get_service_info()
        assert get_service_info == SERVICE_INFO_CONFIG


def test_get_service_info_duplicatekey():
    """Test for duplicated service info config."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )

    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['service_info'].client.insert_one = mock
    mock_db_call = MagicMock(name="Find_Obj")
    mock_db_call.return_value.sort.return_value \
        .limit.return_value.next.return_value = deepcopy(SERVICE_INFO_CONFIG)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['service_info'].client.find = mock_db_call
    with app.app_context():
        get_service_info = RegisterService().get_service_info()
        assert get_service_info == SERVICE_INFO_CONFIG
