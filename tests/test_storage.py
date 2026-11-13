"""Tests of the storage of file contents in S3-compatible object storage.

The tests use an in-memory S3 (moto), or, if the environment variable
`S3_TEST_ENDPOINT_URL` is set, the S3-compatible server at that URL (e.g.,
`http://localhost:8333`, as in CI), with the credentials of
`S3_TEST_ACCESS_KEY_ID` and `S3_TEST_SECRET_ACCESS_KEY` (test credentials of
that server, `test` by default). There, the bucket `BUCKET` is created for
each test and deleted afterwards, so use a server without other data.
Credentials and settings of the environment (e.g., `~/.aws`) are not used.
"""

from collections.abc import Iterator
from copy import deepcopy
import hashlib
import http.client
from io import BytesIO
import logging
import os
from pathlib import Path
import socket
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock
from urllib.parse import urlsplit
from zipfile import ZipFile

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, EndpointConnectionError
from connexion import App
from flask.testing import FlaskClient
from moto import mock_aws
import pydantic
from pymongo import MongoClient
from pymongo.collection import Collection
import pytest
from werkzeug.test import TestResponse
import yaml

from tests import conftest
from tests.conftest import Records, admin_client
from tests.mock_data import BASE_PATH, MOCK_TOOL_VERSION_ID
from trs_filer import storage
from trs_filer.app import create_app
from trs_filer.custom_config import CustomConfig, S3StorageConfig, StorageConfig
from trs_filer.errors.exceptions import InternalServerError
from trs_filer.ga4gh.trs import server
from trs_filer.storage import STORAGE_FIELD, FileStore, ObjectMissing
from trs_filer.utils import get_collection

if TYPE_CHECKING:  # pragma: no cover
    from types_boto3_s3.client import S3Client

S3_TEST_ENDPOINT_URL = os.environ.get("S3_TEST_ENDPOINT_URL", "")
BUCKET = "trs-filer-test"
REGION = "us-east-1"
TOOL_ID = "TOOL01"
TOOL_PATH = f"{BASE_PATH}/tools/{TOOL_ID}"
VERSION_ID = MOCK_TOOL_VERSION_ID["versions"][0]["id"]
VERSION_PATH = f"{TOOL_PATH}/versions/{VERSION_ID}"


def _tool() -> dict[str, Any]:
    """Get the mock tool, with distinct contents of its files.

    Returns:
        Registration payload of the tool: one version with five files, whose
        content is their path.
    """
    tool = deepcopy(MOCK_TOOL_VERSION_ID)
    for file in tool["versions"][0]["files"]:
        file["file_wrapper"]["content"] = f"content of {file['tool_file']['path']}"
    return tool


def _json(response: TestResponse) -> Any:
    """Get the JSON body of a response.

    Args:
        response: Response.

    Returns:
        JSON body.
    """
    return response.get_json()


def _content(path: str) -> str:
    """Get the content of a file of `_tool()`.

    Args:
        path: Path of the file.

    Returns:
        Content of the file.
    """
    return f"content of {path}"


def _keys(s3: "S3Client") -> set[str]:
    """Get the keys of the objects in the test bucket.

    Args:
        s3: S3 client.

    Returns:
        Keys of the objects.
    """
    response = s3.list_objects_v2(Bucket=BUCKET)
    return {obj["Key"] for obj in response.get("Contents", [])}


def _stored_keys(tools: Collection[dict[str, Any]]) -> set[str]:
    """Get the object keys that stored files refer to.

    Args:
        tools: Collection of tools.

    Returns:
        Keys of objects.
    """
    return {
        file[STORAGE_FIELD]["key"]
        for tool in tools.find()
        for version in tool.get("versions", [])
        for file in version.get("files", [])
        if STORAGE_FIELD in file
    }


def _s3_addresses(url: str) -> frozenset[tuple[str, int]]:
    """Get the socket addresses of the host of the test S3 endpoint.

    Args:
        url: Endpoint URL.

    Returns:
        IP address and port of the host.
    """
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return frozenset(
        (str(info[4][0]), port)
        for info in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    )


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator["S3Client"]:
    """S3 with the empty test bucket `BUCKET`, in memory or at the test server.

    Args:
        monkeypatch: Patches of the environment and of the allowed network
            addresses.
        tmp_path: Temporary directory, for empty AWS config files.

    Yields:
        S3 client.
    """
    # no credentials or settings of the environment
    for name in list(os.environ):
        if name.startswith("AWS_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "aws-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "aws-creds"))
    monkeypatch.setenv(
        "AWS_ACCESS_KEY_ID", os.environ.get("S3_TEST_ACCESS_KEY_ID", "test")
    )
    monkeypatch.setenv(
        "AWS_SECRET_ACCESS_KEY", os.environ.get("S3_TEST_SECRET_ACCESS_KEY", "test")
    )
    if not S3_TEST_ENDPOINT_URL:
        with mock_aws():
            client = boto3.client("s3", region_name=REGION)
            client.create_bucket(Bucket=BUCKET)
            yield client
        return
    monkeypatch.setattr(
        conftest,
        "DB_ADDRESSES",
        conftest.DB_ADDRESSES | _s3_addresses(S3_TEST_ENDPOINT_URL),
    )
    client = boto3.client(
        "s3",
        endpoint_url=S3_TEST_ENDPOINT_URL,
        region_name=REGION,
        config=BotoConfig(
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    client.create_bucket(Bucket=BUCKET)
    try:
        yield client
    finally:
        for key in _keys(client):
            client.delete_object(Bucket=BUCKET, Key=key)
        client.delete_bucket(Bucket=BUCKET)


@pytest.fixture
def records() -> Iterator[Records]:
    """Log records of `trs_filer.storage` (warnings and errors).

    Yields:
        Log handler with the records.
    """
    handler = Records()
    logger = logging.getLogger(storage.__name__)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


def _s3_config(**kwargs: Any) -> dict[str, Any]:
    """Get the settings of the test S3 (`custom.storage.s3`).

    Args:
        **kwargs: Further settings.

    Returns:
        Settings.
    """
    config: dict[str, Any] = {"bucket": BUCKET, "region": REGION, **kwargs}
    if S3_TEST_ENDPOINT_URL:
        config["endpoint_url"] = S3_TEST_ENDPOINT_URL
    return config


def _app(overlay: Path, backend: str = "s3", **kwargs: Any) -> App:
    """Create an app that stores files in the test S3.

    Args:
        overlay: Config overlay.
        backend: Storage backend.
        **kwargs: Further settings of `custom.storage.s3`.

    Returns:
        FOCA app.
    """
    overlay.write_text(
        yaml.safe_dump(
            {"custom": {"storage": {"backend": backend, "s3": _s3_config(**kwargs)}}}
        )
    )
    return create_app()


@pytest.fixture
def s3_app(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path, s3: "S3Client"
) -> App:
    """App that stores files in the test S3.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        s3: S3 client.

    Returns:
        FOCA app.
    """
    return _app(overlay)


@pytest.fixture
def s3_client(s3_app: App) -> FlaskClient:
    """Test client of `s3_app`, whose requests carry an admin's access token.

    Args:
        s3_app: FOCA app.

    Returns:
        Test client.
    """
    return admin_client(s3_app)


@pytest.fixture
def s3_tools(s3_app: App) -> Collection[dict[str, Any]]:
    """Collection `tools` of `s3_app`.

    Args:
        s3_app: FOCA app.

    Returns:
        The collection.
    """
    with s3_app.app.app_context():
        return get_collection("tools")


def _register(client: FlaskClient) -> None:
    """Register the tool of `_tool()` as `TOOL_ID`.

    Args:
        client: Test client.
    """
    response = client.put(TOOL_PATH, json=_tool())
    assert response.status_code == 200, response.text


# Config


def test_storage_config_default() -> None:
    """Files are stored in MongoDB by default."""
    config = CustomConfig.model_validate({"service": {}}).storage
    assert config == StorageConfig(backend="mongodb", s3=None)


def test_storage_config_s3_required() -> None:
    """Backend `s3` requires the connection to object storage."""
    with pytest.raises(pydantic.ValidationError, match=r"storage\.s3 must be set"):
        StorageConfig(backend="s3")


@pytest.mark.parametrize(
    "settings",
    [
        {"bucket": ""},
        {"bucket": "b", "endpoint_url": "ftp://s3.example.org"},
        {"bucket": "b", "presigned_url_expiry": 0},
        {"bucket": "b", "presigned_url_expiry": 604801},
        {"bucket": "b", "connect_timeout": float("inf")},
        {"bucket": "b", "read_timeout": 0},
        {"bucket": "b", "access_key_id": "key"},
    ],
)
def test_s3_config_invalid(settings: dict[str, Any]) -> None:
    """Invalid settings, and credentials, are rejected.

    Args:
        settings: Settings of `custom.storage.s3`.
    """
    with pytest.raises(pydantic.ValidationError):
        S3StorageConfig(**settings)


def test_s3_config_defaults() -> None:
    """The defaults suit self-hosted S3-compatible servers."""
    config = S3StorageConfig(bucket="b", endpoint_url="https://s3.example.org")
    assert config.addressing_style == "path"
    assert config.presigned_urls is False
    assert config.presigned_url_expiry == 300
    assert config.prefix == ""


def test_mongodb_backend_untouched(
    client: FlaskClient, tools: Collection[dict[str, Any]]
) -> None:
    """With the default backend, contents stay in MongoDB.

    Args:
        client: Test client (of an app with the default config).
        tools: Collection of tools.
    """
    _register(client)
    stored = tools.find_one({"id": TOOL_ID})
    assert stored is not None
    for file in stored["versions"][0]["files"]:
        assert STORAGE_FIELD not in file
        assert file["file_wrapper"]["content"] == _content(file["tool_file"]["path"])


# Writing and reading


def test_register_stores_objects(
    s3_client: FlaskClient, s3_tools: Collection[dict[str, Any]], s3: "S3Client"
) -> None:
    """Contents are stored as objects, with their checksums, not in MongoDB.

    Args:
        s3_client: Test client.
        s3_tools: Collection of tools.
        s3: S3 client.
    """
    _register(s3_client)
    stored = s3_tools.find_one({"id": TOOL_ID})
    assert stored is not None
    files = stored["versions"][0]["files"]
    assert len(files) == 5
    for file in files:
        assert "content" not in file["file_wrapper"]
        ref = file[STORAGE_FIELD]
        content = _content(file["tool_file"]["path"]).encode()
        assert ref["sha256"] == hashlib.sha256(content).hexdigest()
        assert ref["size"] == len(content)
        obj = s3.get_object(Bucket=BUCKET, Key=ref["key"])
        assert obj["Body"].read() == content
        assert obj["ContentType"] == "text/plain; charset=utf-8"
    assert _keys(s3) == _stored_keys(s3_tools)


def test_key_prefix(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path, s3: "S3Client"
) -> None:
    """Object keys start with the prefix.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        s3: S3 client.
    """
    _register(admin_client(_app(overlay, prefix="trs-filer/")))
    keys = _keys(s3)
    assert len(keys) == 5
    assert all(key.startswith("trs-filer/") for key in keys)


def test_files_served_from_objects(s3_client: FlaskClient) -> None:
    """Files are served with their contents, read from object storage.

    Args:
        s3_client: Test client.
    """
    _register(s3_client)
    response = s3_client.get(f"{VERSION_PATH}/CWL/descriptor")
    assert response.status_code == 200
    assert _json(response)["content"] == _content("path_prim_desc_cwl")
    assert _json(response)["url"] == "url"

    response = s3_client.get(f"{VERSION_PATH}/PLAIN_CWL/descriptor")
    assert response.status_code == 200
    assert response.text == _content("path_prim_desc_cwl")

    response = s3_client.get(f"{VERSION_PATH}/CWL/descriptor/path_sec_desc_cwl")
    assert response.status_code == 200
    assert _json(response)["content"] == _content("path_sec_desc_cwl")

    response = s3_client.get(f"{VERSION_PATH}/PLAIN_CWL/descriptor/path_other_cwl")
    assert response.status_code == 200
    assert response.text == _content("path_other_cwl")

    response = s3_client.get(f"{VERSION_PATH}/CWL/tests")
    assert response.status_code == 200
    assert [w["content"] for w in _json(response)] == [_content("path_test_cwl")]

    response = s3_client.get(f"{VERSION_PATH}/containerfile")
    assert response.status_code == 200
    assert [w["content"] for w in _json(response)] == [
        _content("path_container_docker")
    ]

    response = s3_client.get(f"{VERSION_PATH}/CWL/files?format=zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.data)) as zf:
        assert zf.read("path_prim_desc_cwl").decode() == _content("path_prim_desc_cwl")
        assert len(zf.namelist()) == 4


def test_presigned_urls(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    s3: "S3Client",
) -> None:
    """With presigned URLs, files are served via URLs of their objects.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        s3: S3 client.
    """
    client = admin_client(_app(overlay, presigned_urls=True, presigned_url_expiry=60))
    _register(client)
    content = _content("path_prim_desc_cwl")

    response = client.get(f"{VERSION_PATH}/CWL/descriptor")
    assert response.status_code == 200
    wrapper = _json(response)
    assert "content" not in wrapper
    assert "X-Amz-Expires=60" in wrapper["url"]
    assert {
        "checksum": hashlib.sha256(content.encode()).hexdigest(),
        "type": "sha-256",
    } in wrapper["checksum"]
    assert {"checksum": "checksum", "type": "sha1"} in wrapper["checksum"]

    response = client.get(f"{VERSION_PATH}/PLAIN_CWL/descriptor")
    assert response.status_code == 302
    url = response.headers["Location"]
    assert "X-Amz-Signature=" in url
    assert "response-content-type=text%2Fplain" in url
    if S3_TEST_ENDPOINT_URL:
        # the server serves the object at the URL, without credentials
        # (`requests` is mocked in the tests)
        parts = urlsplit(url)
        connection = http.client.HTTPConnection(str(parts.netloc), timeout=10)
        connection.request("GET", f"{parts.path}?{parts.query}")
        assert connection.getresponse().read().decode() == content
        connection.close()

    # archives are still built by the app
    response = client.get(f"{VERSION_PATH}/CWL/files?format=zip")
    assert response.status_code == 200
    with ZipFile(BytesIO(response.data)) as zf:
        assert zf.read("path_prim_desc_cwl").decode() == content


def test_presigned_sha256_given() -> None:
    """A SHA-256 checksum given on registration is not added twice."""
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://s3/presigned"
    store = FileStore(S3StorageConfig(bucket=BUCKET, presigned_urls=True), client)
    entry = {
        "file_wrapper": {"checksum": [{"checksum": "abc", "type": "sha-256"}]},
        STORAGE_FIELD: {"key": "k", "sha256": "def", "size": 1},
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(storage, "_store_for", lambda entry: store)
        wrapper = storage.served_wrapper(entry)
    assert wrapper == {
        "checksum": [{"checksum": "abc", "type": "sha-256"}],
        "url": "https://s3/presigned",
    }
    # the stored wrapper is unchanged
    assert entry["file_wrapper"] == {
        "checksum": [{"checksum": "abc", "type": "sha-256"}]
    }


# Checks of contents


@pytest.mark.parametrize("change", ["content", "missing"])
def test_changed_object_rejected(
    s3_client: FlaskClient,
    s3_tools: Collection[dict[str, Any]],
    s3: "S3Client",
    change: str,
) -> None:
    """Objects that were changed or deleted are not served.

    Args:
        s3_client: Test client.
        s3_tools: Collection of tools.
        s3: S3 client.
        change: How the object was changed.
    """
    _register(s3_client)
    stored = s3_tools.find_one({"id": TOOL_ID})
    assert stored is not None
    (file,) = (
        f
        for f in stored["versions"][0]["files"]
        if f["tool_file"]["path"] == "path_prim_desc_cwl"
    )
    key = file[STORAGE_FIELD]["key"]
    if change == "content":
        # same size, other content
        tampered = _content("path_prim_desc_cwl").upper()
        s3.put_object(Bucket=BUCKET, Key=key, Body=tampered.encode())
    else:
        s3.delete_object(Bucket=BUCKET, Key=key)
    assert s3_client.get(f"{VERSION_PATH}/CWL/descriptor").status_code == 500
    assert s3_client.get(f"{VERSION_PATH}/PLAIN_CWL/descriptor").status_code == 500
    response = s3_client.get(f"{VERSION_PATH}/CWL/files?format=zip")
    assert response.status_code == 500


@pytest.mark.parametrize(
    "path",
    [
        "CWL/descriptor",
        "PLAIN_CWL/descriptor",
        "CWL/descriptor/path_sec_desc_cwl",
        "CWL/tests",
        "containerfile",
        "CWL/files?format=zip",
    ],
)
def test_missing_object_retried(
    s3_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """Files whose object is missing once (e.g., replaced meanwhile) are read again.

    Args:
        s3_client: Test client.
        monkeypatch: Patch of `FileStore.get()`.
        path: Path of the endpoint, relative to the version.
    """
    _register(s3_client)
    get = FileStore.get
    calls: list[str] = []

    def missing_once(self: FileStore, ref: dict[str, Any]) -> bytes:
        """Raise `ObjectMissing` on the first call only.

        Args:
            self: Store.
            ref: Reference to the object.

        Returns:
            Content of the object.

        Raises:
            ObjectMissing: On the first call.
        """
        calls.append(ref["key"])
        if len(calls) == 1:
            raise ObjectMissing
        return get(self, ref)

    monkeypatch.setattr(FileStore, "get", missing_once)
    response = s3_client.get(f"{VERSION_PATH}/{path}")
    assert response.status_code == 200
    assert len(calls) >= 2


def test_storage_key_index(s3_tools: Collection[dict[str, Any]]) -> None:
    """The keys of objects are indexed, for the check of released objects.

    Args:
        s3_tools: Collection of tools.
    """
    indexes = s3_tools.index_information().values()
    assert any(
        index["key"] == [(f"versions.files.{STORAGE_FIELD}.key", 1)]
        and index.get("sparse")
        for index in indexes
    )


def test_larger_object_rejected(
    s3_client: FlaskClient, s3_tools: Collection[dict[str, Any]], s3: "S3Client"
) -> None:
    """Objects larger than recorded are not served.

    Args:
        s3_client: Test client.
        s3_tools: Collection of tools.
        s3: S3 client.
    """
    _register(s3_client)
    stored = s3_tools.find_one({"id": TOOL_ID})
    assert stored is not None
    key = stored["versions"][0]["files"][0][STORAGE_FIELD]["key"]
    s3.put_object(Bucket=BUCKET, Key=key, Body=b"x" * 1000)
    assert s3_client.get(f"{VERSION_PATH}/CWL/tests").status_code == 500


# Switching backends


def test_switch_back_to_mongodb(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    s3: "S3Client",
) -> None:
    """With backend `mongodb` and `s3` set, files in object storage are served.

    New files are stored in MongoDB again.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        s3: S3 client.
    """
    _register(admin_client(_app(overlay)))
    client = admin_client(_app(overlay, backend="mongodb"))
    response = client.get(f"{VERSION_PATH}/PLAIN_CWL/descriptor")
    assert response.text == _content("path_prim_desc_cwl")

    version = deepcopy(_tool()["versions"][0])
    del version["id"]
    response = client.put(f"{TOOL_PATH}/versions/v2", json=version)
    assert response.status_code == 200
    stored = get_collection("tools").find_one({"id": TOOL_ID})
    assert stored is not None
    assert all(STORAGE_FIELD not in f for f in stored["versions"][1]["files"])
    assert len(_keys(s3)) == 5


def test_objects_without_s3_config(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    s3: "S3Client",
    records: Records,
) -> None:
    """Files in object storage can't be served without `custom.storage.s3`.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        s3: S3 client.
        records: Log records of `trs_filer.storage`.
    """
    _register(admin_client(_app(overlay)))
    overlay.write_text("{}\n")
    client = admin_client(create_app())
    response = client.get(f"{VERSION_PATH}/CWL/descriptor")
    assert response.status_code == 500
    assert any("custom.storage.s3 is not set" in m for m in records.messages)


# Deleting objects


def test_replace_tool_deletes_old_objects(
    s3_client: FlaskClient, s3_tools: Collection[dict[str, Any]], s3: "S3Client"
) -> None:
    """Replacing a tool deletes the objects of its previous files.

    Args:
        s3_client: Test client.
        s3_tools: Collection of tools.
        s3: S3 client.
    """
    _register(s3_client)
    before = _keys(s3)
    _register(s3_client)
    after = _keys(s3)
    assert len(after) == 5
    assert not before & after
    assert after == _stored_keys(s3_tools)


def test_version_changes_delete_objects(
    s3_client: FlaskClient, s3_tools: Collection[dict[str, Any]], s3: "S3Client"
) -> None:
    """Replacing or deleting a version deletes its objects; others are kept.

    Args:
        s3_client: Test client.
        s3_tools: Collection of tools.
        s3: S3 client.
    """
    _register(s3_client)
    first = _keys(s3)
    version = deepcopy(_tool()["versions"][0])
    del version["id"]
    response = s3_client.post(f"{TOOL_PATH}/versions", json=version)
    assert response.status_code == 200
    second_id = _json(response)
    second = _keys(s3) - first
    assert len(second) == 5

    response = s3_client.put(f"{TOOL_PATH}/versions/{second_id}", json=version)
    assert response.status_code == 200
    replaced = _keys(s3) - first
    assert len(replaced) == 5
    assert not replaced & second
    assert first <= _keys(s3)

    response = s3_client.delete(f"{TOOL_PATH}/versions/{second_id}")
    assert response.status_code == 200
    assert _keys(s3) == first == _stored_keys(s3_tools)

    response = s3_client.delete(TOOL_PATH)
    assert response.status_code == 200
    assert _keys(s3) == set()


def test_failed_registration_deletes_objects(
    s3_client: FlaskClient,
    s3: "S3Client",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Objects of registrations that fail after storing them are deleted.

    Args:
        s3_client: Test client.
        s3: S3 client.
        monkeypatch: Patch of granting the owner role.
    """

    def fail(*args: Any) -> None:
        """Fail to grant the owner role.

        Args:
            *args: Arguments.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("no roles")

    monkeypatch.setattr(server, "own_tool", fail)
    response = s3_client.post(f"{BASE_PATH}/tools", json=_tool())
    assert response.status_code == 500
    assert _keys(s3) == set()


def test_invalid_version_stores_nothing(s3_client: FlaskClient, s3: "S3Client") -> None:
    """Versions with invalid files store no objects.

    Args:
        s3_client: Test client.
        s3: S3 client.
    """
    tool = _tool()
    files = tool["versions"][0]["files"]
    files.append(deepcopy(files[0]))
    response = s3_client.put(TOOL_PATH, json=tool)
    assert response.status_code == 400
    assert _keys(s3) == set()


def test_cleanup_failure_logged(
    s3_client: FlaskClient,
    s3: "S3Client",
    monkeypatch: pytest.MonkeyPatch,
    records: Records,
) -> None:
    """If released objects can't be determined, they are left, and logged.

    Args:
        s3_client: Test client.
        s3: S3 client.
        monkeypatch: Patch of `referenced_keys()`.
        records: Log records of `trs_filer.storage`.
    """

    def fail(keys: set[str]) -> set[str]:
        """Fail to read the database.

        Args:
            keys: Keys of objects.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(storage, "referenced_keys", fail)
    _register(s3_client)
    assert any("5 left" in m for m in records.messages)
    assert len(_keys(s3)) == 5


# Store


def _client_error(operation: str) -> ClientError:
    """Get an error of the S3 API.

    Args:
        operation: Name of the operation.

    Returns:
        The error.
    """
    return ClientError({"Error": {"Code": "InternalError"}}, operation)


def test_store_errors(records: Records) -> None:
    """Errors of the S3 API are internal errors, logged; deletions don't raise.

    Args:
        records: Log records of `trs_filer.storage`.
    """
    client = MagicMock()
    client.put_object.side_effect = _client_error("PutObject")
    client.get_object.side_effect = _client_error("GetObject")
    client.delete_object.side_effect = _client_error("DeleteObject")
    client.generate_presigned_url.side_effect = _client_error("GetObject")
    store = FileStore(S3StorageConfig(bucket=BUCKET), client)
    with pytest.raises(InternalServerError):
        store.put(b"content")
    with pytest.raises(InternalServerError):
        store.get({"key": "k", "sha256": "", "size": 1})
    with pytest.raises(InternalServerError):
        store.presigned_url("k")
    store.delete(["k1", "k2"])
    text = "\n".join(records.messages)
    assert "could not be stored" in text
    assert "could not be read" in text
    assert "No presigned URL" in text
    assert "'k1' could not be deleted" in text
    assert "'k2' could not be deleted" in text


def test_store_read_error(records: Records) -> None:
    """Errors of botocore (e.g., of the connection) on reads are internal errors.

    Args:
        records: Log records of `trs_filer.storage`.
    """
    client = MagicMock()
    client.get_object.side_effect = EndpointConnectionError(endpoint_url="u")
    store = FileStore(S3StorageConfig(bucket=BUCKET), client)
    with pytest.raises(InternalServerError) as info:
        store.get({"key": "k", "sha256": "", "size": 1})
    assert not isinstance(info.value, ObjectMissing)
    assert any("'k' could not be read" in m for m in records.messages)


def test_store_created_once(s3_app: App) -> None:
    """The store of an app is created once.

    Args:
        s3_app: FOCA app.
    """
    with s3_app.app.app_context():
        store = storage.get_file_store()
        assert store is not None
        assert storage.get_file_store() is store
        assert store.config.bucket == BUCKET


def test_referenced_keys_none() -> None:
    """No keys need no query."""
    assert storage.referenced_keys(set()) == set()
