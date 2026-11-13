"""Tests of the modes of adding tool classes, and of pending tool classes.

The app is created from `config.yaml`, the test overlay and an overlay with
the mode (`custom.access_control.tool_classes`); its identity provider is
mocked (see `tests/conftest.py`).
"""

from copy import deepcopy
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from connexion import App
from flask.testing import FlaskClient
from pymongo import MongoClient
from pymongo.collection import Collection
import pytest

from tests.conftest import (
    ADMIN,
    COLLEAGUE,
    USER,
    admin_client,
    make_headers,
)
from tests.mock_data import BASE_PATH, MOCK_TOOL
from trs_filer.app import create_app
from trs_filer.ga4gh.trs import tool_classes
from trs_filer.ga4gh.trs.tool_classes import (
    PENDING,
    sync_pending_flags,
)
from trs_filer.utils import DB

ROOT = Path(__file__).resolve().parents[1]
TOOLS = f"{BASE_PATH}/tools"
TOOL_CLASSES = f"{BASE_PATH}/toolClasses"
APPROVALS = f"{BASE_PATH}/approvals"
UNREGISTERED = (
    "The tool class doesn't exist: use a registered one (`GET /toolClasses`), "
    "or ask an admin to add it."
)
NEW_CLASS = {"name": "New", "description": "A new tool class."}
# Another user, without a role on the tools of the tests and in no group
STRANGER = "mallory@example.org"


def _doc(collection: Collection[dict[str, Any]], id: str) -> dict[str, Any]:
    """Get a stored document by its identifier.

    Args:
        collection: Collection of the document.
        id: Identifier of the document.

    Returns:
        The document, with internal fields and without `_id`.
    """
    doc = collection.find_one({"id": id}, {"_id": False})
    assert doc is not None
    return doc


def _app(overlay: Path, mode: str) -> App:
    """Create the app with a mode of adding tool classes.

    Args:
        overlay: Config overlay.
        mode: Mode (`custom.access_control.tool_classes`).

    Returns:
        FOCA app.
    """
    overlay.write_text(f"custom:\n  access_control:\n    tool_classes: {mode}\n")
    return create_app()


def _tool(class_id: str) -> dict[str, Any]:
    """Get the mock tool with a tool class.

    Args:
        class_id: Identifier of the tool class.

    Returns:
        Tool, whose tool class has the identifier.
    """
    tool = deepcopy(MOCK_TOOL)
    tool["toolclass"] = {"id": class_id, **NEW_CLASS}
    return tool


def _register(client: FlaskClient, class_id: str, user: str = USER) -> str:
    """Register a tool with a tool class.

    Args:
        client: Test client.
        class_id: Identifier of the tool class.
        user: User registering the tool.

    Returns:
        Identifier of the tool.
    """
    response = client.post(TOOLS, json=_tool(class_id), headers=make_headers(user))
    assert response.status_code == 200, response.get_json()
    tool_id: str = response.get_json()
    return tool_id


def _class_ids(client: FlaskClient, **kwargs: Any) -> set[str]:
    """List the identifiers of the tool classes that a request lists.

    Args:
        client: Test client.
        **kwargs: Arguments of the request (e.g., `headers`).

    Returns:
        Identifiers of the listed tool classes.
    """
    response = client.get(TOOL_CLASSES, **kwargs)
    assert response.status_code == 200
    return {tool_class["id"] for tool_class in response.get_json()}


def _tool_paths(tool_id: str, version_id: str) -> list[str]:
    """Get the paths of all reads of a tool.

    Args:
        tool_id: Tool identifier.
        version_id: Identifier of a version of the tool.

    Returns:
        Paths of the tool, its versions, a version, its descriptor, a file,
        its tests, files and containerfile.
    """
    version = f"{TOOLS}/{tool_id}/versions/{version_id}"
    return [
        f"{TOOLS}/{tool_id}",
        f"{TOOLS}/{tool_id}/versions",
        version,
        f"{version}/CWL/descriptor",
        f"{version}/CWL/descriptor/path_sec_desc_cwl",
        f"{version}/CWL/tests",
        f"{version}/CWL/files",
        f"{version}/containerfile",
    ]


def _reads(client: FlaskClient, tool_id: str, version_id: str, **kwargs: Any) -> int:
    """Read a tool in every way, and count the reads that find it.

    Args:
        client: Test client.
        tool_id: Tool identifier.
        version_id: Identifier of a version of the tool.
        **kwargs: Arguments of the requests (e.g., `headers`).

    Returns:
        Number of reads that found the tool (`200`); the others must not
        (`404`). `GET /tools` counts if it lists the tool.
    """
    found = 0
    for path in _tool_paths(tool_id, version_id):
        status = client.get(path, **kwargs).status_code
        assert status in (200, 404), (path, status)
        found += status == 200
    response = client.get(TOOLS, **kwargs)
    assert response.status_code == 200
    found += tool_id in {tool["id"] for tool in response.get_json()}
    return found


def test_controlled(mongo_client: MongoClient[dict[str, Any]], overlay: Path) -> None:
    """In mode `controlled`, only admins add tool classes.

    Users other than admins can't add them explicitly, nor by registering
    tools, which must have a stored tool class; admins can, both ways.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = admin_client(_app(overlay, "controlled"))
    user = make_headers(USER)
    response = client.post(TOOL_CLASSES, json=NEW_CLASS, headers=user)
    assert response.status_code == 403
    response = client.put(f"{TOOL_CLASSES}/new", json=NEW_CLASS, headers=user)
    assert response.status_code == 403
    response = client.post(TOOLS, json=_tool("new"), headers=user)
    assert response.status_code == 400
    assert response.get_json()["detail"] == UNREGISTERED
    assert mongo_client[DB]["toolclasses"].count_documents({}) == 0
    assert mongo_client[DB]["tools"].count_documents({}) == 0
    # admins add tool classes explicitly and by registering tools
    response = client.put(f"{TOOL_CLASSES}/new", json=NEW_CLASS)
    assert response.status_code == 200
    response = client.post(TOOL_CLASSES, json=NEW_CLASS)
    assert response.status_code == 200
    _register(client, "byadmin", user=ADMIN)
    assert _class_ids(client) == {"new", "byadmin", response.get_json()}
    # users register tools with stored tool classes
    _register(client, "new")
    # replacing tool classes still needs an admin
    response = client.put(f"{TOOL_CLASSES}/new", json=NEW_CLASS, headers=user)
    assert response.status_code == 403


def test_moderated_explicit(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """In mode `moderated`, tool classes of users other than admins are pending.

    Pending tool classes are listed to admins and the user who added them,
    until an admin approves them; those of admins are approved.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    app = _app(overlay, "moderated")
    client = admin_client(app)
    anonymous = app.app.test_client()
    user = make_headers(USER)
    response = client.post(TOOL_CLASSES, json=NEW_CLASS, headers=user)
    assert response.status_code == 200
    posted = response.get_json()
    response = client.put(f"{TOOL_CLASSES}/new", json=NEW_CLASS, headers=user)
    assert response.status_code == 200
    response = client.put(f"{TOOL_CLASSES}/byadmin", json=NEW_CLASS)
    assert response.status_code == 200
    stored = mongo_client[DB]["toolclasses"].find_one({"id": "new"}, {"_id": False})
    assert stored == {"id": "new", **NEW_CLASS, "_createdBy": USER, PENDING: True}
    assert _class_ids(client) == {posted, "new", "byadmin"}
    assert _class_ids(client, headers=user) == {posted, "new", "byadmin"}
    assert _class_ids(client, headers=make_headers(COLLEAGUE)) == {"byadmin"}
    assert _class_ids(anonymous) == {"byadmin"}
    # internal fields are not served
    response = client.get(TOOL_CLASSES)
    assert {"id": "new", **NEW_CLASS} in response.get_json()
    # pending tool classes are listed as approvals
    response = client.get(APPROVALS, headers=user)
    assert response.status_code == 200
    assert response.get_json() == {
        "toolClasses": sorted(
            [{"id": posted, **NEW_CLASS}, {"id": "new", **NEW_CLASS}],
            key=lambda tool_class: tool_class["id"],
        ),
        "tools": [],
    }
    response = client.get(APPROVALS, headers=make_headers(COLLEAGUE))
    assert response.get_json() == {"toolClasses": [], "tools": []}
    assert anonymous.get(APPROVALS).status_code == 401
    # replacing a pending tool class doesn't approve it
    changed = {"name": "Changed"}
    assert client.put(f"{TOOL_CLASSES}/new", json=changed).status_code == 200
    stored = mongo_client[DB]["toolclasses"].find_one({"id": "new"}, {"_id": False})
    assert stored == {"id": "new", **changed, "_createdBy": USER, PENDING: True}
    # only admins approve tool classes
    approval = f"{TOOL_CLASSES}/new/approval"
    assert client.put(approval, headers=user).status_code == 403
    for _ in range(2):
        response = client.put(approval)
        assert response.status_code == 200
        assert response.get_json() == "new"
    assert "new" in _class_ids(anonymous)
    assert client.put(f"{TOOL_CLASSES}/unknown/approval").status_code == 404


def test_moderated_tools(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Tools with a pending tool class are pending too.

    They are only served to admins and the users with a role on them, until
    an admin approves the tool class.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    app = _app(overlay, "moderated")
    client = admin_client(app)
    anonymous = app.app.test_client()
    tool_id = _register(client, "new")
    other_id = _register(client, "new", user=COLLEAGUE)
    approved_id = _register(client, "byadmin", user=ADMIN)
    tools = mongo_client[DB]["tools"]
    toolclasses = mongo_client[DB]["toolclasses"]
    assert toolclasses.find_one({"id": "new"}, {"_id": False}) == {
        "id": "new",
        **NEW_CLASS,
        "_createdBy": USER,
        PENDING: True,
    }
    assert _doc(tools, tool_id)[PENDING] is True
    assert _doc(tools, other_id)[PENDING] is True
    assert PENDING not in _doc(tools, approved_id)
    response = client.get(f"{TOOLS}/{tool_id}/versions", headers=make_headers(USER))
    version_id = response.get_json()[0]["id"]
    # the tool's tool class is served without internal fields
    tool = client.get(f"{TOOLS}/{tool_id}").get_json()
    assert tool["toolclass"] == {"id": "new", **NEW_CLASS}
    assert PENDING not in tool
    all_reads = len(_tool_paths(tool_id, version_id)) + 1
    assert _reads(client, tool_id, version_id) == all_reads
    assert _reads(client, tool_id, version_id, headers=make_headers(USER)) == (
        all_reads
    )
    assert _reads(client, tool_id, version_id, headers=make_headers(STRANGER)) == 0
    assert _reads(anonymous, tool_id, version_id) == 0
    # the colleague registered a tool with the user's pending tool class, and
    # sees that one only
    assert _reads(client, tool_id, version_id, headers=make_headers(COLLEAGUE)) == 0
    response = client.get(APPROVALS, headers=make_headers(COLLEAGUE))
    assert response.get_json()["toolClasses"] == []
    assert [tool["id"] for tool in response.get_json()["tools"]] == [other_id]
    response = client.get(APPROVALS)
    assert response.get_json()["toolClasses"] == [{"id": "new", **NEW_CLASS}]
    assert [tool["id"] for tool in response.get_json()["tools"]] == sorted(
        [tool_id, other_id]
    )
    assert all(
        "files" not in version
        for tool in response.get_json()["tools"]
        for version in tool["versions"]
    )
    # approving the tool class approves its tools
    assert client.put(f"{TOOL_CLASSES}/new/approval").status_code == 200
    assert tools.count_documents({PENDING: True}) == 0
    assert _reads(anonymous, tool_id, version_id) == all_reads
    assert client.get(APPROVALS).get_json() == {"toolClasses": [], "tools": []}


def test_moderated_replace_tool(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Replacing a tool sets its pending flag by its new tool class.

    Adding versions keeps it.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = admin_client(_app(overlay, "moderated"))
    user = make_headers(USER)
    tool_id = _register(client, "new")
    tools = mongo_client[DB]["tools"]
    version = deepcopy(MOCK_TOOL["versions"][0])
    response = client.post(f"{TOOLS}/{tool_id}/versions", json=version, headers=user)
    assert response.status_code == 200
    assert _doc(tools, tool_id)[PENDING] is True
    assert client.put(f"{TOOL_CLASSES}/byadmin", json=NEW_CLASS).status_code == 200
    path = f"{TOOLS}/{tool_id}"
    response = client.put(path, json=_tool("byadmin"), headers=user)
    assert response.status_code == 200
    assert PENDING not in _doc(tools, tool_id)
    response = client.put(path, json=_tool("new"), headers=user)
    assert response.status_code == 200
    assert _doc(tools, tool_id)[PENDING] is True


def test_open_mode_keeps_pending(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Pending tool classes stay pending when the mode changes.

    Tools registered with them are pending too; new tool classes aren't.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = admin_client(_app(overlay, "moderated"))
    _register(client, "new")
    client = admin_client(_app(overlay, "open"))
    tool_id = _register(client, "new", user=COLLEAGUE)
    other_id = _register(client, "other", user=COLLEAGUE)
    tools = mongo_client[DB]["tools"]
    assert _doc(tools, tool_id)[PENDING] is True
    assert PENDING not in _doc(tools, other_id)
    assert _doc(mongo_client[DB]["toolclasses"], "other")["_createdBy"] == COLLEAGUE


def test_startup_sync(mongo_client: MongoClient[dict[str, Any]], overlay: Path) -> None:
    """The app corrects the pending flags of tools on startup.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = admin_client(_app(overlay, "moderated"))
    pending_id = _register(client, "new")
    approved_id = _register(client, "byadmin", user=ADMIN)
    tools = mongo_client[DB]["tools"]
    # flags missed, e.g., by interrupted requests
    tools.update_one({"id": pending_id}, {"$unset": {PENDING: ""}})
    tools.update_one({"id": approved_id}, {"$set": {PENDING: True}})
    tools.insert_one({"id": "noclass", "toolclass": {"id": None}, PENDING: True})
    _app(overlay, "moderated")
    assert _doc(tools, pending_id)[PENDING] is True
    assert PENDING not in _doc(tools, approved_id)
    # tools without a valid tool class identifier are skipped
    assert _doc(tools, "noclass")[PENDING] is True


def test_added_tool_class_syncs(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Adding a tool class sets the pending flags of the tools that have it.

    E.g., of a tool whose pending tool class an admin deleted while it was
    registered: it is pending without a tool class to approve, until an
    admin adds the tool class again.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    client = admin_client(_app(overlay, "moderated"))
    tools = mongo_client[DB]["tools"]
    tools.insert_one({"id": "TOOL", "toolclass": {"id": "gone"}, PENDING: True})
    tools.insert_one({"id": "OTHER", "toolclass": {"id": "pending"}})
    assert client.put(f"{TOOL_CLASSES}/gone", json=NEW_CLASS).status_code == 200
    assert PENDING not in _doc(tools, "TOOL")
    user = make_headers(USER)
    response = client.put(f"{TOOL_CLASSES}/pending", json=NEW_CLASS, headers=user)
    assert response.status_code == 200
    assert _doc(tools, "OTHER")[PENDING] is True
    # also if a registration adds it, in any mode
    tools.insert_one({"id": "THIRD", "toolclass": {"id": "new"}, PENDING: True})
    client = admin_client(_app(overlay, "open"))
    _register(client, "new")
    assert PENDING not in _doc(tools, "THIRD")


def test_sync_pending_flags_changed(
    app: App, monkeypatch: pytest.MonkeyPatch, mongo_client: MongoClient[dict[str, Any]]
) -> None:
    """Flags are written again if the tool class changes meanwhile.

    Args:
        app: FOCA app.
        monkeypatch: Patches of the check of the tool class.
        mongo_client: MongoDB client.
    """
    tools = mongo_client[DB]["tools"]
    tools.insert_one({"id": "TOOL", "toolclass": {"id": "new"}})
    # the tool class is pending on the first check (the flag is set), and
    # approved on the check after the write (the flag is cleared again, and
    # the third check confirms it); each check records the flag it sees
    states = iter([False, True, True])
    flags: list[bool] = []

    def is_approved(id: str) -> bool:
        """Record the flag of the tool, and return the next state.

        Args:
            id: Tool class identifier.

        Returns:
            Whether the tool class is approved.
        """
        flags.append(PENDING in _doc(tools, "TOOL"))
        return next(states)

    monkeypatch.setattr(tool_classes, "is_approved", is_approved)
    with app.app.app_context():
        sync_pending_flags("new")
    assert flags == [False, True, False]
    assert PENDING not in _doc(tools, "TOOL")


def test_noauth_not_moderated(
    mongo_client: MongoClient[dict[str, Any]],
    overlay: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without authentication, nothing is pending, and all tools are served.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
        monkeypatch: Patches of `FOCA_CONFIG_OVERLAY`.
    """
    overlay.write_text("custom:\n  access_control:\n    tool_classes: moderated\n")
    monkeypatch.setenv(
        "FOCA_CONFIG_OVERLAY",
        os.pathsep.join(
            [
                str(ROOT / "config.dev.yaml"),
                str(ROOT / "config.noauth.yaml"),
                str(overlay),
            ]
        ),
    )
    client = create_app().app.test_client()
    response = client.post(TOOLS, json=_tool("new"))
    assert response.status_code == 200, response.get_json()
    tool_id = response.get_json()
    assert client.post(TOOL_CLASSES, json=NEW_CLASS).status_code == 200
    assert mongo_client[DB]["toolclasses"].count_documents({PENDING: True}) == 0
    # tools left pending (e.g., by a deployment with authentication) are
    # served to everybody
    tools = mongo_client[DB]["tools"]
    tools.update_one({"id": tool_id}, {"$set": {PENDING: True}})
    assert client.get(f"{TOOLS}/{quote(tool_id)}").status_code == 200
    response = client.get(APPROVALS)
    assert [tool["id"] for tool in response.get_json()["tools"]] == [tool_id]
