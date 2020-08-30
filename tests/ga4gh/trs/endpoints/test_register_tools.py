import mongomock
import string  # noqa: F401

from pymongo.errors import DuplicateKeyError

from flask import Flask
from foca.models.config import Config, MongoConfig
from unittest.mock import MagicMock
from addict import Dict

from trs_filer.ga4gh.trs.endpoints.register_tools import (
    RegisterObject
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
    },
}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'trsStore': DB_CONFIG,
    },
}
ENDPOINT_CONFIG_1 = {
    "tools": {
        "id_charset": 'string.digits',
        "id_length": 6
    },
    "tool_versions": {
        "id_charset": 'string.digits',
        "id_length": 6
    }
}
ENDPOINT_CONFIG_2 = {
    "tools": {
        "id_charset": '0123456789',
        "id_length": 6
    },
    "tool_versions": {
        "id_charset": 'string.digits',
        "id_length": 6
    }
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


MOCK_REQUEST_DATA_2 = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
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
            "meta_version": "0.0.1",
            "name": "string",
            "signed": True,
            "verified_source": [
                "string"
            ]
        },
        {
            "author": [
                "string"
            ],
            "descriptor_type": [
                "CWL"
            ],
            "included_apps": [
                "https://bio.tools/tool/mytum.de/SNAP3/1",
                "https://bio.tools/bioexcel_seqqc/1"
            ],
            "is_production": True,
            "meta_version": "0.1.0",
            "name": "string",
            "signed": True,
            "verified_source": [
                "string"
            ]
        },
        {
            "author": [
                "string"
            ],
            "descriptor_type": [
                "CWL"
            ],
            "included_apps": [
                "https://bio.tools/tool/mytum.de/SNAP4/1",
                "https://bio.tools/bioexcel_seqqc/1"
            ],
            "is_production": True,
            "meta_version": "1.1.0",
            "name": "string",
            "signed": True,
            "verified_source": [
                "string"
            ]
        }
    ]
}

MOCK_REQUEST_DATA_3 = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
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
            "name": "string",
            "signed": True,
            "verified_source": [
                "string"
            ]
        }
    ]
}

MOCK_REQUEST_DATA_4 = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
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
            "name": "string",
            "signed": True,
            "meta_version": "alpha",
            "verified_source": [
                "string"
            ]
        },
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
            "name": "string",
            "signed": True,
            "meta_version": "beta",
            "verified_source": [
                "string"
            ]
        }
    ]
}

MOCK_REQUEST_DATA_5 = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "description": "string",
    "name": "string",
    "organization": "string",
}

SAMPLE_TOOL_CLASS = {
    "description": "Temporary tool class.",
    "id": "123456",
    "name": "ToolClass"
}

SAMPLE_VERSION_LIST = ["1.0.0", "1.2.0", "2.0.0"]


def test_generate_id():
    """Test for generate_id method."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )
    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_1
    with app.app_context():
        assert isinstance(RegisterObject(request_data).generate_id(), str)


def test_generate_id_no_expression():
    """Test for generate_id method, raw charset string supplied."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_2
    )
    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_1
    with app.app_context():
        assert isinstance(RegisterObject(request_data).generate_id(), str)


def test_latest_version_return():
    """ Test for finding latest version from versions list. """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )
    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_1

    with app.app_context():
        assert (
            RegisterObject(request_data)
            .get_latest_meta_version(SAMPLE_VERSION_LIST) == "2.0.0"
        )


def test_create_tool_object_meta_version():
    """ Test for valid meta_version when
    set from user specifically.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_1

    with app.app_context():
        assert (
            RegisterObject(request_data)
            .register_object().get("meta_version") == "0.0.0"
        )


def test_create_tool_object_meta_version_sub_version_based():
    """ Test for valid meta_version when assigned
    based on the version information available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_2

    with app.app_context():
        assert (
            RegisterObject(request_data)
            .register_object().get("meta_version") == "1.1.0"
        )


def test_create_tool_no_meta_version():
    """ Test for valid meta_version when not
    specified, i.e, neither in tools, nor in versions.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_3

    with app.app_context():
        assert (
            RegisterObject(request_data)
            .register_object().get("meta_version") == ""
        )


def test_create_tool_non_semantic_versions():
    """ Test for valid meta_version when non
    semantic versioning present.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_4

    with app.app_context():
        assert (
            RegisterObject(request_data)
            .register_object().get("meta_version") == ""
        )


def test_create_tool_versions_checker_absence():
    """ Test for valid meta_version when versions not present.
    Also covers the case when checker_url is absent.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = mongomock.MongoClient().db.collection

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_5

    with app.app_context():
        tool_data = RegisterObject(request_data).register_object()
        assert (tool_data.get("meta_version") == "")
        assert (tool_data.get("has_checker") is False)


def test_create_tool_duplicate_key():
    """ Test for valid duplicate key error. """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG_1
    )

    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client = MagicMock()
    mock = MagicMock(side_effect=[DuplicateKeyError(''), None])
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['objects'].client.insert_one = mock

    request_data = Dict()
    request_data.json = MOCK_REQUEST_DATA_1
    with app.app_context():
        assert isinstance(
            RegisterObject(request_data)
            .register_object()['id'], str
        )
