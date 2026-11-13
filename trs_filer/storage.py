"""Storage of the content of files in S3-compatible object storage (optional).

By default, the content of files is stored in MongoDB, with the other data of
tools (`file_wrapper.content` of the files of versions). With
`custom.storage.backend: s3`, the content of files registered from then on is
stored as objects in a bucket of S3-compatible object storage instead, via
the S3 API only (boto3), and MongoDB keeps their metadata: each file of a
version records its object (field `_storage`, see `STORAGE_FIELD`), with the
object's key, the SHA-256 checksum and the size of its content, which are
checked when the content is read.

Objects are written once, under random keys, when a version is registered,
and never changed. Objects that no stored file refers to any more (of
replaced or deleted versions and tools, and of registrations that failed) are
deleted at the end of the request that released them (`releases_objects()`).

Files are served through the app, which reads their content from object
storage, or, with `custom.storage.s3.presigned_urls`, via presigned URLs of
their objects (see `served_wrapper()` and `plain_redirect()`).
"""

from collections.abc import Callable, Iterable
import functools
import hashlib
import logging
import threading
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
import uuid

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from flask import Response, current_app, g

from trs_filer.custom_config import S3StorageConfig
from trs_filer.errors.exceptions import InternalServerError
from trs_filer.utils import get_collection, get_custom_config

if TYPE_CHECKING:  # pragma: no cover
    from types_boto3_s3.client import S3Client

logger = logging.getLogger(__name__)

# Internal field of the files of stored versions that refers to the object
# with the file's content (not part of TRS, and not served): `key`, `sha256`
# (hex) and `size` (bytes) of the content
STORAGE_FIELD = "_storage"
# Path of the keys of objects in stored tools
KEY_PATH = f"versions.files.{STORAGE_FIELD}.key"
# Key of the store in `Flask.extensions`
EXTENSION = "trs_filer.storage"
# Attribute of `flask.g` with the keys of the objects written in a request
NEW_KEYS = "trs_filer_new_object_keys"
# Media type of objects (file contents are text)
CONTENT_TYPE = "text/plain; charset=utf-8"

P = ParamSpec("P")
R = TypeVar("R")

_lock = threading.Lock()


class FileStore:
    """Store of file contents in a bucket of S3-compatible object storage.

    Args:
        config: Connection to object storage.
        client: S3 client; created from `config` if not given (credentials
            from the environment, via boto3's default credential chain).

    Attributes:
        config: Connection to object storage.
        client: S3 client.
    """

    def __init__(
        self,
        config: S3StorageConfig,
        client: "S3Client | None" = None,
    ) -> None:
        """Initialize the store."""
        self.config = config
        if client is None:
            client = boto3.session.Session().client(
                "s3",
                endpoint_url=config.endpoint_url,
                region_name=config.region,
                config=BotoConfig(
                    connect_timeout=config.connect_timeout,
                    read_timeout=config.read_timeout,
                    retries={"mode": "standard", "max_attempts": 3},
                    # Signature Version 4, also for presigned URLs (boto3 may
                    # presign with the deprecated version 2)
                    signature_version="s3v4",
                    s3={"addressing_style": config.addressing_style},
                    # Checksums only where the S3 API requires them, as many
                    # S3-compatible servers don't support those that boto3
                    # adds by default; contents are checked by the app
                    request_checksum_calculation="when_required",
                    response_checksum_validation="when_required",
                ),
            )
        self.client: S3Client = client

    def put(self, content: bytes) -> dict[str, Any]:
        """Store content as a new object.

        Args:
            content: Content of a file.

        Returns:
            Reference to the object: its `key`, and the `sha256` checksum
            (hex) and `size` (bytes) of the content.

        Raises:
            InternalServerError: The object could not be stored.
        """
        key = f"{self.config.prefix}{uuid.uuid4().hex}"
        try:
            self.client.put_object(
                Bucket=self.config.bucket,
                Key=key,
                Body=content,
                ContentType=CONTENT_TYPE,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("Object '%s' could not be stored: %s", key, exc)
            raise InternalServerError from exc
        return {
            "key": key,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }

    def get(self, ref: dict[str, Any]) -> bytes:
        """Get the content of an object, checked against its reference.

        Args:
            ref: Reference to the object (cf. `put()`).

        Returns:
            Content of the object.

        Raises:
            InternalServerError: The object could not be read, or its content
                doesn't match the size or checksum of the reference.
        """
        key = ref["key"]
        try:
            response = self.client.get_object(Bucket=self.config.bucket, Key=key)
            # At most one byte more than expected, to detect larger objects
            # without reading them
            content = response["Body"].read(int(ref["size"]) + 1)
        except (BotoCoreError, ClientError) as exc:
            logger.error("Object '%s' could not be read: %s", key, exc)
            raise InternalServerError from exc
        if (
            len(content) != ref["size"]
            or hashlib.sha256(content).hexdigest() != ref["sha256"]
        ):
            logger.error("Object '%s' doesn't match its checksum or size.", key)
            raise InternalServerError
        return content

    def delete(self, keys: Iterable[str]) -> None:
        """Delete objects; failures are logged, not raised.

        One request per object, as `DeleteObjects` requires checksums that
        some S3-compatible servers don't support.

        Args:
            keys: Keys of the objects.
        """
        for key in sorted(keys):
            try:
                self.client.delete_object(Bucket=self.config.bucket, Key=key)
            except (BotoCoreError, ClientError) as exc:
                logger.error("Object '%s' could not be deleted: %s", key, exc)
            else:
                logger.debug("Deleted object '%s'.", key)

    def presigned_url(self, key: str) -> str:
        """Get a presigned URL to read an object.

        The URL is valid for `presigned_url_expiry` seconds; responses are
        `text/plain`, as when files are served through the app.

        Args:
            key: Key of the object.

        Returns:
            Presigned URL.

        Raises:
            InternalServerError: The URL could not be created (e.g., without
                credentials).
        """
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.config.bucket,
                    "Key": key,
                    "ResponseContentType": CONTENT_TYPE,
                },
                ExpiresIn=self.config.presigned_url_expiry,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.error("No presigned URL for object '%s': %s", key, exc)
            raise InternalServerError from exc


def get_file_store() -> FileStore | None:
    """Get the store of file contents of the current app.

    Created once per app (and process) on first use.

    Returns:
        Store of file contents, or `None` if object storage is not configured
        (`custom.storage.s3`).
    """
    config = get_custom_config().storage.s3
    if config is None:
        return None
    store: FileStore | None = current_app.extensions.get(EXTENSION)
    if store is None:
        with _lock:
            store = current_app.extensions.get(EXTENSION)
            if store is None:
                store = FileStore(config)
                current_app.extensions[EXTENSION] = store
    return store


def store_file(entry: dict[str, Any]) -> None:
    """Store the content of a file of a version to be registered.

    With backend `s3`, the content (`file_wrapper.content`) is stored as an
    object and replaced by a reference to it (`STORAGE_FIELD`); the key is
    remembered for the request (cf. `releases_objects()`). Otherwise, the
    file is left as it is.

    Args:
        entry: File of a version (`tool_file`, `file_wrapper`, `type`), with
            its content.
    """
    # never a reference given by the client
    entry.pop(STORAGE_FIELD, None)
    if get_custom_config().storage.backend != "s3":
        return
    store = get_file_store()
    assert store is not None  # backend `s3` requires `s3` (`StorageConfig`)
    wrapper = entry["file_wrapper"]
    ref = store.put(str(wrapper["content"]).encode("utf-8"))
    new_keys: list[str] = g.setdefault(NEW_KEYS, [])
    new_keys.append(ref["key"])
    del wrapper["content"]
    entry[STORAGE_FIELD] = ref


def _store_for(entry: dict[str, Any]) -> FileStore:
    """Get the store of a file whose content is in object storage.

    Args:
        entry: File of a stored version, with a reference to its object.

    Returns:
        Store of file contents.

    Raises:
        InternalServerError: Object storage is not configured.
    """
    store = get_file_store()
    if store is None:
        logger.error(
            "Object '%s' can't be read: custom.storage.s3 is not set.",
            entry[STORAGE_FIELD]["key"],
        )
        raise InternalServerError
    return store


def file_content(entry: dict[str, Any]) -> bytes | None:
    """Get the content of a file from object storage.

    Args:
        entry: File of a stored version.

    Returns:
        Content of the file, or `None` if it is not in object storage.

    Raises:
        InternalServerError: The content could not be read, or doesn't match
            its checksum, or object storage is not configured.
    """
    if STORAGE_FIELD not in entry:
        return None
    return _store_for(entry).get(entry[STORAGE_FIELD])


def served_wrapper(entry: dict[str, Any]) -> dict[str, Any]:
    """Get the file wrapper of a file as served.

    Files in MongoDB are served as stored. For files in object storage, the
    content is read from there, or, with presigned URLs, the wrapper has the
    presigned URL of the object as `url` instead of the content, and the
    SHA-256 checksum of the content (`sha-256`), unless given already.

    Args:
        entry: File of a stored version.

    Returns:
        File wrapper.

    Raises:
        InternalServerError: The content could not be read, or doesn't match
            its checksum, or object storage is not configured.
    """
    wrapper: dict[str, Any] = entry["file_wrapper"]
    if STORAGE_FIELD not in entry:
        return wrapper
    store = _store_for(entry)
    ref = entry[STORAGE_FIELD]
    served = dict(wrapper)
    if store.config.presigned_urls:
        served["url"] = store.presigned_url(ref["key"])
        checksums = list(served.get("checksum") or [])
        if not any(c.get("type") == "sha-256" for c in checksums):
            checksums.append({"checksum": ref["sha256"], "type": "sha-256"})
        served["checksum"] = checksums
    else:
        served["content"] = store.get(ref).decode("utf-8")
    return served


def plain_redirect(entry: dict[str, Any]) -> Response | None:
    """Get the redirect to the presigned URL of a file, for plain types.

    Args:
        entry: File of a stored version.

    Returns:
        Redirect (`302 Found`) to the presigned URL of the file's object,
        or `None` if the file is not in object storage or presigned URLs
        are not enabled.

    Raises:
        InternalServerError: The URL could not be created, or object storage
            is not configured.
    """
    if STORAGE_FIELD not in entry:
        return None
    store = _store_for(entry)
    if not store.config.presigned_urls:
        return None
    return Response(
        status=302,
        headers={"Location": store.presigned_url(entry[STORAGE_FIELD]["key"])},
    )


def tool_object_keys(tool_id: str) -> set[str]:
    """Get the keys of the objects that the files of a stored tool refer to.

    Args:
        tool_id: Tool identifier.

    Returns:
        Keys of the objects.
    """
    tool = get_collection("tools").find_one(
        {"id": tool_id}, {"_id": False, "versions.files": True}
    )
    if tool is None:
        return set()
    return {
        entry[STORAGE_FIELD]["key"]
        for version in tool.get("versions", [])
        for entry in version.get("files", [])
        if STORAGE_FIELD in entry
    }


def referenced_keys(keys: set[str]) -> set[str]:
    """Get those of the given object keys that stored files refer to.

    Args:
        keys: Keys of objects.

    Returns:
        Keys that the files of stored tools refer to.
    """
    if not keys:
        return set()
    found = get_collection("tools").distinct(KEY_PATH, {KEY_PATH: {"$in": list(keys)}})
    return keys & set(found)


def releases_objects(controller: Callable[P, R]) -> Callable[P, R]:
    """Delete the objects that a write request released.

    For the controllers that write tools and versions (`id`: the tool's
    identifier, if any): after the request, successful or not, the objects of
    the tool's files before the request and those written during the request
    (`store_file()`) are deleted, unless stored files refer to them. As keys
    are random and written once, no other request can refer to them again.
    Without object storage, the controller is called as is.

    Args:
        controller: Controller.

    Returns:
        Controller that deletes released objects.
    """

    @functools.wraps(controller)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        """Call the controller, then delete released objects.

        Args:
            *args: Positional arguments of the controller.
            **kwargs: Keyword arguments of the controller.

        Returns:
            Return value of the controller.
        """
        store = get_file_store()
        if store is None:
            return controller(*args, **kwargs)
        tool_id = kwargs.get("id")
        before = tool_object_keys(tool_id) if isinstance(tool_id, str) else set()
        g.pop(NEW_KEYS, None)
        try:
            return controller(*args, **kwargs)
        finally:
            candidates = before | set(g.pop(NEW_KEYS, []))
            try:
                released = candidates - referenced_keys(candidates)
            except Exception:
                # e.g., the database is unavailable: objects are left, rather
                # than masking the outcome of the request
                logger.exception(
                    "Released objects could not be determined; %d left.",
                    len(candidates),
                )
            else:
                if released:
                    store.delete(released)

    return wrapper
