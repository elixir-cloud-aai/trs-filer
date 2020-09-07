from flask import Flask
from foca.models.config import Config, MongoConfig
from unittest.mock import MagicMock
from trs_filer.ga4gh.trs.endpoints.register_tool_classes import (
    RegisterToolClass
)
from pymongo.errors import DuplicateKeyError
from addict import Dict


INDEX_CONFIG = {
    'keys': [('id', 1)]
}
COLLECTION_CONFIG = {
    'indexes': [INDEX_CONFIG],
}
DB_CONFIG = {
    'collections': {
        'toolclasses': COLLECTION_CONFIG,
    },
}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'trsStore': DB_CONFIG,
    },
}

ENDPOINT_CONFIG_CHARSET_LITERAL = {
    "toolclass": {
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
    "description": "string",
    "id": "string",
    "name": "string"
}


def test_generate_id():
    """Test for generate_id method."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )
    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_VALID
    with app.app_context():
        assert isinstance(RegisterToolClass(request_data).generate_id(), str)


def test_create_tool_duplicate_key():
    """Test for valid duplicate key error."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_CHARSET_LITERAL,
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['toolclasses'].client = MagicMock()
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['toolclasses'].client.insert_one = mock

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_VALID
    with app.app_context():
        assert isinstance(
            RegisterToolClass(request_data).register_toolclass()['id'],
            str,
        )
