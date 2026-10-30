"""Tests for setting tool classes."""

from copy import deepcopy
from unittest.mock import MagicMock

from pymongo.errors import DuplicateKeyError
import pytest

from tests.apps import (
    app_collection,
    make_app,
    mock_collection,
    mock_unset_collections,
    set_client,
)
from tests.mock_data import (
    CUSTOM_CONFIG,
    CUSTOM_CONFIG_ONE_ID,
    MOCK_ID,
    MOCK_ID_ONE_CHAR,
    MOCK_TOOL_CLASS,
    TOOL_VERSION_CONFIG_ONE_ID,
)
from trs_filer.errors.exceptions import (
    InternalServerError,
)
from trs_filer.ga4gh.trs.endpoints.register_tool_classes import (
    RegisterToolClass,
)


class TestRegisterToolClass:
    """Tests for `RegisterToolClass` class."""

    def test_init(self) -> None:
        """Test for constructing class."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)

        data = deepcopy(MOCK_TOOL_CLASS)
        with app.app_context():
            tool = RegisterToolClass(data)
            assert tool.data["description"] == MOCK_TOOL_CLASS["description"]
            assert tool.data["id"] is None

    def test_register_metadata(self) -> None:
        """Test for creating a tool class with a randomly assigned identifier."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        set_client(app, "toolclasses", MagicMock())

        data = deepcopy(MOCK_TOOL_CLASS)
        with app.app_context():
            tool_class = RegisterToolClass(data=data)
            tool_class.register_metadata()
            assert isinstance(tool_class.data["id"], str)

    def test_register_metadata_with_id(self) -> None:
        """Test for creating a tool class with a user-supplied identifier."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        set_client(app, "toolclasses", MagicMock())

        data = deepcopy(MOCK_TOOL_CLASS)
        with app.app_context():
            tool_class = RegisterToolClass(data=data, id=MOCK_ID)
            tool_class.register_metadata()
            assert isinstance(tool_class.data["id"], str)

    def test_register_metadata_with_id_replace(self) -> None:
        """Test for updating an existing tool class."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_CLASS)
        mock_collection(app, "toolclasses")
        app_collection(app, "toolclasses").insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL_CLASS)
        del data["id"]
        with app.app_context():
            tool_class = RegisterToolClass(data=data, id=MOCK_ID)
            tool_class.register_metadata()
            assert isinstance(tool_class.data["id"], str)

    def test_register_metadata_duplicate_key(self) -> None:
        """Test for creating a tool class; duplicate key error occurs."""
        app = make_app(CUSTOM_CONFIG)
        mock_unset_collections(app)
        mock_resp = MagicMock(side_effect=[DuplicateKeyError(""), None])
        set_client(app, "toolclasses", MagicMock(insert_one=mock_resp))

        temp_data = deepcopy(MOCK_TOOL_CLASS)
        data = temp_data
        with app.app_context():
            tool = RegisterToolClass(data=data)
            tool.register_metadata()
            assert isinstance(tool.data["id"], str)

    def test_register_metadata_duplicate_keys_repeated(self) -> None:
        """Test for creating a tool class; running out of unique identifiers."""
        # `CUSTOM_CONFIG_ONE_ID` gives one identifier only to tools; tool
        # classes need their own one-identifier config
        config = deepcopy(CUSTOM_CONFIG_ONE_ID)
        config["toolclass"] = {**TOOL_VERSION_CONFIG_ONE_ID, "validation": False}
        app = make_app(config)
        mock_unset_collections(app)
        mock_resp = deepcopy(MOCK_TOOL_CLASS)
        mock_resp["id"] = MOCK_ID_ONE_CHAR
        mock_collection(app, "toolclasses")
        app_collection(app, "toolclasses").insert_one(mock_resp)

        data = deepcopy(MOCK_TOOL_CLASS)
        del data["id"]
        with app.app_context(), pytest.raises(InternalServerError):
            RegisterToolClass(data=data).register_metadata()
