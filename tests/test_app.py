"""Tests of the app created from `config.yaml`, with FOCA 0.17."""

from copy import deepcopy
from importlib.metadata import version
import logging
from pathlib import Path
import re

from connexion import App
from flask import Flask
from flask.testing import FlaskClient
from foca import get_config
from foca.models.config import Config
import mongomock
import pydantic
import pytest

from tests.mock_data import MOCK_TOOL
from trs_filer.app import create_app, main
from trs_filer.custom_config import CustomConfig, IdConfig
from trs_filer.utils import DB, get_collection, get_custom_config

BASE_PATH = "/ga4gh/trs/v2"


def test_config(app: App) -> None:
    """Debug mode is off, request bodies are limited, specs are named.

    Args:
        app: FOCA app.
    """
    with app.app.app_context():
        conf = get_config()
        custom = get_custom_config()
    assert conf.server.debug is False
    assert conf.server.max_content_length == 1048576
    assert [spec.name for spec in conf.api.specs] == ["trs"]
    assert isinstance(custom, CustomConfig)
    assert custom.tool.id.charset == "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    assert custom.service.external_host == "localhost"


def test_service_info(client: FlaskClient) -> None:
    """FOCA serves the configured service info, with the package version.

    Args:
        client: Test client.
    """
    response = client.get(f"{BASE_PATH}/service-info")
    assert response.status_code == 200
    service_info = response.get_json()
    assert service_info["id"] == "org.example.trs-filer"
    assert service_info["name"] == "TRS-Filer"
    assert service_info["version"] == version("trs-filer")
    assert service_info["type"] == {
        "group": "org.ga4gh",
        "artifact": "trs",
        "version": "2.0.1",
    }
    assert service_info["organization"] == {
        "name": "Example Organization",
        "url": "https://example.org",
    }


def test_service_info_not_writable(
    client: FlaskClient, mongo_client: mongomock.MongoClient
) -> None:
    """The service info can't be changed via the API, and is not stored.

    Args:
        client: Test client.
        mongo_client: In-memory MongoDB client.
    """
    response = client.post(
        f"{BASE_PATH}/service-info", json={"id": "org.example.other"}
    )
    assert response.status_code == 405
    assert client.get(f"{BASE_PATH}/service-info").get_json()["id"] == (
        "org.example.trs-filer"
    )
    for db_name in mongo_client.list_database_names():
        assert "service_info" not in (
            mongo_client[db_name].list_collection_names()
        )


class _Records(logging.Handler):
    """Log handler keeping the messages of its records."""

    def __init__(self) -> None:
        """Initialize the handler without messages."""
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Keep the message of a record.

        Args:
            record: Log record.
        """
        self.messages.append(record.getMessage())


def test_placeholder_warning(
    mongo_client: mongomock.MongoClient,
    overlay: Path,
) -> None:
    """The app warns of placeholders of the service info, unless replaced.

    The handler is added to the app's logger, as FOCA's log config replaces
    the handlers of the root logger (and with them, pytest's).

    Args:
        mongo_client: In-memory MongoDB client.
        overlay: Config overlay.
    """
    records = _Records()
    logger = logging.getLogger("trs_filer.app")
    logger.addHandler(records)
    try:
        create_app()
        assert len(records.messages) == 1
        assert "set `id`, `organization`" in records.messages[0]
        records.messages.clear()
        overlay.write_text(
            "service_info:\n"
            "  service:\n"
            "    id: org.example.trs\n"
            "    organization:\n"
            "      name: Other\n"
            "      url: https://trs.example.com\n"
        )
        create_app()
        assert records.messages == []
    finally:
        logger.removeHandler(records)


def test_problem_details(client: FlaskClient) -> None:
    """Errors are problem details, sent as `application/json`.

    Args:
        client: Test client.
    """
    response = client.get(f"{BASE_PATH}/tools/UNKNOWN")
    assert response.status_code == 404
    assert response.mimetype == "application/json"
    assert response.get_json() == {
        "title": "Not found",
        "status": 404,
        "detail": "The requested resource wasn't found.",
    }


def test_request_body_size_limit(client: FlaskClient) -> None:
    """Request bodies larger than 1 MiB are rejected.

    Args:
        client: Test client.
    """
    response = client.post(
        f"{BASE_PATH}/tools",
        data=b"x" * (1048576 + 1),
        content_type="application/json",
    )
    assert response.status_code == 413
    assert response.get_json()["title"] == "Content Too Large"


def test_no_request_body_size_limit(
    mongo_client: mongomock.MongoClient, overlay: Path
) -> None:
    """The app refuses to start without a size limit of request bodies.

    Args:
        mongo_client: In-memory MongoDB client.
        overlay: Config overlay.
    """
    overlay.write_text("server:\n  max_content_length: null\n")
    with pytest.raises(RuntimeError, match="max_content_length"):
        create_app()


@pytest.mark.parametrize(
    ("custom", "reason"),
    [
        (
            "custom:\n  service_info:\n    id: org.example.trs\n",
            r"service_info\s+Extra inputs are not permitted",
        ),
        (
            "custom:\n  tool:\n    id:\n      charset: string.digits\n",
            r"tool\.id\.charset\s+Value error.*expression",
        ),
        (
            "custom:\n  version:\n    id:\n      charset: ''\n",
            r"version\.id\.charset\s+Value error",
        ),
        (
            "custom:\n  toolclass:\n    id:\n      length: 0\n",
            r"toolclass\.id\.length\s+Input should be greater than 0",
        ),
    ],
    ids=["service-info", "expression", "empty-charset", "zero-length"],
)
def test_invalid_custom_config(
    mongo_client: mongomock.MongoClient,
    overlay: Path,
    custom: str,
    reason: str,
) -> None:
    """Invalid custom configs, and those of previous versions, are rejected.

    FOCA raises a `ValueError` from the model's validation error.

    Args:
        mongo_client: In-memory MongoDB client.
        overlay: Config overlay.
        custom: Overlay with an invalid custom config.
        reason: Pattern of the validation error.
    """
    overlay.write_text(custom)
    with pytest.raises(ValueError, match="does not match model") as exc:
        create_app()
    cause = exc.value.__cause__ or exc.value.__context__
    assert isinstance(cause, pydantic.ValidationError)
    assert re.search(reason, str(cause))


@pytest.mark.parametrize("name", [None, "other"])
def test_database_name(
    mongo_client: mongomock.MongoClient,
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str | None,
) -> None:
    """The app uses the configured database, unless `MONGO_DBNAME` is set.

    FOCA reads the environment variable itself (e.g., in Gunicorn's workers,
    which inherit the environment), as the Helm chart sets it.

    Args:
        mongo_client: In-memory MongoDB client.
        overlay: Config overlay.
        monkeypatch: Patches of environment variable `MONGO_DBNAME`.
        name: Value of `MONGO_DBNAME`; unset if `None`.
    """
    if name is None:
        monkeypatch.delenv("MONGO_DBNAME", raising=False)
    else:
        monkeypatch.setenv("MONGO_DBNAME", name)
    app = create_app()
    with app.app.app_context():
        assert get_collection("tools").database.name == (name or DB)


@pytest.mark.parametrize("charset", ["string.ascii_uppercase", "", 1])
def test_id_config_charset(charset: object) -> None:
    """Character sets must be non-empty strings of characters.

    Args:
        charset: Invalid character set.
    """
    with pytest.raises(pydantic.ValidationError):
        IdConfig(charset=charset)  # type: ignore[arg-type]


def test_register_tool(client: FlaskClient) -> None:
    """Tools are registered via the API, with identifiers of the config.

    Args:
        client: Test client.
    """
    response = client.post(f"{BASE_PATH}/tools", json=deepcopy(MOCK_TOOL))
    assert response.status_code == 200
    tool_id = response.get_json()
    assert len(tool_id) == 6
    assert set(tool_id) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    response = client.get(f"{BASE_PATH}/tools/{tool_id}")
    assert response.status_code == 200
    tool = response.get_json()
    assert tool["url"] == f"http://localhost:8080{BASE_PATH}/tools/{tool_id}"
    assert client.get(f"{BASE_PATH}/toolClasses").status_code == 200


def test_register_tool_class(client: FlaskClient) -> None:
    """Tool classes get identifiers of their own config (`toolclass`).

    Args:
        client: Test client.
    """
    response = client.post(
        f"{BASE_PATH}/toolClasses",
        json={"name": "Workflow", "description": "A workflow."},
    )
    assert response.status_code == 200
    tool_class_id = response.get_json()
    assert len(tool_class_id) == 6
    assert set(tool_class_id) <= set("abcdefghijklmnopqrstuvwxyz0123456789")


def test_swagger_ui(client: FlaskClient) -> None:
    """The Swagger UI and the specification are served.

    Args:
        client: Test client.
    """
    assert client.get(f"{BASE_PATH}/ui/").status_code == 200
    spec = client.get(f"{BASE_PATH}/openapi.json").get_json()
    assert "post" not in spec["paths"]["/service-info"]
    assert "get" in spec["paths"]["/service-info"]


def test_collections(app: App) -> None:
    """The collections of the app's database are registered.

    Args:
        app: FOCA app.
    """
    with app.app.app_context():
        for name in ("tools", "toolclasses"):
            assert get_collection(name).name == name
        assert set(get_config().db.dbs) == {DB}


def test_no_custom_config() -> None:
    """Apps without the custom config are refused."""
    app = Flask(__name__)
    app.config.foca = Config()
    with app.app_context():
        with pytest.raises(RuntimeError, match="No custom configuration"):
            get_custom_config()


def test_main(
    mongo_client: mongomock.MongoClient,
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`main()` runs the app on the configured port.

    Args:
        mongo_client: In-memory MongoDB client.
        overlay: Config overlay.
        monkeypatch: Patches of the development server.
    """
    ports: list[int] = []
    monkeypatch.setattr(
        App, "run", lambda self, port: ports.append(port), raising=True
    )
    main()
    assert ports == [8080]
