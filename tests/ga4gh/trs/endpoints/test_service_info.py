"""Tests for getting/setting service info."""

from copy import deepcopy
import string  # noqa: F401
import pytest

from flask import Flask
from foca.models.config import (Config, MongoConfig)
import mongomock

from tests.mock_data import (
    CUSTOM_CONFIG,
    HEADERS_SERVICE_INFO,
    MONGO_CONFIG,
    SERVICE_CONFIG,
    SERVICE_INFO_CONFIG,
)
from trs_filer.ga4gh.trs.endpoints.service_info import (
    RegisterServiceInfo,
)
from trs_filer.errors.exceptions import NotFound
from trs_filer.custom_config import CustomConfig


class TestRegisterServiceInfo:
    """Tests for `RegisterServiceInfo` class."""

    def test_init(self):
        """Test for constructing class."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )

        with app.app_context():
            service_info = RegisterServiceInfo()
            assert service_info.url_prefix == SERVICE_CONFIG['url_prefix']

    def test_get_service_info(self):
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
            service_info = RegisterServiceInfo()
            res = service_info.get_service_info()
            assert res == SERVICE_INFO_CONFIG

    def test_get_service_info_na(self):
        """Test for getting service info when service info is unavailable."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        app.config.foca.db.dbs['trsStore'].collections['service_info'] \
            .client = mongomock.MongoClient().db.collection

        with app.app_context():
            with pytest.raises(NotFound):
                RegisterServiceInfo().get_service_info()

    def test_set_service_info_from_config(self):
        """Test for setting service info from config."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        app.config.foca.db.dbs['trsStore'].collections['service_info'] \
            .client = mongomock.MongoClient().db.collection

        with app.app_context():
            service_info = RegisterServiceInfo()
            service_info.set_service_info_from_config()
            assert service_info.get_service_info() == SERVICE_INFO_CONFIG

    def test_set_service_info_from_config_skip(self):
        """Test for skipping setting service info because identical service
        info is already available.
        """
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
            service_info = RegisterServiceInfo()
            service_info.set_service_info_from_config()
            assert service_info.get_service_info() == SERVICE_INFO_CONFIG

    def test_set_service_info_from_app_context(self):
        """Test for setting service info from app context."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        app.config.foca.db.dbs['trsStore'].collections['service_info'] \
            .client = mongomock.MongoClient().db.collection

        with app.app_context():
            service_info = RegisterServiceInfo()
            service_info.set_service_info_from_app_context(
                data=SERVICE_INFO_CONFIG,
            )
            assert service_info.get_service_info() == SERVICE_INFO_CONFIG

    def test__upsert_service_info_insert(self):
        """Test for creating service info document in database."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        app.config.foca.db.dbs['trsStore'].collections['service_info'] \
            .client = mongomock.MongoClient().db.collection

        data = deepcopy(SERVICE_INFO_CONFIG)
        del data['contactUrl']
        with app.app_context():
            service_info = RegisterServiceInfo()
            service_info._upsert_service_info(data=data)
            assert service_info.get_service_info() == data
            assert service_info.get_service_info() != SERVICE_INFO_CONFIG

    def test__upsert_service_info_update(self):
        """Test for replacing service info document in database."""
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

        data = deepcopy(SERVICE_INFO_CONFIG)
        del data['contactUrl']
        with app.app_context():
            service_info = RegisterServiceInfo()
            service_info._upsert_service_info(data=data)
            assert service_info.get_service_info() == data
            assert service_info.get_service_info() != SERVICE_INFO_CONFIG

    def test__get_headers(self):
        """Test for response headers getter."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )

        with app.app_context():
            service_info = RegisterServiceInfo()
            headers = service_info._get_headers()
            assert headers == HEADERS_SERVICE_INFO
