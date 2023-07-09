"""Unit tests for endpoint controllers."""

from copy import deepcopy

from flask import Flask
from flask import (request)
from foca.models.config import (Config, MongoConfig)
import mongomock
import pytest

from tests.mock_data import (
    CUSTOM_CONFIG,
    HEADERS_PAGINATION,
    MOCK_ID,
    MOCK_ID_2,
    MOCK_TOOL_CLASS,
    MOCK_TOOL_VERSION_ID,
    MOCK_VERSION_ID,
    MONGO_CONFIG,
    SERVICE_INFO_CONFIG,
    MOCK_CONTAINER_FILE,
    MOCK_DESCRIPTOR_FILE,
    MOCK_DESCRIPTOR_SEC_FILE,
    MOCK_OTHER_FILE,
    MOCK_TEST_FILE,
    MOCK_VERSION_NO_ID,
    TEST_LIMIT,
    TEST_LIMIT_2,
    TEST_OFFSET,
    TEST_OFFSET_2,
)
from trs_filer.ga4gh.trs.server import (
    deleteTool,
    deleteToolClass,
    deleteToolVersion,
    getServiceInfo,
    postServiceInfo,
    postTool,
    postToolClass,
    postToolVersion,
    putTool,
    putToolClass,
    putToolVersion,
    toolClassesGet,
    toolsGet,
    toolsIdGet,
    toolsIdVersionsGet,
    toolsIdVersionsVersionIdTypeFilesGet,
    toolsIdVersionsVersionIdContainerfileGet,
    toolsIdVersionsVersionIdGet,
    toolsIdVersionsVersionIdTypeDescriptorGet,
    toolsIdVersionsVersionIdTypeDescriptorRelativePathGet,
    toolsIdVersionsVersionIdTypeTestsGet,
)
from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)
from trs_filer.custom_config import CustomConfig


# GET /toolClasses
def test_toolClassesGet():
    """Test for getting a list of all available tool classes.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    with app.app_context():
        res = toolClassesGet.__wrapped__()
        assert res == [data]


# GET /tools
def test_toolsGet():
    """Test for getting a list of all available tools; no filters specified.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    del data['versions'][0]['files']
    HEADERS_PAGINATION_RESULT = deepcopy(HEADERS_PAGINATION)
    with app.test_request_context():
        HEADERS_PAGINATION_RESULT["self_link"] = request.url
        res = toolsGet.__wrapped__()
        assert res == ([data], '200', HEADERS_PAGINATION_RESULT)


def test_toolsGet_pagination():
    """Test for getting a list of all available tools; pagination values specified.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    mock_resp2 = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp2['id'] = MOCK_ID_2
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp2)

    data = deepcopy(MOCK_VERSION_NO_ID)
    data['id'] = MOCK_ID_2

    HEADERS_PAGINATION_RESULT = deepcopy(HEADERS_PAGINATION)

    with app.test_request_context():
        HEADERS_PAGINATION_RESULT["self_link"] = request.url
        HEADERS_PAGINATION_RESULT["next_page"] = (
            f"{request.base_url}?offset={int(TEST_OFFSET) + TEST_LIMIT}&limit="
            f"{TEST_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["last_page"] = (
            f"{request.base_url}?offset={max(0,int(TEST_OFFSET) - TEST_LIMIT)}"
            f"&limit={TEST_LIMIT}"
        )
        HEADERS_PAGINATION_RESULT["current_offset"] = TEST_OFFSET
        HEADERS_PAGINATION_RESULT["current_limit"] = TEST_LIMIT
        res = toolsGet.__wrapped__(
            limit=TEST_LIMIT,
            offset=TEST_OFFSET,
        )
        assert res == ([data], '200', HEADERS_PAGINATION_RESULT)


def test_toolsGet_pagination_negativeLimit():
    """Test for getting a list of all available tools; pagination values
    specified, given a negative limit.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    mock_resp2 = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp2['id'] = MOCK_ID_2
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp2)

    data = deepcopy(MOCK_VERSION_NO_ID)
    data['id'] = MOCK_ID_2

    HEADERS_PAGINATION_RESULT = {}

    with app.test_request_context():
        res = toolsGet.__wrapped__(
            limit=TEST_LIMIT_2,
            offset=TEST_OFFSET,
        )
        assert res == ([], '422', HEADERS_PAGINATION_RESULT)


def test_toolsGet_pagination_negativeOffset():
    """Test for getting a list of all available tools; pagination values
    specified, given a negative offset.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    mock_resp2 = deepcopy(MOCK_VERSION_NO_ID)
    mock_resp2['id'] = MOCK_ID_2
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp2)

    data = deepcopy(MOCK_VERSION_NO_ID)
    data['id'] = MOCK_ID_2

    HEADERS_PAGINATION_RESULT = {}

    with app.test_request_context():
        res = toolsGet.__wrapped__(
            limit=TEST_LIMIT,
            offset=TEST_OFFSET_2,
        )
        assert res == ([], '422', HEADERS_PAGINATION_RESULT)


def test_toolsGet_filters():
    """Test for getting a list of all available tools; all defined filters
    specified.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    data = deepcopy(MOCK_TOOL_VERSION_ID)
    data['id'] = MOCK_ID
    del data['versions'][0]['files']

    HEADERS_PAGINATION_RESULT = deepcopy(HEADERS_PAGINATION)
    with app.test_request_context():
        HEADERS_PAGINATION_RESULT["self_link"] = request.base_url
        res = toolsGet.__wrapped__(
            id=data['id'],
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
        assert res == ([data], '200', HEADERS_PAGINATION_RESULT)


# GET /tools/{id}
def test_toolsIdGet():
    """Test for getting a tool associated with a given identifier."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['_id']
    del mock_resp['versions'][0]['files']

    with app.app_context():
        res = toolsIdGet.__wrapped__(id=MOCK_ID)
        assert res == mock_resp


def test_toolsIdGet_NotFound():
    """Test for getting a tool associated with a given identifier when a tool
    with that identifier is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['_id']

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdGet.__wrapped__(id=MOCK_ID + MOCK_ID)


# GET /tools/{id}/versions
def test_toolsIdVersionsGet():
    """Test for getting tool versions associated with a given identifier."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['_id']
    del mock_resp['versions'][0]['files']

    with app.app_context():
        res = toolsIdVersionsGet.__wrapped__(id=MOCK_ID)
        assert res == mock_resp["versions"]


def test_toolsIdVersionsGet_NotFound():
    """Test for getting tool versions associated with a given identifier when a
    tool with that identifier is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    del mock_resp['versions'][0]['files']

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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID
            )


# GET /tools/{id}/versions/{version_id}/containerfile
def test_toolsIdVersionsVersionIdContainerfileGet():
    """Test for getting container files associated with a specific tool version
    identified by the given tool and version identifiers.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = toolsIdVersionsVersionIdContainerfileGet.__wrapped__(
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == [MOCK_CONTAINER_FILE["file_wrapper"]]


def test_toolsIdVersionsVersionIdContainerfileGet_tool_na_NotFound():
    """Test for getting container files associated with a specific tool version
    identified by the given tool and version identifiers when a tool with the
    specified identifier is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdContainerfileGet.__wrapped__(
                id=MOCK_ID + MOCK_ID,
                version_id=MOCK_ID,
            )


def test_toolsIdVersionsVersionIdContainerfileGet_version_na_NotFound():
    """Test for getting container files associated with a specific tool version
    identified by the given tool and version identifiers when a version with
    the specified identifier is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdContainerfileGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
            )


def test_toolsIdVersionsVersionIdContainerfileGet_no_containerfile_NotFound():
    """Test for getting container files associated with a specific tool version
    identified by the given tool and version identifiers when no container
    specification file is available for the tool version.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'][0]['files'] = []

    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            res = toolsIdVersionsVersionIdContainerfileGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID,
            )
            assert res == []


# GET /tools/{id}/versions/{version_id}/{type}/descriptor
def test_toolsIdVersionsVersionIdTypeDescriptorGet():
    """Test for getting `PRIMARY_DESCRIPTOR` wrapper associated with a specific
    tool version identified by the given tool and version identifiers for the
    given input `type`.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = toolsIdVersionsVersionIdTypeDescriptorGet.__wrapped__(
            type='CWL',
            id=MOCK_ID,
            version_id=MOCK_ID,
        )
        assert res == MOCK_DESCRIPTOR_FILE["file_wrapper"]


def test_toolsIdVersionsVersionIdTypeDescriptorGet_tool_na_NotFound():
    """Test for getting `PRIMARY_DESCRIPTOR` wrapper associated with a specific
    tool version identified by the given tool and version identifiers for the
    given input `type` when a tool with the specified identifier is not
    available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeDescriptorGet.__wrapped__(
                id=MOCK_ID + MOCK_ID,
                version_id=MOCK_ID,
                type="CWL",
            )


def test_toolsIdVersionsVersionIdTypeDescriptorGet_version_na_NotFound():
    """Test for getting `PRIMARY_DESCRIPTOR` wrapper associated with a specific
    tool version identified by the given tool and version identifiers for the
    given input `type` when a version with the specified identifier is not
    available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeDescriptorGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
                type="CWL",
            )


def test_toolsIdVersionsVersionIdTypeDescriptorGet_type_NotFound():
    """Test for getting `PRIMARY_DESCRIPTOR` wrapper associated with a specific
    tool version identified by the given tool and version identifiers for the
    given input `type` when the descriptor type is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'][0]['files'] = []
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeDescriptorGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID,
                type='CWL',
            )


# GET /tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}
def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet():
    """Test for getting descriptor wrapper associated with a specific tool
    version identified by the given tool and version identifiers for the
    given input `type` and `relative_path`.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = toolsIdVersionsVersionIdTypeDescriptorRelativePathGet \
            .__wrapped__(
                type='CWL',
                id=MOCK_ID,
                version_id=MOCK_ID,
                relative_path='path_sec_desc_cwl',
            )
        assert res == MOCK_DESCRIPTOR_SEC_FILE["file_wrapper"]


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_tool_NotFound():
    """Test for getting descriptor wrapper associated with a specific tool
    version identified by the given tool and version identifiers for the
    given input `type` and `relative_path` when a tool with the specified
    identifier is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeDescriptorRelativePathGet.__wrapped__(
                id=MOCK_ID + MOCK_ID,
                version_id=MOCK_ID,
                type="CWL",
                relative_path='path_tmp',
            )


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_vers_NotFound():
    """Test for getting descriptor wrapper associated with a specific tool
    version identified by the given tool and version identifiers for the
    given input `type` and `relative_path` when a tool version with the
    specified identifier is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeDescriptorRelativePathGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
                type="CWL",
                relative_path='path_tmp',
            )


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_type_NotFound():
    """Test for getting descriptor wrapper associated with a specific tool
    version identified by the given tool and version identifiers for the
    given input `type` and `relative_path` when a descriptor of the specified
    descriptor type is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeDescriptorRelativePathGet.__wrapped__(
                type='WDL',
                id=MOCK_ID,
                version_id=MOCK_ID,
                relative_path='path_tmp',
            )


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet_path_NotFound():
    """Test for getting descriptor wrapper associated with a specific tool
    version identified by the given tool and version identifiers for the
    given input `type` and `relative_path` when a descriptor is not available
    at the specified path.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeDescriptorRelativePathGet.__wrapped__(
                type='CWL',
                id=MOCK_ID,
                version_id=MOCK_ID,
                relative_path='path_tmp_na',
            )


# GET /tools/{id}/versions/{version_id}/{type}/files
def test_toolsIdVersionsVersionIdTypeFilesGet():
    """Test for getting descriptor files associated with a specific tool version
    identified by the given tool and version identifiers.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'][0]['files'][4]['type'] = "WDL"
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = toolsIdVersionsVersionIdTypeFilesGet.__wrapped__(
            id=MOCK_ID,
            version_id=MOCK_ID,
            type="CWL"
        )
        descriptors = [
            _desc for _desc in mock_resp['versions'][0]['files']
            if _desc['tool_file']['file_type'] != 'CONTAINERFILE'
        ]
        assert res == [
            _file['tool_file'] for _file in descriptors
            if _file['type'] == "CWL"
        ]
        assert len(res) == len(descriptors) - 1


def test_toolsIdVersionsVersionIdTypeFilesGet_tool_na_NotFound():
    """Test for getting descriptor files associated with a specific tool version
    identified by the given tool and version identifiers with specified tool
    identifier not present.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'][0]['files'][4]['type'] = "WDL"
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeFilesGet.__wrapped__(
                id=MOCK_ID + MOCK_ID,
                version_id=MOCK_ID,
                type="CWL"
            )


def test_toolsIdVersionsVersionIdTypeFilesGet_version_na_NotFound():
    """Test for getting descriptor files associated with a specific tool version
    identified by the given tool and version identifiers with specified tool
    version identifier not present.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'][0]['files'][4]['type'] = "WDL"
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeFilesGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
                type="CWL"
            )


def test_toolsIdVersionsVersionIdTypeFilesGet_no_tool_file_NotFound():
    """Test for getting tool files associated with a specific tool version
    identified by the given tool and version identifiers when no
    specification file is available for the tool version.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'][0]['files'] = []
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeFilesGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
                type=MOCK_OTHER_FILE['type']
            )


def test_toolsIdVersionsVersionIdTypeFilesGet_wrong_type_BadRequest():
    """Test for getting files when an invalid type is specified."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )

    with app.app_context():
        with pytest.raises(BadRequest):
            toolsIdVersionsVersionIdTypeFilesGet.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
                type='foo'
            )


# GET /tools/{id}/versions/{version_id}/{type}/tests
def test_toolsIdVersionsVersionIdTypeTestsGet():
    """Test for getting list of test JSONs associated with a specific tool
    version identified by the given tool and version identifiers for the given
    input `type`.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = toolsIdVersionsVersionIdTypeTestsGet.__wrapped__(
                type='CWL',
                id=MOCK_ID,
                version_id=MOCK_ID,
            )
        assert res == [MOCK_TEST_FILE["file_wrapper"]]


def test_toolsIdVersionsVersionIdTypeTestsGet_tool_na_NotFound():
    """Test for getting list of test JSONs associated with a specific tool
    version identified by the given tool and version identifiers for the given
    input `type` with specified tool identifier not present.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeTestsGet.__wrapped__(
                type='CWL',
                id=MOCK_ID + MOCK_ID,
                version_id=MOCK_ID,
            )


def test_toolsIdVersionsVersionIdTypeTestsGet_version_na_NotFound():
    """Test for getting list of test JSONs associated with a specific tool
    version identified by the given tool and version identifiers for the given
    input `type` with specified tool version identifier not present.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeTestsGet.__wrapped__(
                type='CWL',
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
            )


def test_toolsIdVersionsVersionIdTypeTestsGet_type_NotFound():
    """Test for getting list of test JSONs associated with a specific tool
    version identified by the given tool and version identifiers for the given
    input `type` when no test files are available for the specified descriptor
    type.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'] \
        .collections['tools'].client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            toolsIdVersionsVersionIdTypeTestsGet.__wrapped__(
                type='WDL',
                id=MOCK_ID,
                version_id=MOCK_ID,
            )


# GET /service-info
def test_getServiceInfo():
    """Test for getting service info."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(SERVICE_INFO_CONFIG)
    app.config.foca.db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['service_info'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = getServiceInfo.__wrapped__()
        assert res == SERVICE_INFO_CONFIG


# POST /service-info
def test_postServiceInfo():
    """Test for creating service info."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    app.config.foca.db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(SERVICE_INFO_CONFIG)):
        postServiceInfo.__wrapped__()
        res = getServiceInfo.__wrapped__()
        assert res == SERVICE_INFO_CONFIG


# POST /tools
def test_postTool():
    """Test for creating a tool; identifier assigned by implementation."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = postTool.__wrapped__()
        assert isinstance(res, str)


# PUT /tools/{id}
def test_putTool():
    """Test for creating a tool; identifier provided by user."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = putTool.__wrapped__(id=MOCK_ID)
        assert res == MOCK_ID


def test_putTool_update():
    """Test for updating an existing tool."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = {}
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_TOOL_VERSION_ID)):
        res = putTool.__wrapped__(id=MOCK_ID)
        assert res == MOCK_ID


# DELETE /tools/{id}
def test_deleteTool():
    """Test for deleting a tool."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        res = deleteTool.__wrapped__(id=MOCK_ID)
        assert res == MOCK_ID


def test_deleteTool_NotFound():
    """Test `DELETE /tools/{id}` endpoint with unavailable id."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = {}
    mock_resp["id"] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.test_request_context(json=deepcopy(MOCK_VERSION_ID)):
        res = postToolVersion.__wrapped__(id=MOCK_ID)
        assert isinstance(res, str)


# PUT /tools/{id}/versions/{version_id}
def test_putToolVersion():
    """Test for creating a tool version; identifier provided by user."""
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = {}
    mock_resp["id"] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = MOCK_TOOL_VERSION_ID
    mock_resp["id"] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'].append(deepcopy(MOCK_VERSION_ID))
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp)

    with app.app_context():
        with pytest.raises(NotFound):
            deleteToolVersion.__wrapped__(
                id=MOCK_ID,
                version_id=MOCK_ID + MOCK_ID,
            )


def test_deleteToolVersion_InternalServerError(monkeypatch):
    """Test for deleting a version `version_id` of a tool associated with a
    given `id` when the deletion was incomplete (either only the tool or only
    the associated files were deleted).
    """
    class MongoMockResponse:
        def __init__(self, matched_count, modified_count):
            self.matched_count = matched_count
            self.modified_count = modified_count

    mock_response = MongoMockResponse(matched_count=1, modified_count=0)
    monkeypatch.setattr(
        'mongomock.collection.Collection.update_one',
        lambda *args, **kwargs: mock_response
    )
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp['id'] = MOCK_ID
    mock_resp['versions'].append(deepcopy(MOCK_VERSION_ID))
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG)
    )
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG)
    )
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG)
    )
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
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
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    with app.test_request_context():
        res = deleteToolClass.__wrapped__(
            id=MOCK_ID,
        )
        assert res == MOCK_ID


def test_deleteToolClass_NotFound():
    """Test for deleting a tool associated with a given tool `id` when a tool
    class with the specified `id` is not available.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp = deepcopy(MOCK_TOOL_CLASS)
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp)

    with app.test_request_context():
        with pytest.raises(NotFound):
            deleteToolClass.__wrapped__(
                id=MOCK_ID + MOCK_ID,
            )


def test_deleteToolClass_BadRequest():
    """Test for deleting a tool class associated with a given `id` when a tool
    associated with this tool class exists.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        db=MongoConfig(**MONGO_CONFIG),
        custom=CustomConfig(**CUSTOM_CONFIG),
    )
    mock_resp_tools = deepcopy(MOCK_TOOL_VERSION_ID)
    mock_resp_classes = deepcopy(MOCK_TOOL_CLASS)
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client = mongomock.MongoClient().db.collection
    app.config.foca.db.dbs['trsStore'].collections['tools'] \
        .client.insert_one(mock_resp_tools)
    app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
        .client.insert_one(mock_resp_classes)

    with app.test_request_context():
        with pytest.raises(BadRequest):
            deleteToolClass.__wrapped__(
                id=MOCK_ID,
            )
