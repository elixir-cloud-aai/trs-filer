"""Tests for setting tool classes."""

from copy import deepcopy
from flask import Flask
from unittest.mock import MagicMock

from foca.models.config import (Config, MongoConfig)
import mongomock
from pymongo.errors import DuplicateKeyError
import pytest

from tests.mock_data import (
    CUSTOM_CONFIG,
    CUSTOM_CONFIG_ONE_ID,
    MOCK_ID,
    MOCK_ID_ONE_CHAR,
    MOCK_TOOL_CLASS,
    MONGO_CONFIG,
)
from trs_filer.errors.exceptions import (
    InternalServerError,
)
from trs_filer.ga4gh.trs.endpoints.register_tool_classes import (
    RegisterToolClass,
)
from trs_filer.custom_config import CustomConfig


def _mock_collections(app: Flask) -> None:
    """Register in-memory collections for unregistered ones.

    FOCA 0.17's `get_collection()` refuses unregistered collections, which
    the classes look up on construction.

    Args:
        app: App whose FOCA config has the database config.
    """
    for db in app.config.foca.db.dbs.values():
        for collection in db.collections.values():
            if collection.client is None:
                collection.client = mongomock.MongoClient().db.collection


class TestRegisterToolClass:
    """Tests for `RegisterToolClass` class."""

    def test_init(self):
        """Test for constructing class."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        _mock_collections(app)

        data = deepcopy(MOCK_TOOL_CLASS)
        with app.app_context():
            tool = RegisterToolClass(data)
            assert tool.data['description'] == MOCK_TOOL_CLASS['description']
            assert tool.data['id'] is None

    def test_register_metadata(self):
        """Test for creating a tool class with a randomly assigned identifier.
        """
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        _mock_collections(app)
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()

        data = deepcopy(MOCK_TOOL_CLASS)
        with app.app_context():
            tool_class = RegisterToolClass(data=data)
            tool_class.register_metadata()
            assert isinstance(tool_class.data['id'], str)

    def test_register_metadata_with_id(self):
        """Test for creating a tool class with a user-supplied identifier."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        _mock_collections(app)
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()

        data = deepcopy(MOCK_TOOL_CLASS)
        with app.app_context():
            tool_class = RegisterToolClass(data=data, id=MOCK_ID)
            tool_class.register_metadata()
            assert isinstance(tool_class.data['id'], str)

    def test_register_metadata_with_id_replace(self):
        """Test for updating an existing tool class."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        _mock_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_CLASS)
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client = mongomock.MongoClient().db.collection
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL_CLASS)
        del data['id']
        with app.app_context():
            tool_class = RegisterToolClass(data=data, id=MOCK_ID)
            tool_class.register_metadata()
            assert isinstance(tool_class.data['id'], str)

    def test_register_metadata_duplicate_key(self):
        """Test for creating a tool class; duplicate key error occurs."""
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG),
        )
        _mock_collections(app)
        mock_resp = MagicMock(side_effect=[DuplicateKeyError(''), None])
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client = MagicMock()
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client.insert_one = mock_resp

        temp_data = deepcopy(MOCK_TOOL_CLASS)
        data = temp_data
        with app.app_context():
            tool = RegisterToolClass(data=data)
            tool.register_metadata()
            assert isinstance(tool.data['id'], str)

    def test_register_metadata_duplicate_keys_repeated(self):
        """Test for creating a tool class; running out of unique identifiers.
        """
        app = Flask(__name__)
        app.config.foca = Config(
            db=MongoConfig(**MONGO_CONFIG),
            custom=CustomConfig(**CUSTOM_CONFIG_ONE_ID),
        )
        _mock_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_CLASS)
        mock_resp["id"] = MOCK_ID_ONE_CHAR
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client = mongomock.MongoClient().db.collection
        app.config.foca.db.dbs['trsStore'].collections['toolclasses'] \
            .client.insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL_CLASS)
        del data['id']
        with app.app_context():
            with pytest.raises(InternalServerError):
                version = RegisterToolClass(data=data)
                version.register_metadata()
                version = RegisterToolClass(data=data)
                version.register_metadata()
