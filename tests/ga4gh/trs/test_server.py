"""Unit tests for endpoint controllers."""

from copy import deepcopy

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock
import pytest

from tests.mock_data import (
    ENDPOINT_CONFIG,
    HEADERS_PAGINATION,
    MOCK_ID,
    MOCK_TOOL_VERSION_ID,
    MOCK_VERSION_ID,
    MONGO_CONFIG,
    SERVICE_INFO_CONFIG,
)
from trs_filer.ga4gh.trs.server import (
    deleteTool,
    deleteToolVersion,
    getServiceInfo,
    postServiceInfo,
    postTool,
    postToolVersion,
    putTool,
    toolsGet,
    toolsIdGet,
    toolsIdVersionsGet,
    toolsIdVersionsVersionIdGet,
)
from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)


def test_postTool():
    """Test `POST /tools` endpoint."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = postTool.__wrapped__()
        assert isinstance(res, str)


def test_putTool():
    """Test `PUT /tools/{id}` endpoint."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = putTool.__wrapped__(MOCK_ID)
        assert res == MOCK_ID


def test_deleteTool():
    """Test `DELETE /tools/{id}` endpoint."""
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
        res = deleteTool.__wrapped__(MOCK_ID)
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
            deleteTool.__wrapped__(MOCK_ID)


def test_toolsIdGet():
    """Test for getting tool object using `tool_id`."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        res = toolsIdGet.__wrapped__(MOCK_ID)
        assert res == mock_resp


def test_toolsIdGet_object_not_found():
    """Test when requested `tool_id` is invalid."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdGet.__wrapped__(MOCK_ID + MOCK_ID)


def test_toolsIdVersionsGet():
    """Test for getting tool object versions associated with
    a given `tool_id`.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        res = toolsIdVersionsGet.__wrapped__(MOCK_ID)
        assert res == mock_resp["versions"]


def test_toolsIdVersionsGet_object_not_found():
    """Test when requested `tool_id` is invalid."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsGet.__wrapped__(MOCK_ID + MOCK_ID)


def test_toolsIdVersionsVersionIdGet():
    """Test for getting a specific version with given `version_id` from tool
    object associated with given `tool_id`.
    """
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)

    with app.app_context():
        res = toolsIdVersionsVersionIdGet.__wrapped__(
            id=MOCK_ID,
            version_id=MOCK_ID
        )
        assert res == mock_resp["versions"][0]


def test_toolsIdVersionsVersionIdGet_object_not_found():
    """Test when requested `tool_id` is valid but `version_id` is invalid."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID
            )


def test_toolsGet():
    """Test for getting filter based tool list(filters present)."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    with app.app_context():
        res = toolsGet.__wrapped__(
            limit=1,
            offset=0,
            id=MOCK_ID,
            checker=True,
            name="string",
            author="string",
            registry="string",
            toolname="string",
            toolClass="string",
            descriptorType="CWL",
            description=data['description'],
            organization=data['organization'],
            alias="630d31c3-381e-488d-b639-ce5d047a0142",
        )
        assert res == ([data], '200', HEADERS_PAGINATION)


def test_toolsGet_nofilters():
    """Test for getting filter based tool list(no filters applied)."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    with app.app_context():
        res = toolsGet.__wrapped__()
        assert res == ([data], '200', HEADERS_PAGINATION)


def test_postToolVersion():
    """Test for updating versions for a give `tool_id`."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp["id"] = "TMP001"
    app.config['FOCA'].db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'].collections['files'] \
        .client = mongomock.MongoClient().db.collection
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['tools'].client.insert_one(mock_resp)
    app.config['FOCA'].db.dbs['trsStore'] \
        .collections['files'].client.insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = postToolVersion.__wrapped__("TMP001")
        assert isinstance(res, str)


def test_deleteToolVersion():
    """Test for `DELETE /tools/{id}/versions/{version_id}` endpoint."""
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


def test_deleteToolVersion_NotFound():
    """Test for `DELETE /tools/{id}/versions/{version_id}` endpoint."""
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
    """Test for `DELETE /tools/{id}/versions/{version_id}` endpoint."""
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
    """Test for `DELETE /tools/{id}/versions/{version_id}` endpoint."""
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
