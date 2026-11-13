"""Tests of authentication and access control, with the app from its config.

The app is created from `config.yaml` and the test overlay, whose identity
provider is mocked (see `tests/conftest.py`): reads are public, writes need
an access token; who may write what is tested here for users without roles
and admins, and in `tests/test_ownership.py` for owners and maintainers.
"""

from copy import deepcopy
import logging
import os
from pathlib import Path
from typing import Any

from connexion import App
from cryptography.hazmat.primitives.asymmetric import rsa
from flask.testing import FlaskClient
from foca import get_config
from pydantic import ValidationError
from pymongo import MongoClient
from pymongo.collection import Collection
import pytest
import yaml

from tests.conftest import (
    ADMIN,
    EDITOR,
    ISSUER,
    OTHER_ADMIN,
    READER,
    USER,
    Records,
    admin_client,
    make_headers,
)
from tests.mock_data import (
    BASE_PATH,
    MOCK_TOOL,
    MOCK_TOOL_VERSION_ID,
    MOCK_VERSION_NO_ID,
)
from trs_filer.app import create_app

ROOT = Path(__file__).parents[1]
TOOL_ID = "TOOL01"
VERSION_ID = MOCK_TOOL_VERSION_ID["versions"][0]["id"]
VERSION = MOCK_VERSION_NO_ID
# A tool class that no tool has, so that it can be deleted
TOOL_CLASS_ID = "spare"
TOOL_CLASS = {"name": "Workflow", "description": "A workflow."}
# The write operations of the API: method, path and body; the tool `TOOL_ID`
# (with version `VERSION_ID` and another one), registered by an admin, and
# the tool class `TOOL_CLASS_ID` exist (cf. `_add_tool()`)
WRITES: list[tuple[str, str, Any]] = [
    ("POST", "/tools", MOCK_TOOL),
    ("PUT", f"/tools/{TOOL_ID}", MOCK_TOOL),
    ("DELETE", f"/tools/{TOOL_ID}", None),
    ("POST", f"/tools/{TOOL_ID}/versions", VERSION),
    ("PUT", f"/tools/{TOOL_ID}/versions/{VERSION_ID}", VERSION),
    ("DELETE", f"/tools/{TOOL_ID}/versions/{VERSION_ID}", None),
    ("POST", "/toolClasses", TOOL_CLASS),
    ("PUT", f"/toolClasses/{TOOL_CLASS_ID}", TOOL_CLASS),
    ("DELETE", f"/toolClasses/{TOOL_CLASS_ID}", None),
]
# The writes that any authenticated user may do: register tools and add tool
# classes, also with identifiers of no tool or tool class (cf.
# `NEW_WRITES`); the others need a role on the tool, or are for admins only
OPEN_WRITES = {("POST", "/tools"), ("POST", "/toolClasses")}
NEW_WRITES: list[tuple[str, str, Any]] = [
    ("PUT", "/tools/NEWTOOL", MOCK_TOOL),
    ("PUT", "/toolClasses/new", TOOL_CLASS),
]
# The read operations of TRS, with paths of the tool `TOOL_ID`
READS = [
    "/tools",
    f"/tools/{TOOL_ID}",
    f"/tools/{TOOL_ID}/versions",
    f"/tools/{TOOL_ID}/versions/{VERSION_ID}",
    f"/tools/{TOOL_ID}/versions/{VERSION_ID}/CWL/descriptor",
    f"/tools/{TOOL_ID}/versions/{VERSION_ID}/CWL/descriptor/path_sec_desc_cwl",
    f"/tools/{TOOL_ID}/versions/{VERSION_ID}/CWL/tests",
    f"/tools/{TOOL_ID}/versions/{VERSION_ID}/CWL/files",
    f"/tools/{TOOL_ID}/versions/{VERSION_ID}/containerfile",
    "/toolClasses",
]


def _add_tool(client: FlaskClient) -> None:
    """Register the tool `TOOL_ID` and the tool class `TOOL_CLASS_ID`.

    The tool has a second version, so that `VERSION_ID` can be deleted (the
    last version of a tool can't).

    Args:
        client: Test client, with an admin's token.
    """
    requests = [
        (f"/tools/{TOOL_ID}", "PUT", MOCK_TOOL_VERSION_ID),
        (f"/tools/{TOOL_ID}/versions", "POST", VERSION),
        (f"/toolClasses/{TOOL_CLASS_ID}", "PUT", TOOL_CLASS),
    ]
    for path, method, body in requests:
        response = client.open(f"{BASE_PATH}{path}", method=method, json=body)
        assert response.status_code == 200, response.get_json()


def _write(
    client: FlaskClient, write: tuple[str, str, Any], headers: dict[str, str]
) -> Any:
    """Send a write request.

    Args:
        client: Test client.
        write: Method, path and body (cf. `WRITES`).
        headers: Request headers.

    Returns:
        Response.
    """
    method, path, body = write
    return client.open(f"{BASE_PATH}{path}", method=method, json=body, headers=headers)


def _overlay(overlay: Path, config: dict[str, Any]) -> None:
    """Write a config overlay (after the test overlay).

    Args:
        overlay: Config overlay.
        config: Its content.
    """
    overlay.write_text(yaml.safe_dump(config))


def test_config(app: App) -> None:
    """Writes need a token of an admin; FOCA validates RFC 9068 tokens.

    Args:
        app: FOCA app.
    """
    with app.app.app_context():
        conf = get_config()
    assert conf.security.auth.verify_token_type is True
    assert conf.security.auth.allow_expired is False
    access_control = conf.security.access_control
    assert access_control.enabled is True
    assert access_control.enforce is True
    assert access_control.require_admin is True
    (spec,) = conf.api.specs
    assert spec.disable_auth is False
    assert spec.add_security_fields == {
        "x-bearerInfoFunc": "foca.security.auth.validate_token"
    }


@pytest.mark.parametrize("write", WRITES, ids=lambda w: f"{w[0]} {w[1]}")
def test_writes_need_token(
    client: FlaskClient,
    anonymous_client: FlaskClient,
    tools: Collection[dict[str, Any]],
    write: tuple[str, str, Any],
) -> None:
    """Writes without a token are refused with a Bearer challenge.

    Args:
        client: Test client, with an admin's token.
        anonymous_client: Test client without token.
        tools: Collection `tools`.
        write: Method, path and body.
    """
    _add_tool(client)
    stored = list(tools.find({}, {"_id": False}))
    response = _write(anonymous_client, write, {})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert response.get_json()["status"] == 401
    assert list(tools.find({}, {"_id": False})) == stored


@pytest.mark.parametrize(
    "write",
    [write for write in WRITES if write[:2] not in OPEN_WRITES],
    ids=lambda w: f"{w[0]} {w[1]}",
)
def test_writes_need_role(
    client: FlaskClient,
    tools: Collection[dict[str, Any]],
    toolclasses: Collection[dict[str, Any]],
    write: tuple[str, str, Any],
) -> None:
    """Changes of tools of others and of tool classes are forbidden.

    For users without a role on the tool, who aren't admins.

    Args:
        client: Test client, with an admin's token.
        tools: Collection `tools`.
        toolclasses: Collection `toolclasses`.
        write: Method, path and body.
    """
    _add_tool(client)
    stored = list(tools.find({}, {"_id": False}))
    classes = list(toolclasses.find({}, {"_id": False}))
    response = _write(client, write, make_headers(USER))
    assert response.status_code == 403
    assert response.get_json()["status"] == 403
    assert list(tools.find({}, {"_id": False})) == stored
    assert list(toolclasses.find({}, {"_id": False})) == classes


@pytest.mark.parametrize(
    "write",
    [write for write in WRITES if write[:2] in OPEN_WRITES] + NEW_WRITES,
    ids=lambda w: f"{w[0]} {w[1]}",
)
def test_writes_of_users(client: FlaskClient, write: tuple[str, str, Any]) -> None:
    """Any authenticated user may register tools and add tool classes.

    Args:
        client: Test client, with an admin's token.
        write: Method, path and body.
    """
    _add_tool(client)
    response = _write(client, write, make_headers(USER))
    assert response.status_code == 200, response.get_json()


@pytest.mark.parametrize("write", WRITES, ids=lambda w: f"{w[0]} {w[1]}")
def test_writes_of_admins(client: FlaskClient, write: tuple[str, str, Any]) -> None:
    """Admins (members of the group mapped to `admin`) may do all writes.

    Also on tools that they have no role on (registered by another admin).

    Args:
        client: Test client, with an admin's token.
        write: Method, path and body.
    """
    _add_tool(client)
    response = _write(client, write, make_headers(OTHER_ADMIN))
    assert response.status_code == 200, response.get_json()


@pytest.mark.parametrize(
    "token",
    [
        {"expired": True},
        {"issuer": "https://login.other.example.org/"},
        {"audience": "other-client"},
        # ID tokens and other JWTs are no access tokens (RFC 9068)
        {"typ": "JWT"},
        {"typ": None},
    ],
    ids=["expired", "issuer", "audience", "type JWT", "no type"],
)
def test_writes_invalid_token(
    client: FlaskClient, tools: Collection[dict[str, Any]], token: dict[str, Any]
) -> None:
    """Writes with invalid tokens of admins are refused as invalid tokens.

    Args:
        client: Test client, with an admin's token.
        tools: Collection `tools`.
        token: Arguments of `make_token()`.
    """
    response = client.post(
        f"{BASE_PATH}/tools", json=MOCK_TOOL, headers=make_headers(ADMIN, **token)
    )
    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["WWW-Authenticate"]
    assert tools.count_documents({}) == 0


def test_writes_wrong_key(
    client: FlaskClient, tools: Collection[dict[str, Any]]
) -> None:
    """Writes with tokens that the issuer didn't sign are refused.

    Args:
        client: Test client, with an admin's token.
        tools: Collection `tools`.
    """
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = client.post(
        f"{BASE_PATH}/tools", json=MOCK_TOOL, headers=make_headers(ADMIN, key=other)
    )
    assert response.status_code == 401
    assert tools.count_documents({}) == 0


@pytest.mark.parametrize("path", READS)
def test_reads_public(
    client: FlaskClient, anonymous_client: FlaskClient, path: str
) -> None:
    """Reads are public, also with tokens of users who aren't admins.

    Args:
        client: Test client, with an admin's token.
        anonymous_client: Test client without token.
        path: Path of the read.
    """
    _add_tool(client)
    assert anonymous_client.get(f"{BASE_PATH}{path}").status_code == 200
    response = anonymous_client.get(f"{BASE_PATH}{path}", headers=make_headers(USER))
    assert response.status_code == 200


def test_service_info_public(anonymous_client: FlaskClient) -> None:
    """The service info, the specification and the Swagger UI are public.

    Args:
        anonymous_client: Test client without token.
    """
    for path in ("/service-info", "/openapi.json", "/ui/"):
        assert anonymous_client.get(f"{BASE_PATH}{path}").status_code == 200, path


def _login_for_reads(overlay: Path) -> None:
    """Apply the shipped patch that requires login for reads.

    Args:
        overlay: Config overlay.
    """
    _overlay(
        overlay,
        {"api": {"specs": {"trs": {"patches": ["api/patches/login-for-reads.yaml"]}}}},
    )


def test_login_for_reads(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With the shipped patch, reads need a token of any user.

    The service info, the specification and the Swagger UI stay public.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _login_for_reads(overlay)
    app = create_app()
    _add_tool(admin_client(app))
    anonymous = app.app.test_client()
    for path in READS:
        response = anonymous.get(f"{BASE_PATH}{path}")
        assert response.status_code == 401, path
        assert response.headers["WWW-Authenticate"].startswith("Bearer")
        response = anonymous.get(f"{BASE_PATH}{path}", headers=make_headers(USER))
        assert response.status_code == 200, path
        # The rules' "GET|HEAD" is matched as `^(GET|HEAD)$` (model.conf)
        assert anonymous.head(f"{BASE_PATH}{path}").status_code == 401, path
        response = anonymous.head(f"{BASE_PATH}{path}", headers=make_headers(USER))
        assert response.status_code == 200, path
    for path in ("/service-info", "/openapi.json", "/ui/"):
        assert anonymous.get(f"{BASE_PATH}{path}").status_code == 200, path


def test_login_for_reads_patch_covers_reads() -> None:
    """The shipped patch covers each read operation of TRS, and only these.

    Checked against the served paths in `test_login_for_reads()`; here
    against the patch itself, so that new reads aren't missed.
    """
    patch = yaml.safe_load(
        (ROOT / "trs_filer" / "api" / "patches" / "login-for-reads.yaml").read_text()
    )
    additions = yaml.safe_load(
        (ROOT / "trs_filer" / "api" / "additions.openapi.yaml").read_text()
    )
    public = {
        path
        for path, item in additions["paths"].items()
        if item.get("get", {}).get("security") == [] and path != "/service-info"
    }
    assert set(patch["paths"]) == public
    for item in patch["paths"].values():
        assert item == {"get": {"security": [{"BEARER": []}]}}


def test_login_for_reads_named_rules(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Overlays restrict reads by replacing the named rules.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(
        overlay,
        {
            "api": {
                "specs": {"trs": {"patches": ["api/patches/login-for-reads.yaml"]}}
            },
            "security": {
                "access_control": {"policies": {"get-tools": None}},
            },
        },
    )
    app = create_app()
    _add_tool(admin_client(app))
    client = app.app.test_client()
    headers = make_headers(USER)
    assert client.get(f"{BASE_PATH}/tools", headers=headers).status_code == 200
    response = client.get(f"{BASE_PATH}/tools/{TOOL_ID}", headers=headers)
    assert response.status_code == 403


def test_refuses_no_issuers(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The app refuses to start without trusted token issuers.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(overlay, {"security": {"auth": {"issuers": []}}})
    with pytest.raises(ValidationError, match="requires trusted token issuers"):
        create_app()


def test_refuses_no_audience(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The app refuses to start without an audience, unless it is not verified.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(overlay, {"security": {"auth": {"audience": None}}})
    with pytest.raises(ValidationError, match="require an audience"):
        create_app()
    _overlay(
        overlay,
        {"security": {"auth": {"audience": None, "verify_audience": False}}},
    )
    create_app()


def test_refuses_no_admins(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The app refuses to start without admin groups, unless admins are optional.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(overlay, {"security": {"access_control": {"group_mapping": None}}})
    with pytest.raises(ValueError, match="require_admin' is set"):
        create_app()
    _overlay(
        overlay,
        {
            "security": {
                "access_control": {"group_mapping": None, "require_admin": False}
            }
        },
    )
    create_app()


def test_clients_allowlist(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With `security.auth.clients`, only tokens of these clients may write.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(overlay, {"security": {"auth": {"clients": ["portal"]}}})
    app = create_app()
    client = app.app.test_client()
    write = ("POST", "/tools", MOCK_TOOL)
    assert _write(client, write, make_headers(client="portal")).status_code == 200
    assert _write(client, write, make_headers(client="other")).status_code == 401
    assert _write(client, write, make_headers()).status_code == 401


def test_refuses_service_clients(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """The app refuses to start with service clients, which it doesn't support.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(
        overlay,
        {
            "security": {
                "auth": {
                    "service_clients": [{"client_id": "gateway", "issuer": ISSUER}]
                }
            }
        },
    )
    with pytest.raises(RuntimeError, match="Service clients are not supported"):
        create_app()


def test_dev_overlay_writes_need_token(
    mongo_client: MongoClient[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    mock_idp: None,
) -> None:
    """The Docker Compose overlay starts the app; writes still need a token.

    It trusts a fictitious issuer and requires no admins, so writes without
    a token are refused (`401`), as the smoke test checks.

    Args:
        mongo_client: MongoDB client.
        monkeypatch: Patches of `FOCA_CONFIG_OVERLAY`.
        mock_idp: Mock of the identity provider.
    """
    monkeypatch.setenv("FOCA_CONFIG_OVERLAY", str(ROOT / "config.dev.yaml"))
    client = create_app().app.test_client()
    response = client.post(f"{BASE_PATH}/tools", json=MOCK_TOOL)
    assert response.status_code == 401
    assert client.get(f"{BASE_PATH}/tools").status_code == 200


def test_noauth_overlay(
    mongo_client: MongoClient[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    mock_idp: None,
) -> None:
    """The overlay for development without authentication opens writes.

    With `config.noauth.yaml` after the Docker Compose overlay, writes
    succeed without a token, and FOCA warns that the operations are public
    (the handler is added to FOCA's logger, as FOCA's log config replaces
    the handlers of the root logger, and with them, pytest's).

    Args:
        mongo_client: MongoDB client.
        monkeypatch: Patches of `FOCA_CONFIG_OVERLAY`.
        mock_idp: Mock of the identity provider.
    """
    monkeypatch.setenv(
        "FOCA_CONFIG_OVERLAY",
        f"{ROOT / 'config.dev.yaml'}{os.pathsep}{ROOT / 'config.noauth.yaml'}",
    )
    records = Records()
    logger = logging.getLogger("foca")
    logger.addHandler(records)
    try:
        client = create_app().app.test_client()
    finally:
        logger.removeHandler(records)
    response = client.post(f"{BASE_PATH}/tools", json=MOCK_TOOL)
    assert response.status_code == 200, response.get_json()
    tool_id = response.get_json()
    for _ in range(2):
        response = client.put(f"{BASE_PATH}/tools/{tool_id}", json=MOCK_TOOL)
        assert response.status_code == 200, response.get_json()
    assert client.delete(f"{BASE_PATH}/tools/{tool_id}").status_code == 200
    response = client.put(f"{BASE_PATH}/tools/NEWTOOL", json=MOCK_TOOL)
    assert response.status_code == 200, response.get_json()
    assert any("Authentication is disabled" in m for m in records.messages)


def test_noauth_off_by_default() -> None:
    """Authentication is only disabled by the documented overlay.

    The base config and the Docker Compose overlay keep it enabled.
    """
    for path in (ROOT / "trs_filer" / "config.yaml", ROOT / "config.dev.yaml"):
        config = yaml.safe_load(path.read_text())
        spec = config.get("api", {}).get("specs", {}).get("trs", {})
        assert spec.get("disable_auth", False) is False, path
    noauth = yaml.safe_load((ROOT / "config.noauth.yaml").read_text())
    assert noauth == {"api": {"specs": {"trs": {"disable_auth": True}}}}


def _doc_example(title: str) -> dict[str, Any]:
    """Get a YAML example of `docs/access-control.md` by its title.

    Args:
        title: Title of the code block (e.g., `editors.yaml`).

    Returns:
        The parsed example.
    """
    text = (ROOT / "docs" / "access-control.md").read_text()
    start = text.index(f'```yaml title="{title}"\n') + len(f'```yaml title="{title}"\n')
    example: dict[str, Any] = yaml.safe_load(text[start : text.index("```", start)])
    return example


def test_editors_example(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With the documented overlay for editors, they change all tools.

    But they may only add tool classes, as other users.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(overlay, _doc_example("editors.yaml"))
    app = create_app()
    client = app.app.test_client()
    headers = make_headers(EDITOR)
    for write in WRITES:
        _add_tool(admin_client(app))
        response = _write(client, write, headers)
        expected = (
            403
            if write[1].startswith("/toolClasses") and write[:2] not in OPEN_WRITES
            else 200
        )
        assert response.status_code == expected, write
    # Registering a tool with a new class creates the class
    tool = deepcopy(MOCK_TOOL)
    tool["toolclass"] = {"name": "EditorClass", "description": "New class"}
    response = client.post(f"{BASE_PATH}/tools", json=tool, headers=headers)
    assert response.status_code == 200
    classes = client.get(f"{BASE_PATH}/toolClasses").get_json()
    assert "EditorClass" in [tool_class["name"] for tool_class in classes]
    # Other users may not change the tools of others
    response = _write(client, WRITES[1], make_headers(USER))
    assert response.status_code == 403


def test_readers_example(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """With login for reads and the documented overlay, only readers read.

    Admins read, too; other users are forbidden.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    readers = _doc_example("readers.yaml")
    readers["api"] = _doc_example("overlay.yaml")["api"]
    _overlay(overlay, readers)
    app = create_app()
    _add_tool(admin_client(app))
    client = app.app.test_client()
    for path in READS:
        url = f"{BASE_PATH}{path}"
        assert client.get(url, headers=make_headers(READER)).status_code == 200
        assert client.head(url, headers=make_headers(READER)).status_code == 200
        assert client.head(url, headers=make_headers(USER)).status_code == 403
        assert client.get(url, headers=make_headers(ADMIN)).status_code == 200
        assert client.get(url, headers=make_headers(USER)).status_code == 403


def test_reads_ignore_tokens(anonymous_client: FlaskClient) -> None:
    """Public reads ignore tokens, also invalid ones.

    Args:
        anonymous_client: Test client without token.
    """
    for headers in (
        make_headers(USER, expired=True),
        {"Authorization": "Bearer not-a-token"},
    ):
        response = anonymous_client.get(f"{BASE_PATH}/tools", headers=headers)
        assert response.status_code == 200


def test_writes_authenticated_before_parsing(anonymous_client: FlaskClient) -> None:
    """Writes without a token are refused before their body is validated.

    Args:
        anonymous_client: Test client without token.
    """
    response = anonymous_client.post(
        f"{BASE_PATH}/tools",
        data="not JSON",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_permissions_api(anonymous_client: FlaskClient) -> None:
    """FOCA's permissions API is for admins only, and lists the named rules.

    Args:
        anonymous_client: Test client without token.
    """
    path = "/admin/access-control/permissions"
    assert anonymous_client.get(path).status_code == 401
    response = anonymous_client.get(path, headers=make_headers(USER))
    assert response.status_code == 403
    response = anonymous_client.get(path, headers=make_headers(ADMIN))
    assert response.status_code == 200
    rules = {tuple(rule["rule"].values()) for rule in response.get_json()["results"]}
    tool = f"{BASE_PATH}/tools/:id"
    version = f"{tool}/versions/:version_id"
    assert rules == {
        ("*", f"{BASE_PATH}/tools", "POST"),
        ("owner", tool, "(PUT)|(DELETE)"),
        ("owner", f"{tool}/versions", "POST"),
        ("owner", version, "(PUT)|(DELETE)"),
        ("owner", f"{tool}/permissions", "GET"),
        ("owner", f"{tool}/permissions/users/*", "(PUT)|(DELETE)"),
        ("owner", f"{tool}/permissions/groups/*", "(PUT)|(DELETE)"),
        ("maintainer", f"{tool}/versions", "POST"),
        ("maintainer", version, "PUT"),
        ("*", f"{BASE_PATH}/toolClasses", "POST"),
        ("*", f"{BASE_PATH}/tools", "GET|HEAD"),
        ("*", tool, "GET|HEAD"),
        ("*", f"{tool}/versions", "GET|HEAD"),
        ("*", f"{tool}/versions/*", "GET|HEAD"),
        ("*", f"{BASE_PATH}/toolClasses", "GET|HEAD"),
    }
