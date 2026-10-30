"""Tests of the shared fixtures (`tests/conftest.py`)."""

import os
import socket
from typing import Any

import mongomock
from pymongo import MongoClient
import pytest

from tests import conftest
from trs_filer.utils import DB


def test_db_client(db_client: MongoClient[dict[str, Any]]) -> None:
    """Tests use MongoDB at `MONGODB_TEST_URI` if it is set, else mongomock.

    Args:
        db_client: MongoDB client of the test.
    """
    uri = os.environ.get("MONGODB_TEST_URI")
    assert isinstance(db_client, mongomock.MongoClient) is not bool(uri)
    if uri:
        assert db_client.server_info()["version"]
    assert isinstance(db_client[DB]["tools"], conftest.COLLECTION_CLASS)


@pytest.mark.parametrize("run", [1, 2])
def test_db_client_empty(db_client: MongoClient[dict[str, Any]], run: int) -> None:
    """Each test starts with an empty database `DB`.

    Args:
        db_client: MongoDB client of the test.
        run: Number of the run.
    """
    tools = db_client[DB]["tools"]
    assert tools.count_documents({}) == 0
    tools.insert_one({"id": f"run{run}"})


def test_check_no_db() -> None:
    """MongoDBs with database `DB` are refused, as the tests would drop it."""
    client: MongoClient[dict[str, Any]] = mongomock.MongoClient()
    client["other"]["tools"].insert_one({"id": "other"})
    conftest._check_no_db(client)
    client[DB]["tools"].insert_one({"id": "deployed"})
    with pytest.raises(pytest.exit.Exception, match=f"has a database '{DB}'"):
        conftest._check_no_db(client)


def test_db_addresses() -> None:
    """The addresses of a URI's hosts are resolved; default port 27017."""
    assert conftest._db_addresses("") == frozenset()
    assert conftest._db_addresses(
        "mongodb://127.0.0.1:12345,127.0.0.2/?replicaSet=rs"
    ) == {
        ("127.0.0.1", 12345),
        ("127.0.0.2", 27017),
    }


def test_no_network() -> None:
    """Connections other than to the test database are blocked in tests."""
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(OSError, match="Network access blocked in tests"),
    ):
        sock.connect(("192.0.2.1", 443))
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(OSError, match="Network access blocked in tests"),
    ):
        sock.connect_ex(("192.0.2.1", 443))


def test_no_network_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connections to the test database are passed on.

    Args:
        monkeypatch: Patches of the test database's addresses and of the
            original `socket.socket.connect()`.
    """
    calls: list[object] = []
    monkeypatch.setattr(conftest, "DB_ADDRESSES", frozenset({("127.0.0.1", 12345)}))
    monkeypatch.setattr(
        conftest, "_CONNECT", lambda sock, address: calls.append(address)
    )
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        conftest._no_network(sock, ("127.0.0.1", 12345))
        assert conftest._no_network_ex(sock, ("127.0.0.1", 12345)) == 0
        with pytest.raises(OSError, match="Network access blocked in tests"):
            conftest._no_network(sock, ("127.0.0.1", 12346))
        with pytest.raises(OSError, match="Network access blocked in tests"):
            conftest._no_network(sock, "/tmp/socket")  # noqa: S108 (not created)
    assert calls == [("127.0.0.1", 12345)] * 2


def test_no_database_name() -> None:
    """`MONGO_DBNAME` is unset in tests, so that apps use database `DB`."""
    assert "MONGO_DBNAME" not in os.environ
