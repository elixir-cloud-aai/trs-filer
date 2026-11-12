"""Tests of the app created from `config.yaml`, with FOCA 0.22."""

from collections.abc import Callable
from copy import deepcopy
import hashlib
from importlib import import_module
from importlib.metadata import version
import inspect
import json
import logging
from pathlib import Path
import re
from typing import Any

from connexion import App
from flask.testing import FlaskClient
from foca import get_config
from foca.api.service_info import getServiceInfo
from pymongo import MongoClient
import pytest
import yaml

from tests.mock_data import BASE_PATH, MOCK_TOOL
from trs_filer.app import create_app, main
from trs_filer.custom_config import CustomConfig
from trs_filer.ga4gh.trs import server
from trs_filer.utils import DB, get_collection, get_custom_config


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
        "version": "2.0.2",
    }
    assert service_info["organization"] == {
        "name": "Example Organization",
        "url": "https://example.org",
    }


def test_service_info_not_writable(
    client: FlaskClient, mongo_client: MongoClient[dict[str, Any]]
) -> None:
    """The service info can't be changed via the API, and is not stored.

    Args:
        client: Test client.
        mongo_client: MongoDB client.
    """
    response = client.post(
        f"{BASE_PATH}/service-info", json={"id": "org.example.other"}
    )
    assert response.status_code == 405
    assert client.get(f"{BASE_PATH}/service-info").get_json()["id"] == (
        "org.example.trs-filer"
    )
    for db_name in mongo_client.list_database_names():
        assert "service_info" not in (mongo_client[db_name].list_collection_names())


class _Records(logging.Handler):
    """Log handler keeping the logger names and messages of its records."""

    def __init__(self) -> None:
        """Initialize the handler without records."""
        super().__init__(level=logging.WARNING)
        self.records: list[tuple[str, str]] = []

    @property
    def messages(self) -> list[str]:
        """The messages of the records, in order."""
        return [message for _, message in self.records]

    def emit(self, record: logging.LogRecord) -> None:
        """Keep the logger name and message of a record.

        Args:
            record: Log record.
        """
        self.records.append((record.name, record.getMessage()))


def test_placeholder_warning(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
) -> None:
    """The app warns once of placeholders of the service info, unless replaced.

    FOCA warns of values in reserved example domains (RFC 2606), as the
    placeholders of `config.yaml` are; the app adds no warning of its own.
    The handler is added to the loggers of FOCA's check and of the app, as
    FOCA's log config replaces the handlers of the root logger (and with
    them, pytest's).

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    records = _Records()
    loggers = [logging.getLogger(name) for name in ("foca", "trs_filer")]
    for logger in loggers:
        logger.addHandler(records)
    try:
        create_app()
        warnings = [
            (name, message)
            for name, message in records.records
            if "service info" in message
        ]
        assert [name for name, _ in warnings] == ["foca.api.service_info"]
        assert "reserved example domains" in warnings[0][1]
        assert "'id', 'organization.url'" in warnings[0][1]
        assert not [name for name, _ in records.records if name.startswith("trs_")]
        records.records.clear()
        overlay.write_text(
            "service_info:\n"
            "  service:\n"
            "    id: eu.elixir.trs\n"
            "    organization:\n"
            "      name: Other\n"
            "      url: https://trs.elixir.eu\n"
        )
        create_app()
        assert not [
            message for message in records.messages if "service info" in message
        ]
    finally:
        for logger in loggers:
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


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/service-info", None),
        ("get", "/toolClasses", None),
        ("post", "/tools", MOCK_TOOL),
        ("post", "/toolClasses", {"name": "Workflow", "description": "A workflow."}),
        # operations with parameters rejected them before FOCA 0.21, too
        ("get", "/tools", None),
        ("get", "/tools/UNKNOWN", None),
    ],
)
def test_undeclared_query_parameters(
    client: FlaskClient,
    mongo_client: MongoClient[dict[str, Any]],
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Query parameters that an operation doesn't declare are rejected (`400`).

    FOCA 0.21 checks them also on operations without parameters (request
    bodies don't count), which Connexion doesn't (`strict_validation`), as
    `docs/api.md` (Errors) says; nothing is stored.

    Args:
        client: Test client.
        mongo_client: MongoDB client.
        method: HTTP method of the operation.
        path: Path of the operation, relative to the base path.
        body: JSON body of the request, if any.
    """
    response = client.open(f"{BASE_PATH}{path}?x=1", method=method, json=deepcopy(body))
    assert response.status_code == 400, response.get_json()
    assert response.mimetype == "application/json"
    for name in ("tools", "toolclasses"):
        assert mongo_client[DB][name].count_documents({}) == 0


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/tools", {**MOCK_TOOL, "name": "Work\ud800flow"}),
        ("/toolClasses", {"name": "Work\ud800flow", "description": "A workflow."}),
    ],
    ids=["tools", "toolClasses"],
)
def test_unpaired_surrogates(
    client: FlaskClient,
    mongo_client: MongoClient[dict[str, Any]],
    path: str,
    body: dict[str, Any],
) -> None:
    """JSON bodies with unpaired surrogates are rejected (`400`).

    Such strings can't be stored; FOCA rejects them before the app sees them,
    with a `detail` that names neither the field nor the value.

    Args:
        client: Test client.
        mongo_client: MongoDB client.
        path: Path of the operation, relative to the base path.
        body: JSON body, with an unpaired surrogate in `name`.
    """
    response = client.post(
        f"{BASE_PATH}{path}",
        # escaped as `\ud800`, which JSON allows
        data=json.dumps(body),
        content_type="application/json",
    )
    assert response.status_code == 400, response.get_json()
    detail = response.get_json()["detail"]
    assert "unpaired surrogates" in detail
    for withheld in ("'name'", "Work", "flow", "ud800"):
        assert withheld not in detail
    for name in ("tools", "toolclasses"):
        assert mongo_client[DB][name].count_documents({}) == 0


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
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The app refuses to start without a size limit of request bodies.

    Args:
        mongo_client: MongoDB client.
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
            r"service_info: Extra inputs are not permitted",
        ),
        (
            "custom:\n  tool:\n    id:\n      charset: string.digits\n",
            # the app's message quotes the value, so FOCA leaves it out
            r"tool\.id\.charset: invalid value",
        ),
        (
            "custom:\n  version:\n    id:\n      charset: ''\n",
            r"version\.id\.charset: Value error",
        ),
        (
            "custom:\n  toolclass:\n    id:\n      length: 0\n",
            r"toolclass\.id\.length: Input should be greater than 0",
        ),
        (
            "custom:\n  access_control:\n    tool_classes: controlled\n",
            r"access_control\.tool_classes: Value error, only the mode 'open' "
            r"of adding tool classes is supported yet",
        ),
        (
            "custom:\n  access_control:\n    tool_classes: moderated\n",
            r"access_control\.tool_classes: Value error, only the mode 'open' "
            r"of adding tool classes is supported yet",
        ),
    ],
    ids=[
        "service-info",
        "expression",
        "empty-charset",
        "zero-length",
        "controlled",
        "moderated",
    ],
)
def test_invalid_custom_config(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    custom: str,
    reason: str,
) -> None:
    """Invalid custom configs, and those of previous versions, are rejected.

    FOCA raises a `ValueError` caused by a plain `ValueError` with the setting
    and the reason, without the input (since FOCA 0.20).

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        custom: Overlay with an invalid custom config.
        reason: Pattern of the validation error.
    """
    overlay.write_text(custom)
    with pytest.raises(ValueError, match="does not match model") as exc:
        create_app()
    cause = exc.value.__cause__
    assert type(cause) is ValueError
    assert re.search(reason, str(cause))


@pytest.mark.parametrize("name", [None, f"{DB}Name"])
def test_database_name(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str | None,
) -> None:
    """The app uses the configured database, unless `MONGO_DBNAME` is set.

    FOCA reads the environment variable itself (e.g., in Gunicorn's workers,
    which inherit the environment), as the Helm chart sets it.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        monkeypatch: Patches of environment variable `MONGO_DBNAME`.
        name: Value of `MONGO_DBNAME`; unset if `None`.
    """
    if name is None:
        monkeypatch.delenv("MONGO_DBNAME", raising=False)
    else:
        monkeypatch.setenv("MONGO_DBNAME", name)
    # Not to drop a database that existed before (with `MONGODB_TEST_URI`)
    assert name not in mongo_client.list_database_names()
    try:
        app = create_app()
        with app.app.app_context():
            assert get_collection("tools").database.name == (name or DB)
    finally:
        # The tests drop database `DB` only (with `MONGODB_TEST_URI`)
        if name is not None:
            mongo_client.drop_database(name)


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


def test_tool_classes_open(app: App, client: FlaskClient) -> None:
    """In mode `open` (the default), anybody adds tool classes.

    Tool classes are added explicitly (`POST /toolClasses`) or by registering
    a tool with a new tool class. The registration doesn't read the mode yet,
    as `open` is the only one supported; extend this test when the other
    modes are (#248).

    Args:
        app: FOCA app.
        client: Test client.
    """
    with app.app.app_context():
        assert get_custom_config().access_control.tool_classes == "open"
    tool = deepcopy(MOCK_TOOL)
    tool["toolclass"] = {"id": "newclass", "name": "New", "description": "New."}
    response = client.post(f"{BASE_PATH}/tools", json=tool)
    assert response.status_code == 200
    response = client.get(f"{BASE_PATH}/toolClasses")
    assert response.status_code == 200
    assert tool["toolclass"] in response.get_json()
    response = client.post(
        f"{BASE_PATH}/toolClasses",
        json={"name": "Explicit", "description": "Added explicitly."},
    )
    assert response.status_code == 200
    tool_class_id = response.get_json()
    response = client.get(f"{BASE_PATH}/toolClasses")
    assert tool_class_id in [item["id"] for item in response.get_json()]


# Methods of operations in OpenAPI path items
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _spec_operations(app: App) -> dict[tuple[str, str], Callable[..., Any]]:
    """Get the controllers of the operations of the app's specs.

    The operations of all files of a spec are merged, as FOCA merges them;
    the controller of an operation is the function named by its
    `operationId` in the module of its `x-openapi-router-controller` (by
    default, that of the spec's `add_operation_fields`).

    Args:
        app: FOCA app.

    Returns:
        Controllers, by method and path.
    """
    with app.app.app_context():
        specs = get_config().api.specs
    controllers: dict[tuple[str, str], Callable[..., Any]] = {}
    for spec in specs:
        operations: dict[tuple[str, str], dict[str, Any]] = {}
        paths = spec.path if isinstance(spec.path, list) else [spec.path]
        for path in paths:
            document = yaml.safe_load(Path(path).read_text())
            for route, item in document["paths"].items():
                for method, operation in item.items():
                    if method in HTTP_METHODS:
                        key = (method.upper(), route)
                        operations.setdefault(key, {}).update(operation)
        default = (spec.add_operation_fields or {})["x-openapi-router-controller"]
        for key, operation in operations.items():
            module = import_module(
                operation.get("x-openapi-router-controller", default)
            )
            controllers[key] = getattr(module, operation["operationId"])
    return controllers


def _served(app: App) -> dict[tuple[str, str], Callable[..., Any]]:
    """Get the functions serving the app's API, without their decorators.

    Args:
        app: FOCA app.

    Returns:
        Functions, by method and path (as in the specs).
    """
    served: dict[tuple[str, str], Callable[..., Any]] = {}
    for rule in app.app.url_map.iter_rules():
        if not rule.rule.startswith(f"{BASE_PATH}/"):
            continue
        route = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule.removeprefix(BASE_PATH))
        view = inspect.unwrap(app.app.view_functions[rule.endpoint])
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}:
            served[(method, route)] = view
    return served


def test_operations_resolve(app: App) -> None:
    """Every operation of the specs is served by its controller.

    The service info is served by FOCA, all other operations by
    `trs_filer.ga4gh.trs.server`.

    Args:
        app: FOCA app.
    """
    controllers = _spec_operations(app)
    served = _served(app)
    # The 19 operations of TRS and its additions, and the service info
    assert len(controllers) == 20
    assert controllers.pop(("GET", "/service-info")) is getServiceInfo
    assert {controller.__module__ for controller in controllers.values()} == {
        server.__name__
    }
    for key, controller in controllers.items():
        assert served.get(key) is inspect.unwrap(controller), key


def test_swagger_ui(client: FlaskClient) -> None:
    """The Swagger UI and the specification are served.

    Args:
        client: Test client.
    """
    assert client.get(f"{BASE_PATH}/ui/").status_code == 200
    spec = client.get(f"{BASE_PATH}/openapi.json").get_json()
    assert "post" not in spec["paths"]["/service-info"]
    assert "get" in spec["paths"]["/service-info"]


def test_spec_additions(client: FlaskClient) -> None:
    """The served specification has the app's info and extensions.

    The info is the app's, as in Cloud Registry; tools have `tags`, and the
    registration schemas reference the enums of the TRS schemas instead of
    copying them.

    Args:
        client: Test client.
    """
    spec = client.get(f"{BASE_PATH}/openapi.json").get_json()
    info = spec["info"]
    assert info["title"] == "TRS-Filer"
    assert "brought to you by ELIXIR On-Cloud" in info["description"]
    assert info["license"]["name"] == "Apache 2.0"
    assert info["contact"]["email"] == "cloud-service@elixir-europe.org"
    schemas = spec["components"]["schemas"]
    for name in ("Tool", "ToolRegister"):
        tags = schemas[name]["properties"]["tags"]
        assert tags["type"] == "array"
        assert tags["items"]["type"] == "string"
    # Commas separate the tags of the filter
    assert schemas["ToolRegister"]["properties"]["tags"]["items"]["pattern"] == (
        "^[^,]*$"
    )
    for name in ("ToolVersionRegister", "ToolVersionRegisterId"):
        properties = schemas[name]["properties"]
        assert properties["description"]["type"] == "string"
        assert properties["descriptor_type_version"] == {
            "$ref": "#/components/schemas/ToolVersion/properties/"
            "descriptor_type_version"
        }
    assert schemas["ToolFileRegister"]["properties"]["file_type"] == {
        "$ref": "#/components/schemas/ToolFile/properties/file_type"
    }
    assert "SMK" in schemas["DescriptorType"]["enum"]


# The vendored GA4GH specifications (`api.specs.trs.path`), by file name,
# with the SHA-256 checksums of the published files
VENDORED = {
    # `service-info.yaml` of ga4gh-discovery/ga4gh-service-info at 11d2c12
    "20200131.11d2c12.service-info.yaml": (
        "743c549d599d36197a06d18493f62d3c3cf6f7a242c5ebec9e341f95b10dad3b"
    ),
    # `openapi/openapi.yaml` of ga4gh/tool-registry-service-schemas at
    # 4854e2f (tag `2.0.2`)
    "20250902.4854e2f.openapi.yaml": (
        "adbe60a993bf2491675184c0564684489817ca7ce000e8f12fe32689cd1dd039"
    ),
}
# The read operations of TRS, by method and path
TRS_READS = [
    ("get", path)
    for path in (
        "/tools",
        "/tools/{id}",
        "/tools/{id}/versions",
        "/tools/{id}/versions/{version_id}",
        "/tools/{id}/versions/{version_id}/{type}/descriptor",
        "/tools/{id}/versions/{version_id}/{type}/descriptor/{relative_path}",
        "/tools/{id}/versions/{version_id}/{type}/tests",
        "/tools/{id}/versions/{version_id}/{type}/files",
        "/tools/{id}/versions/{version_id}/containerfile",
        "/toolClasses",
    )
]


def test_vendored_specs_unchanged(app: App) -> None:
    """The GA4GH specifications are vendored as published, and merged first.

    The app changes them in `additions.openapi.yaml` only, merged last, whose
    `null` values remove keys (`merge_null_removes`).

    Args:
        app: FOCA app.
    """
    with app.app.app_context():
        (spec,) = get_config().api.specs
    assert isinstance(spec.path, list)
    paths = [Path(path) for path in spec.path]
    assert [path.name for path in paths] == [*VENDORED, "additions.openapi.yaml"]
    assert spec.merge_null_removes is True
    for path in paths[:-1]:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == VENDORED[path.name]
    assert sorted(path.name for path in paths[0].parent.glob("2*")) == sorted(VENDORED)


def test_spec_security(client: FlaskClient) -> None:
    """The TRS reads and the service info are public, with a bearer scheme.

    The served specification has TRS's scheme (`BEARER`) as an HTTP bearer
    scheme only (not the API key scheme of TRS 2.0.2, nor the scheme of the
    service info specification), no security requirements of its own, and
    the path item of the service info specification for `/service-info`,
    instead of the remote reference of TRS. The registration endpoints have
    no security requirements yet.

    Args:
        client: Test client.
    """
    spec = client.get(f"{BASE_PATH}/openapi.json").get_json()
    assert spec["components"]["securitySchemes"] == {
        "BEARER": {"type": "http", "scheme": "bearer"}
    }
    assert "security" not in spec
    service_info = spec["paths"]["/service-info"]
    assert "$ref" not in service_info
    assert service_info["get"]["security"] == []
    assert service_info["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/Service"}
    for method, path in TRS_READS:
        assert spec["paths"][path][method]["security"] == [], path
    public = {*TRS_READS, ("get", "/service-info")}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS and (method, path) not in public:
                assert "security" not in operation, (method, path)
    zip_response = spec["paths"]["/tools/{id}/versions/{version_id}/{type}/files"][
        "get"
    ]["responses"]["200"]["content"]["application/zip"]["schema"]
    assert zip_response == {"type": "string", "format": "binary"}


def test_reads_public(client: FlaskClient) -> None:
    """The TRS reads are served without a token.

    Args:
        client: Test client.
    """
    assert client.get(f"{BASE_PATH}/tools").status_code == 200
    assert client.get(f"{BASE_PATH}/toolClasses").status_code == 200
    assert client.get(f"{BASE_PATH}/service-info").status_code == 200


def test_login_for_reads_patch(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """A patch can require a bearer token for a read, with TRS's scheme.

    FOCA's token validation is added to the scheme, as deployments would do;
    requests without a token are refused before the token is validated.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    overlay.write_text(
        yaml.safe_dump(
            {
                "api": {
                    "specs": {
                        "trs": {
                            "add_security_fields": {
                                "x-bearerInfoFunc": (
                                    "foca.security.auth.validate_token"
                                )
                            },
                            "patches": [
                                {
                                    "paths": {
                                        "/tools": {
                                            "get": {"security": [{"BEARER": []}]}
                                        }
                                    }
                                }
                            ],
                        }
                    }
                }
            }
        )
    )
    client = create_app().app.test_client()
    assert client.get(f"{BASE_PATH}/tools").status_code == 401
    assert client.get(f"{BASE_PATH}/toolClasses").status_code == 200


def test_no_startup_warnings(mongo_client: MongoClient[dict[str, Any]]) -> None:
    """The app starts with the base config without warnings of its spec.

    The only warning is FOCA's of the placeholders of the service info (see
    `test_placeholder_warning()`); neither FOCA nor Connexion warn of the
    specification (e.g., of security schemes, or of operations that the
    app's changes make public).

    Args:
        mongo_client: MongoDB client.
    """
    records = _Records()
    loggers = [logging.getLogger(name) for name in ("foca", "connexion", "trs_filer")]
    for logger in loggers:
        logger.addHandler(records)
    try:
        create_app()
    finally:
        for logger in loggers:
            logger.removeHandler(records)
    assert [name for name, _ in records.records] == ["foca.api.service_info"]


def test_collections(app: App) -> None:
    """The collections of the app's database are registered.

    Args:
        app: FOCA app.
    """
    with app.app.app_context():
        for name in ("tools", "toolclasses"):
            assert get_collection(name).name == name
        db = get_config().db
        assert db is not None
        assert set(db.dbs or {}) == {DB}


def test_main(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`main()` runs the app on the configured port.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        monkeypatch: Patches of the development server.
    """
    ports: list[int] = []
    monkeypatch.setattr(App, "run", lambda self, port: ports.append(port), raising=True)
    main()
    assert ports == [8080]
