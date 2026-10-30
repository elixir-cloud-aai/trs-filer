"""Bare Flask apps for the unit tests of controllers and registration classes.

The apps have the database config of `tests/mock_data.py` (`MONGO_CONFIG`)
and, optionally, a custom config; their collections have no clients until a
test gives them in-memory ones (mongomock).
"""

from typing import Any
from unittest.mock import MagicMock

from flask import Flask
from foca.config.access import get_app_config, set_app_config
from foca.models.config import CollectionConfig, Config, MongoConfig
import mongomock
from pymongo.collection import Collection

from tests.mock_data import MONGO_CONFIG
from trs_filer.custom_config import CustomConfig
from trs_filer.utils import DB


def make_app(custom: dict[str, Any] | None = None) -> Flask:
    """Create a bare Flask app with a FOCA config.

    Args:
        custom: Custom config (cf. `trs_filer.custom_config.CustomConfig`);
            none if not given.

    Returns:
        Flask app.
    """
    app = Flask(__name__)
    config: dict[str, Any] = {"db": MongoConfig(**MONGO_CONFIG)}
    if custom is not None:
        config["custom"] = CustomConfig(**custom)
    set_app_config(app, Config.model_validate(config))
    return app


def _collections(app: Flask) -> dict[str, CollectionConfig]:
    """Get the collection configs of the app's database.

    Args:
        app: Flask app (cf. :py:func:`make_app`).

    Returns:
        Collection configs, by name.
    """
    db = get_app_config(app).db
    assert db is not None
    assert db.dbs is not None
    collections = db.dbs[DB].collections
    assert collections is not None
    return collections


def mock_collection(app: Flask, name: str) -> Collection[dict[str, Any]]:
    """Give a collection of the app's database a new in-memory client.

    The collection has a unique index on `id`, as configured.

    Args:
        app: Flask app (cf. :py:func:`make_app`).
        name: Name of the collection.

    Returns:
        The client of the collection.
    """
    client: Collection[dict[str, Any]] = mongomock.MongoClient().db.collection
    # The unique index of `config.yaml` (and of `tests/mock_data.py`)
    client.create_index("id", unique=True)
    _collections(app)[name].client = client
    return client


def set_client(
    app: Flask, name: str, client: Collection[dict[str, Any]] | MagicMock
) -> None:
    """Set the client of a collection of the app's database.

    Args:
        app: Flask app (cf. :py:func:`make_app`).
        name: Name of the collection.
        client: Client, e.g., a mock.
    """
    _collections(app)[name].client = client


def mock_unset_collections(app: Flask) -> None:
    """Give the collections without clients new in-memory clients.

    FOCA 0.17's `get_collection()` refuses collections without clients, which
    the registration classes look up on construction.

    Args:
        app: Flask app (cf. :py:func:`make_app`).
    """
    for name, collection in _collections(app).items():
        if collection.client is None:
            mock_collection(app, name)


def app_collection(app: Flask, name: str) -> Collection[dict[str, Any]]:
    """Get the client of a collection of the app's database.

    Args:
        app: Flask app (cf. :py:func:`make_app`).
        name: Name of the collection.

    Returns:
        The client of the collection.
    """
    client = _collections(app)[name].client
    assert client is not None
    return client


def custom_config(app: Flask) -> CustomConfig:
    """Get the custom config of the app.

    Args:
        app: Flask app (cf. :py:func:`make_app`).

    Returns:
        Custom config.
    """
    custom = (get_app_config(app).model_extra or {}).get("custom")
    assert isinstance(custom, CustomConfig)
    return custom
