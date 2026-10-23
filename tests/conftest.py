"""Shared fixtures.

The app is created from `trs_filer/config.yaml`, with an in-memory database
(mongomock) instead of MongoDB.
"""

from pathlib import Path

from connexion import App
from flask.testing import FlaskClient
from foca.database import register_mongodb
import mongomock
import pytest

from trs_filer.app import create_app


@pytest.fixture
def mongo_client(monkeypatch: pytest.MonkeyPatch) -> mongomock.MongoClient:
    """In-memory MongoDB client, used by all apps created in a test.

    Args:
        monkeypatch: Patches of FOCA's MongoDB client.

    Returns:
        MongoDB client.
    """
    client: mongomock.MongoClient = mongomock.MongoClient()
    monkeypatch.setattr(
        register_mongodb, "MongoClient", lambda *args, **kwargs: client
    )
    return client


@pytest.fixture
def overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Config overlay merged into `config.yaml` by apps created in a test.

    Empty, unless the test writes to it.

    Args:
        tmp_path: Temporary directory.
        monkeypatch: Patches of environment variable `FOCA_CONFIG_OVERLAY`.

    Returns:
        Path of the overlay.
    """
    path = tmp_path / "overlay.yaml"
    path.write_text("{}\n")
    monkeypatch.setenv("FOCA_CONFIG_OVERLAY", str(path))
    return path


@pytest.fixture
def app(
    mongo_client: mongomock.MongoClient,
    overlay: Path,
) -> App:
    """App created from `config.yaml` and the overlay.

    Args:
        mongo_client: In-memory MongoDB client.
        overlay: Config overlay.

    Returns:
        FOCA app.
    """
    return create_app()


@pytest.fixture
def client(app: App) -> FlaskClient:
    """Test client of the app.

    Args:
        app: FOCA app.

    Returns:
        Test client.
    """
    return app.app.test_client()
