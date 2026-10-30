"""Shared fixtures.

App tests use the app created from `trs_filer/config.yaml` (and an overlay,
empty unless a test writes to it), with requests through Flask's test client,
so that request and response validation and error handling are part of every
test. Unit tests of the registration classes use bare Flask apps
(`tests/apps.py`).

The app tests use an in-memory database (mongomock), or, if the environment
variable `MONGODB_TEST_URI` is set, the MongoDB at that URI (e.g.,
`mongodb://localhost:27017`), as in CI: there, database `trsStore` (`DB`) is
dropped before each test, so use a single-node MongoDB (only the hosts of the
URI may be connected to) without other data, one per test run. The tests
refuse to start if the database exists already.

Tests have no network access, except to the test database.
"""

from collections.abc import Iterator
import os
from pathlib import Path
import socket
from typing import Any

from connexion import App
from flask.testing import FlaskClient
from foca.database import register_mongodb
import mongomock
from mongomock.collection import Collection as MockCollection
from pymongo import MongoClient, uri_parser
from pymongo.collection import Collection
import pytest

from trs_filer.app import create_app
from trs_filer.utils import DB, get_collection

# URI of a MongoDB to test against instead of mongomock (see above)
MONGODB_TEST_URI = os.environ.get("MONGODB_TEST_URI", "")
# Class of the collections that the app tests use, e.g., to patch their
# methods
COLLECTION_CLASS: type[Collection[Any]] | type[MockCollection] = (
    Collection if MONGODB_TEST_URI else MockCollection
)
_CONNECT = socket.socket.connect


def _db_addresses(uri: str) -> frozenset[tuple[str, int]]:
    """Get the socket addresses of the hosts of a MongoDB URI.

    Args:
        uri: MongoDB connection string (`mongodb://`), or an empty string.

    Returns:
        IP address and port of each host of the URI; none for an empty string.
    """
    if not uri:
        return frozenset()
    return frozenset(
        (str(info[4][0]), port)
        for host, port in uri_parser.parse_uri(uri)["nodelist"]
        for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    )


# Addresses that the tests may connect to
DB_ADDRESSES = _db_addresses(MONGODB_TEST_URI)


def _no_network(sock: socket.socket, address: Any) -> None:
    """Replace `socket.socket.connect()`, to block network access.

    Connections to the test database (`DB_ADDRESSES`) are allowed.

    Args:
        sock: Socket to connect.
        address: Address to connect to.

    Raises:
        OSError: The address is not one of the test database.
    """
    if isinstance(address, tuple) and tuple(address[:2]) in DB_ADDRESSES:
        _CONNECT(sock, address)
        return
    raise OSError(f"Network access blocked in tests: {address}")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block network access in all tests, except to the test database.

    Args:
        monkeypatch: Patches of `socket.socket.connect()`.
    """
    monkeypatch.setattr(socket.socket, "connect", _no_network)


def _check_no_db(client: MongoClient[dict[str, Any]]) -> None:
    """Check that a MongoDB has no database `DB`, which the tests would drop.

    Ends the test run (`pytest.exit()`, as a usage error) if the database
    exists, e.g., with data of a deployment, or left by an aborted test run.

    Args:
        client: Client of the MongoDB.
    """
    if DB in client.list_database_names():
        pytest.exit(
            f"MongoDB at MONGODB_TEST_URI has a database '{DB}', which the"
            " tests would drop: use a MongoDB without it (drop it if it is"
            " left from an aborted test run)",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )


@pytest.fixture(scope="session")
def _mongodb() -> Iterator[MongoClient[dict[str, Any]] | None]:
    """Client of the MongoDB at `MONGODB_TEST_URI`, if set, for all tests.

    Ends the test run if the MongoDB has a database `DB` before the tests.

    Yields:
        The client; `None` if `MONGODB_TEST_URI` is not set.
    """
    if not MONGODB_TEST_URI:
        yield None
        return
    client: MongoClient[dict[str, Any]] = MongoClient(
        MONGODB_TEST_URI, serverSelectionTimeoutMS=5000
    )
    try:
        _check_no_db(client)
        yield client
        client.drop_database(DB)
    finally:
        client.close()


@pytest.fixture
def db_client(
    _mongodb: MongoClient[dict[str, Any]] | None,
) -> MongoClient[dict[str, Any]]:
    """MongoDB client of a test, with an empty database `DB`.

    Args:
        _mongodb: Client of the MongoDB at `MONGODB_TEST_URI`, if set.

    Returns:
        The MongoDB at `MONGODB_TEST_URI` if set, otherwise a new in-memory
        one.
    """
    if _mongodb is None:
        client: MongoClient[dict[str, Any]] = mongomock.MongoClient()
        return client
    _mongodb.drop_database(DB)
    return _mongodb


@pytest.fixture
def mongo_client(
    monkeypatch: pytest.MonkeyPatch,
    db_client: MongoClient[dict[str, Any]],
) -> MongoClient[dict[str, Any]]:
    """MongoDB client used by all apps created in a test (see `db_client`).

    Args:
        monkeypatch: Patches of FOCA's MongoDB client.
        db_client: MongoDB client of the test.

    Returns:
        MongoDB client.
    """
    monkeypatch.setattr(
        register_mongodb, "MongoClient", lambda *args, **kwargs: db_client
    )
    return db_client


@pytest.fixture
def overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
) -> App:
    """App created from `config.yaml` and the overlay.

    Args:
        mongo_client: MongoDB client.
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


@pytest.fixture
def tools(app: App) -> Collection[dict[str, Any]]:
    """Collection `tools` of the app.

    Args:
        app: FOCA app.

    Returns:
        The collection.
    """
    with app.app.app_context():
        return get_collection("tools")


@pytest.fixture
def toolclasses(app: App) -> Collection[dict[str, Any]]:
    """Collection `toolclasses` of the app.

    Args:
        app: FOCA app.

    Returns:
        The collection.
    """
    with app.app.app_context():
        return get_collection("toolclasses")
