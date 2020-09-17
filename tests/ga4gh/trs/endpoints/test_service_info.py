"""Unit tests for `RegisterService()` controller."""

from copy import deepcopy
import string  # noqa: F401
import pytest

from flask import Flask
from foca.models.config import Config, MongoConfig
import mongomock

from tests.mock_data import (
    ENDPOINT_CONFIG,
    HEADERS_SERVICE_INFO,
    MONGO_CONFIG,
    SERVICE_INFO_CONFIG,
)
from trs_filer.ga4gh.trs.endpoints.service_info import (
    RegisterServiceInfo,
)
from trs_filer.errors.exceptions import (
    NotFound,
    ValidationError,
)


def test_get_service_info():
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
        assert RegisterServiceInfo().get_service_info() == SERVICE_INFO_CONFIG


def test_get_service_info_na():
    """Test for getting service info if unavailable."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        with pytest.raises(NotFound):
            RegisterServiceInfo().get_service_info()


def test_set_service_info_from_config():
    """Test for setting service info from config."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test_set_service_info_from_config_corrupt():
    """Test for setting service info from corrupt config."""
    app = Flask(__name__)
    mock_resp = deepcopy(ENDPOINT_CONFIG)
    del mock_resp['service_info']['id']
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=mock_resp,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        with pytest.raises(ValidationError):
            service_info = RegisterServiceInfo()
            service_info.set_service_info_from_config()


def test_set_service_info_from_config_skip():
    """Test for skipping setting service info because it is already
    available.
    """
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
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test_set_service_info_from_app_context():
    """Test for setting service info from app context."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_app_context(
            data=SERVICE_INFO_CONFIG,
        )
        assert service_info.get_service_info() == SERVICE_INFO_CONFIG


def test__upsert_service_info_insert():
    """Test for creating service info document in database."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )
    app.config['FOCA'].db.dbs['trsStore'].collections['service_info'] \
        .client = mongomock.MongoClient().db.collection

    data = deepcopy(SERVICE_INFO_CONFIG)
    del data['contactUrl']
    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info._upsert_service_info(data=data)
        assert service_info.get_service_info() == data
        assert service_info.get_service_info() != SERVICE_INFO_CONFIG


def test__upsert_service_info_update():
    """Test for replacing service info document in database."""
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

    data = deepcopy(SERVICE_INFO_CONFIG)
    del data['contactUrl']
    with app.app_context():
        service_info = RegisterServiceInfo()
        service_info._upsert_service_info(data=data)
        assert service_info.get_service_info() == data
        assert service_info.get_service_info() != SERVICE_INFO_CONFIG


def test__get_headers():
    """Test for response headers getter."""
    app = Flask(__name__)
    app.config['FOCA'] = Config(
        db=MongoConfig(**MONGO_CONFIG),
        endpoints=ENDPOINT_CONFIG,
    )

    with app.app_context():
        service_info = RegisterServiceInfo()
        headers = service_info._get_headers()
        assert headers == HEADERS_SERVICE_INFO
