"""Unit tests for endpoint controllers."""

from copy import deepcopy

from flask import Flask
from foca.models.config import (Config, MongoConfig)
import mongomock
import pytest

from tests.mock_data import (
    ENDPOINT_CONFIG,
    HEADERS_PAGINATION,
    MOCK_ID,
    MOCK_TOOL_CLASS,
    MOCK_TOOL_VERSION_ID,
    MOCK_VERSION_ID,
    MONGO_CONFIG,
    SERVICE_INFO_CONFIG,
)
from trs_filer.ga4gh.trs.server import (
    deleteTool,
    deleteToolClass,
    deleteToolVersion,
    getServiceInfo,
    postServiceInfo,
    postTool,
    postToolVersion,
    putTool,
    putToolVersion,
    toolsGet,
    toolsIdGet,
    toolsIdVersionsGet,
    toolsIdVersionsVersionIdGet,
    postToolClass,
    toolClassesGet,
    putToolClass,
)
from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)


# GET /tools/{id}
def test_toolsIdGet():
    """Test for getting a tool associated with a given identifier."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        res = toolsIdGet.__wrapped__(id=MOCK_ID)
        assert res == mock_resp


def test_toolsIdGet_NotFound():
    """Test for getting a tool associated with a given identifier when a tool
    with that identifier is not available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdGet.__wrapped__(id=MOCK_ID + MOCK_ID)


# GET /tools/{id}/versions
def test_toolsIdVersionsGet():
    """Test for getting tool versions associated with a given identifier."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        res = toolsIdVersionsGet.__wrapped__(id=MOCK_ID)
        assert res == mock_resp["versions"]


def test_toolsIdVersionsGet_NotFound():
    """Test for getting tool versions associated with a given identifier when a
    tool with that identifier is not available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsGet.__wrapped__(id=MOCK_ID + MOCK_ID)


# GET /tools/{id}/versions/{version_id}
def test_toolsIdVersionsVersionIdGet():
    """Test for getting a specific version of a tool associated with given tool
    and version identifiers.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = toolsIdVersionsVersionIdGet.__wrapped__(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == mock_resp["versions"][0]


def test_toolsIdVersionsVersionIdGet_tool_NotFound():
    """Test for getting a specific version of a tool associated with given tool
    and version identifiers when a tool with the specified identifier is not
    available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdGet.__wrapped__(
                id=MOCK_ID + MOCK_ID,
                version_id=MOCK_ID,
            )


def test_toolsIdVersionsVersionIdGet_version_NotFound():
    """Test for getting a specific version of a tool associated with given tool
    and version identifiers when a version with the specified identifier is not
    available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID
            )


# GET /tools
def test_toolsGet():
    """Test for getting a list of all available tools; no filters specified.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    with app.app_context():
        res = toolsGet.__wrapped__()
        assert res == ([data], '200', HEADERS_PAGINATION)


def test_toolsGet_filters():
    """Test for getting a list of all available tools; all defined filters
    specified.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    with app.app_context():
        res = toolsGet.__wrapped__(
            id=data['id'],
            limit=1,
            offset=0,
            checker=data['has_checker'],
            name=data['versions'][0]['images'][0]['image_name'],
            alias=data['aliases'][0],
            author=data['versions'][0]['author'][0],
            registry=data['versions'][0]['images'][0]['registry_host'],
            toolname=data['name'],
            toolClass=data['toolclass']['name'],
            descriptorType=data['versions'][0]['descriptor_type'][0],
            description=data['description'],
            organization=data['organization'],
        )
        assert res == ([data], '200', HEADERS_PAGINATION)


# GET /toolClasses
def test_toolClassesGet():
    """Test for getting a list of all available tool classes.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    with app.app_context():
        res = toolClassesGet.__wrapped__()
        assert res == [data]


# GET /service-info
def test_getServiceInfo():
    """Test for getting service info."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(SERVICE_INFO_CONFIG)
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = getServiceInfo.__wrapped__()
        assert res == SERVICE_INFO_CONFIG


# POST /service-info
def test_postServiceInfo():
    """Test for creating service info."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(SERVICE_INFO_CONFIG)):
        postServiceInfo.__wrapped__()
        res = getServiceInfo.__wrapped__()
        assert res == SERVICE_INFO_CONFIG


# POST /tools
def test_postTool():
    """Test for creating a tool; identifier assigned by implementation."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = postTool.__wrapped__()
        assert isinstance(res, str)


# PUT /tools/{id}
def test_putTool():
    """Test for creating a tool; identifier provided by user."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = putTool.__wrapped__(id=MOCK_ID)
        assert res == MOCK_ID


def test_putTool_update():
    """Test for updating an existing tool."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = {}
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = putTool.__wrapped__(id=MOCK_ID)
        assert res == MOCK_ID


# DELETE /tools/{id}
def test_deleteTool():
    """Test for deleting a tool."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = deleteTool.__wrapped__(id=MOCK_ID)
        assert res == MOCK_ID


def test_deleteTool_NotFound():
    """Test `DELETE /tools/{id}` endpoint with unavailable id."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            deleteTool.__wrapped__(id=MOCK_ID)


# POST /tools/{id}/versions
def test_postToolVersion():
    """Test for appending or replacing a version of a tool associated with a
    given `id`.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = {}
    mock_resp["id"] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client.insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = postToolVersion.__wrapped__(id=MOCK_ID)
        assert isinstance(res, str)


# PUT /tools/{id}/versions/{version_id}
def test_putToolVersion():
    """Test for creating a tool version; identifier provided by user."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = {}
    mock_resp["id"] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client.insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = putToolVersion.__wrapped__(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert isinstance(res, str)


def test_putToolVersion_update():
    """Test for updating an existing tool version."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = MOCK_TOOL_VERSION_ID
    mock_resp["id"] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client.insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = putToolVersion.__wrapped__(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert isinstance(res, str)


# DELETE /tools/{id}/versions/{version_id}
def test_deleteToolVersion():
    """Test for deleting a version `version_id` of a tool associated with a
    given `id`.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'].append(deepcopy(MOCK_VERSION_ID))
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    with app.app_context():
        res = deleteToolVersion.__wrapped__(
            id=MOCK_ID,
            version_id=data['versions'][0]['id'],
        )
        assert res == data['versions'][0]['id']


def test_deleteToolVersion_tool_NotFound():
    """Test for deleting a version `version_id` of a tool associated with a
    given `id` when a tool with the specified identifier is not available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            deleteToolVersion.__wrapped__(
                id=MOCK_ID + MOCK_ID,
                version_id=MOCK_ID,
            )


def test_deleteToolVersion_version_NotFound():
    """Test for deleting a version `version_id` of a tool associated with a
    given `id` when a version with the specified `version_id` is not available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            deleteToolVersion.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
            )


def test_deleteToolVersion_BadRequest():
    """Test for deleting a version `version_id` of a tool associated with a
    given `id` when that version is the last remaining version associated with
    the tool.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    with app.app_context():
        with pytest.raises(BadRequest):
            deleteToolVersion.__wrapped__(
                id=MOCK_ID,
                version_id=data['versions'][0]['id'],
            )


def test_deleteToolVersion_InternalServerError():
    """Test for deleting a version `version_id` of a tool associated with a
    given `id` when the deletion was incomplete (either only the tool or only
    the associated files were deleted).
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'].append(deepcopy(MOCK_VERSION_ID))
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    with app.app_context():
        with pytest.raises(InternalServerError):
            deleteToolVersion.__wrapped__(
                id=MOCK_ID,
                version_id=data['versions'][0]['id'],
            )


# POST /toolClasses
def test_postToolClass():
    """Test for creating a tool class; identifier assigned by implementation.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection

    data = deepcopy(MOCK_TOOL_CLASS)
    del data['id']
    with app.test_request_context(json=data):
        res = postToolClass.__wrapped__()
        assert isinstance(res, str)


# PUT /toolClasses
def test_putToolClass():
    """Test for creating a tool class; identifier provided by user."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection

    data = deepcopy(MOCK_TOOL_CLASS)
    del data['id']
    with app.test_request_context(json=MOCK_TOOL_CLASS):
        res = putToolClass.__wrapped__(id=MOCK_ID)
        assert isinstance(res, str)
        assert res == MOCK_ID


def test_putToolClass_update():
    """Test for updating an existing tool class."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG
    )
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_CLASS)
    del data['id']
    with app.test_request_context(json=MOCK_TOOL_CLASS):
        res = putToolClass.__wrapped__(id=MOCK_ID)
        assert isinstance(res, str)
        assert res == MOCK_ID


# DELETE /toolClasses
def test_deleteToolClass():
    """Test for deleting a tool class associated with a given `id`."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = deleteToolClass.__wrapped__(
            id=MOCK_ID,
        )
        assert res == MOCK_ID


def test_deleteToolClass_NotFound():
    """Test for deleting a tool associated with a given tool `id` when a tool
    class with the specified `id` is not available.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            deleteToolClass.__wrapped__(
                id=MOCK_ID + MOCK_ID,
            )


def test_deleteToolClass_BadRequest():
    """Test for deleting a tool class associated with a given `id` when a tool
    associated with this tool class exists.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp_tools = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp_classes = deepcopy(MOCK_TOOL_CLASS)
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp_tools)
    app.config['FOCA'].db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp_classes)

    with app.app_context():
        with pytest.raises(BadRequest):
            deleteToolClass.__wrapped__(
                id=MOCK_ID,
            )
