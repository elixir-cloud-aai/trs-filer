"""Unit tests for `RegisterObject()` controller."""

import string  # noqa: F401

import pytest
from pymongo.errors import DuplicateKeyError

from flask import Flask
from foca.models.config import Config, MongoConfig
from unittest.mock import MagicMock
from addict import Dict

from trs_filer.ga4gh.trs.endpoints.register_tools import (
    RegisterObject
)
from trs_filer.errors.exceptions import BadRequest

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
}
ENDPOINT_CONFIG_CHARSET_LITERAL = {
    "tool": {
        "id": {
            "charset": '0123456789',
            "length": 6,
        },
        "meta_version": {
            "init": 1,
            "increment": 1,
        },
    },
    "tool_version": {
        "id": {
            "charset": '0123456789',
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


def test_generate_id():
    """Test for generate_id method."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )
    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_VALID
    with app.app_context():
        assert isinstance(RegisterObject(request_data).generate_id(), str)


def test_generate_id_no_expression():
    """Test for generate_id method, raw charset string supplied."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )
    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_VALID
    with app.app_context():
        assert isinstance(RegisterObject(request_data).generate_id(), str)


def test_create_tool_duplicate_key():
    """Test for valid duplicate key error."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_EXPRESSION,
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = MagicMock()
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one = mock

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_VALID
    with app.app_context():
        assert isinstance(
            RegisterObject(request_data).register_object()['id'],
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
        .collections['objects'].client = MagicMock()
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one = MagicMock()

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_SAME_VERSION_ID
    with app.app_context():
        with pytest.raises(BadRequest):
            RegisterObject(request_data).register_object()
