import mongomock
from typing import (Dict, List)

from flask import Flask
from foca.models.config import Config, MongoConfig

from trs_filer.ga4gh.trs.server import (
    addTool,
    toolsGet,
    # toolsIdGet,
    getServiceInfo,
    toolClassesGet,
    # toolsIdVersionsGet,
    # toolsIdVersionsVersionIdGet,
    toolsIdVersionsVersionIdTypeTestsGet,
    toolsIdVersionsVersionIdTypeFilesGet,
    toolsIdVersionsVersionIdContainerfileGet,
    toolsIdVersionsVersionIdTypeDescriptorGet,
    toolsIdVersionsVersionIdTypeDescriptorRelativePathGet,
)
from trs_filer.errors.exceptions import (
    NotFound,
    Forbidden,
    BadRequest,
    Unauthorized,
    InternalServerError,
)

TEMP_ID = "id"
TEMP_VERSION_ID = "version_id"
TEMP_TYPE = "type"
TEMP_RELATIVE_PATH = "/a/b/c"

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


# def test_toolIdGet():
#     """Test for getting tool id.
#     """
#     res = toolsIdGet.__wrapped__(TEMP_ID)
#     assert isinstance(res, Dict)


# def test_toolsIdVersionsGet():
#     """Test for getting version list for a given tool id.
#     """
#     res = toolsIdVersionsGet.__wrapped__(TEMP_ID)
#     assert isinstance(res, List)


# def test_toolsIdVersionsVersionIdGet():
#     """Test for getting particular version of a particular
#     tool.
#     """
#     res = toolsIdVersionsVersionIdGet.__wrapped__(
#         TEMP_ID,
#         TEMP_VERSION_ID
#     )
#     assert isinstance(res, Dict)


def test_toolsGet():
    """Test for getting list of tools.
    """
    res = toolsGet.__wrapped__()
    assert isinstance(res, List)


def test_toolsIdVersionsVersionIdTypeDescriptorGet():
    """Test for addional tool descriptor.
    """
    res = toolsIdVersionsVersionIdTypeDescriptorGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, Dict)


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet():
    """Test for addional tool descriptor relative path.
    """
    res = toolsIdVersionsVersionIdTypeDescriptorRelativePathGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID,
        TEMP_RELATIVE_PATH
    )
    assert isinstance(res, Dict)


def test_toolsIdVersionsVersionIdTypeTestsGet():
    """Test for getting test jsons.
    """
    res = toolsIdVersionsVersionIdTypeTestsGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, List)


def test_toolsIdVersionsVersionIdTypeFilesGet():
    """Test for getting list of objects with file path and type.
    """
    res = toolsIdVersionsVersionIdTypeFilesGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, List)


def test_toolsIdVersionsVersionIdContainerfileGet():
    """Test for getting container specs.
    """
    res = toolsIdVersionsVersionIdContainerfileGet.__wrapped__(
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, List)


def test_toolClassesGet():
    """Test for getting tool classes.
    """
    res = toolClassesGet.__wrapped__()
    assert isinstance(res, List)


def test_getServiceInfo():
    """Test get service info.
    """
    res = getServiceInfo.__wrapped__()
    assert isinstance(res, Dict)


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


def test_errors():
    """ Test for exception raised. """
    assert NotFound.code == 404
    assert Forbidden.code == 403
    assert BadRequest.code == 400
    assert Unauthorized.code == 401
    assert InternalServerError.code == 500
