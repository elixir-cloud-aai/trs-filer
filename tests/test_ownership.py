"""Tests of roles on tools: owners, maintainers, groups and admins.

The app is created from `config.yaml` and the test overlay, whose identity
provider is mocked (see `tests/conftest.py`).
"""

from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote

from flask.testing import FlaskClient
from pymongo import MongoClient
from pymongo.collection import Collection
import pytest

from tests.conftest import (
    ADMIN,
    ADMIN_GROUP,
    COLLEAGUE,
    EDITOR,
    USER,
    USERS_GROUP,
    make_headers,
)
from tests.mock_data import BASE_PATH, MOCK_TOOL, MOCK_VERSION_NO_ID
from tests.test_access_control import _doc_example, _overlay
from trs_filer.app import create_app
from trs_filer.ga4gh.trs import permissions
from trs_filer.ga4gh.trs.endpoints import register_objects
from trs_filer.ga4gh.trs.endpoints.register_objects import (
    CREATED_AT,
    CREATED_BY,
    UPDATED_AT,
    RegisterTool,
    RegisterToolVersion,
)

TOOLS = f"{BASE_PATH}/tools"
# Another user, without a role on the tools of the tests and in no group
STRANGER = "mallory@example.org"


def _register(client: FlaskClient, user: str = USER) -> str:
    """Register a tool.

    Args:
        client: Test client.
        user: User registering the tool.

    Returns:
        Identifier of the tool.
    """
    response = client.post(TOOLS, json=MOCK_TOOL, headers=make_headers(user))
    assert response.status_code == 200, response.get_json()
    tool_id: str = response.get_json()
    return tool_id


def _version_id(client: FlaskClient, tool_id: str) -> str:
    """Get the identifier of the first version of a tool.

    Args:
        client: Test client.
        tool_id: Tool identifier.

    Returns:
        Version identifier.
    """
    version_id: str = client.get(f"{TOOLS}/{tool_id}/versions").get_json()[0]["id"]
    return version_id


def _grant(
    client: FlaskClient,
    tool_id: str,
    subject: str,
    role: str,
    by: str = USER,
    group: bool = False,
) -> Any:
    """Grant a user or group a role on a tool.

    Args:
        client: Test client.
        tool_id: Tool identifier.
        subject: User or group.
        role: Role to grant.
        by: User granting the role.
        group: Whether the subject is a group.

    Returns:
        Response.
    """
    kind = "groups" if group else "users"
    return client.put(
        f"{TOOLS}/{tool_id}/permissions/{kind}/{quote(subject, safe='')}",
        json={"role": role},
        headers=make_headers(by),
    )


def _roles(client: FlaskClient, tool_id: str, by: str = ADMIN) -> Any:
    """List the roles on a tool.

    Args:
        client: Test client.
        tool_id: Tool identifier.
        by: User listing the roles.

    Returns:
        Response.
    """
    return client.get(f"{TOOLS}/{tool_id}/permissions", headers=make_headers(by))


def _changes(tool_id: str, version_id: str) -> dict[str, tuple[str, str, Any]]:
    """Get the changes of a tool, by name.

    Args:
        tool_id: Tool identifier.
        version_id: Identifier of a version of the tool.

    Returns:
        Method, path and body of each change.
    """
    tool = f"{TOOLS}/{tool_id}"
    return {
        "add version": ("POST", f"{tool}/versions", MOCK_VERSION_NO_ID),
        "replace version": (
            "PUT",
            f"{tool}/versions/{version_id}",
            MOCK_VERSION_NO_ID,
        ),
        "delete version": ("DELETE", f"{tool}/versions/{version_id}", None),
        "replace tool": ("PUT", tool, MOCK_TOOL),
        "list roles": ("GET", f"{tool}/permissions", None),
        "grant role": (
            "PUT",
            f"{tool}/permissions/users/{STRANGER}",
            {"role": "maintainer"},
        ),
        "delete tool": ("DELETE", tool, None),
    }


def _check_changes(
    client: FlaskClient, tool_id: str, user: str, allowed: set[str]
) -> None:
    """Check which changes of a tool a user may make.

    The tool gets a second version first, so that one can be deleted.

    Args:
        client: Test client.
        tool_id: Tool identifier.
        user: User making the changes.
        allowed: Names of the changes the user may make (cf. `_changes()`).
    """
    response = client.post(
        f"{TOOLS}/{tool_id}/versions",
        json=MOCK_VERSION_NO_ID,
        headers=make_headers(ADMIN),
    )
    assert response.status_code == 200
    changes = _changes(tool_id, _version_id(client, tool_id))
    for name, (method, path, body) in changes.items():
        response = client.open(
            path, method=method, json=body, headers=make_headers(user)
        )
        expected = 200 if name in allowed else 403
        assert response.status_code == expected, (name, response.get_json())


def test_creator_owns_tool(client: FlaskClient) -> None:
    """The user registering a tool becomes its owner.

    Owners and admins list the roles; other users may not, also with the
    default rules for reads, and anonymous requests need a token.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    owner = [{"subject_type": "user", "subject": USER, "role": "owner"}]
    for user in (USER, ADMIN):
        response = _roles(client, tool_id, by=user)
        assert response.status_code == 200
        assert response.get_json() == owner
    assert _roles(client, tool_id, by=STRANGER).status_code == 403
    anonymous = client.application.test_client()
    assert anonymous.get(f"{TOOLS}/{tool_id}/permissions").status_code == 401


def test_owner_changes(client: FlaskClient) -> None:
    """Owners may make all changes of their tools.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    _check_changes(client, tool_id, USER, set(_changes(tool_id, "x")))


def test_maintainer_changes(client: FlaskClient) -> None:
    """Maintainers may add and replace versions, nothing else.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    assert _grant(client, tool_id, COLLEAGUE, "maintainer").status_code == 200
    _check_changes(client, tool_id, COLLEAGUE, {"add version", "replace version"})


def test_others_changes(client: FlaskClient) -> None:
    """Users without a role on a tool may not change it.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    _check_changes(client, tool_id, STRANGER, set())


def test_admin_changes(client: FlaskClient) -> None:
    """Admins may make all changes of tools of others.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    _check_changes(client, tool_id, ADMIN, set(_changes(tool_id, "x")))


def test_put_new_tool(client: FlaskClient) -> None:
    """Any user may register a tool with `PUT`, but only its owners replace it.

    Args:
        client: Test client.
    """
    path = f"{TOOLS}/NEWTOOL"
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 200
    assert _roles(client, "NEWTOOL").get_json() == [
        {"subject_type": "user", "subject": USER, "role": "owner"}
    ]
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(STRANGER))
    assert response.status_code == 403
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 200
    # the owner stays the user who registered it
    assert _roles(client, "NEWTOOL").get_json() == [
        {"subject_type": "user", "subject": USER, "role": "owner"}
    ]


def test_put_tool_unusable_id(
    client: FlaskClient, tools: Collection[dict[str, Any]]
) -> None:
    """New tools with identifiers that can't be stored in roles are refused.

    Args:
        client: Test client.
        tools: Collection `tools`.
    """
    response = client.put(f"{TOOLS}/A,B", json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 400
    assert "commas" in response.get_json()["detail"]
    assert tools.count_documents({}) == 0


def test_tool_deleted_while_owned(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner role of a tool deleted while it is granted is revoked again.

    Args:
        client: Test client.
        monkeypatch: Patch of the existence check of tools.
    """
    exists = permissions.tool_exists
    monkeypatch.setattr(permissions, "tool_exists", lambda id: False)
    tool_id = _register(client)
    monkeypatch.setattr(permissions, "tool_exists", exists)
    assert _roles(client, tool_id).get_json() == []


def test_owner_role_fails(
    client: FlaskClient,
    tools: Collection[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new tool is deleted again if its owner role can't be granted.

    Args:
        client: Test client.
        tools: Collection `tools`.
        monkeypatch: Patch of the grant of the owner role.
    """

    def fail(path: str) -> None:
        raise RuntimeError("Can't store roles")

    monkeypatch.setattr(permissions, "add_owner", fail)
    response = client.post(TOOLS, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 500
    assert tools.count_documents({}) == 0


def test_delete_tool_revokes_roles(client: FlaskClient) -> None:
    """Deleting a tool revokes its roles, also for a tool with its identifier.

    Args:
        client: Test client.
    """
    path = f"{TOOLS}/NEWTOOL"
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 200
    assert _grant(client, "NEWTOOL", COLLEAGUE, "maintainer").status_code == 200
    assert client.delete(path, headers=make_headers(USER)).status_code == 200
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(STRANGER))
    assert response.status_code == 200
    assert _roles(client, "NEWTOOL").get_json() == [
        {"subject_type": "user", "subject": STRANGER, "role": "owner"}
    ]
    response = client.delete(path, headers=make_headers(USER))
    assert response.status_code == 403


def test_last_owner(client: FlaskClient) -> None:
    """The last owner of a tool can't be removed or downgraded.

    Once another owner is granted, they can.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    path = f"{TOOLS}/{tool_id}/permissions/users/{USER}"
    response = client.delete(path, headers=make_headers(USER))
    assert response.status_code == 409
    assert response.get_json()["status"] == 409
    assert _grant(client, tool_id, USER, "maintainer").status_code == 409
    assert _grant(client, tool_id, COLLEAGUE, "owner").status_code == 200
    assert _grant(client, tool_id, USER, "maintainer").status_code == 200
    response = _grant(client, tool_id, COLLEAGUE, "maintainer", by=COLLEAGUE)
    assert response.status_code == 409
    assert client.delete(path, headers=make_headers(COLLEAGUE)).status_code == 200
    assert _roles(client, tool_id).get_json() == [
        {"subject_type": "user", "subject": COLLEAGUE, "role": "owner"}
    ]


def test_role_errors(client: FlaskClient) -> None:
    """Invalid roles, tools and subjects without roles are refused.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    assert _grant(client, tool_id, COLLEAGUE, "admin").status_code == 400
    response = client.delete(
        f"{TOOLS}/{tool_id}/permissions/users/{STRANGER}", headers=make_headers(USER)
    )
    assert response.status_code == 404
    assert _grant(client, "NOTOOL", COLLEAGUE, "owner", by=ADMIN).status_code == 404
    assert _roles(client, "NOTOOL").status_code == 404
    assert _grant(client, "NOTOOL", COLLEAGUE, "owner").status_code == 403


def test_group_roles(client: FlaskClient) -> None:
    """Owners grant roles to their groups, whose members then have them.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    response = _grant(client, tool_id, USERS_GROUP, "maintainer", group=True)
    assert response.status_code == 200
    assert response.get_json() == {
        "subject_type": "group",
        "subject": USERS_GROUP,
        "role": "maintainer",
    }
    _check_changes(client, tool_id, COLLEAGUE, {"add version", "replace version"})
    assert _roles(client, tool_id).get_json() == [
        {"subject_type": "user", "subject": USER, "role": "owner"},
        {"subject_type": "group", "subject": USERS_GROUP, "role": "maintainer"},
    ]
    # Groups count as owners
    assert _grant(client, tool_id, USERS_GROUP, "owner", group=True).status_code == 200
    path = f"{TOOLS}/{tool_id}/permissions/users/{USER}"
    assert client.delete(path, headers=make_headers(USER)).status_code == 200
    group_path = f"{TOOLS}/{tool_id}/permissions/groups/{quote(USERS_GROUP, safe='')}"
    response = client.delete(group_path, headers=make_headers(COLLEAGUE))
    assert response.status_code == 409


def test_group_roles_members_only(client: FlaskClient) -> None:
    """Owners grant roles only to their groups; admins to any group.

    Any owner may revoke the roles of groups.

    Args:
        client: Test client.
    """
    tool_id = _register(client)
    response = _grant(client, tool_id, ADMIN_GROUP, "maintainer", group=True)
    assert response.status_code == 403
    assert response.get_json()["status"] == 403
    response = _grant(client, tool_id, "other-team", "maintainer", by=ADMIN, group=True)
    assert response.status_code == 200
    path = f"{TOOLS}/{tool_id}/permissions/groups/other-team"
    assert client.delete(path, headers=make_headers(USER)).status_code == 200
    assert client.delete(path, headers=make_headers(USER)).status_code == 404


def test_tools_without_owners(
    client: FlaskClient, tools: Collection[dict[str, Any]]
) -> None:
    """Tools stored before tools had owners: admins grant the first owner.

    Args:
        client: Test client.
        tools: Collection `tools`.
    """
    tool_id = _register(client)
    tool = tools.find_one({"id": tool_id}, {"_id": False})
    assert tool is not None
    for field in (CREATED_BY, CREATED_AT, UPDATED_AT):
        del tool[field]
    tool["id"] = "OLDTOOL"
    tools.insert_one(tool)
    path = f"{TOOLS}/OLDTOOL"
    assert client.put(path, json=MOCK_TOOL, headers=make_headers(USER)).status_code == (
        403
    )
    assert _roles(client, "OLDTOOL").get_json() == []
    assert _roles(client, "OLDTOOL", by=USER).status_code == 403
    assert _grant(client, "OLDTOOL", USER, "owner").status_code == 403
    assert _grant(client, "OLDTOOL", USER, "maintainer", by=ADMIN).status_code == 400
    assert _grant(client, "OLDTOOL", USER, "owner", by=ADMIN).status_code == 200
    assert client.put(path, json=MOCK_TOOL, headers=make_headers(USER)).status_code == (
        200
    )


def test_internal_fields(
    client: FlaskClient, tools: Collection[dict[str, Any]]
) -> None:
    """Who registered a tool and when is stored, but not served.

    Replacing the tool keeps them; changes of the tool and of its versions
    update when it last changed.

    Args:
        client: Test client.
        tools: Collection `tools`.
    """
    tool_id = _register(client)
    stored = tools.find_one({"id": tool_id})
    assert stored is not None
    assert stored[CREATED_BY] == USER
    assert stored[CREATED_AT] == stored[UPDATED_AT]
    for response in (
        client.get(f"{TOOLS}/{tool_id}"),
        client.get(TOOLS),
    ):
        assert CREATED_BY not in response.get_data(as_text=True)
    updated = stored[UPDATED_AT]
    tool = deepcopy(MOCK_TOOL)
    tool["name"] = "renamed"
    changes = [
        ("PUT", f"{TOOLS}/{tool_id}", tool, ADMIN),
        ("POST", f"{TOOLS}/{tool_id}/versions", MOCK_VERSION_NO_ID, USER),
    ]
    for method, path, body, user in changes:
        response = client.open(
            path, method=method, json=body, headers=make_headers(user)
        )
        assert response.status_code == 200
        changed = tools.find_one({"id": tool_id})
        assert changed is not None
        assert changed[CREATED_BY] == USER
        assert changed[CREATED_AT] == stored[CREATED_AT]
        assert changed[UPDATED_AT] >= updated
        updated = changed[UPDATED_AT]
    version_id = _version_id(client, tool_id)
    version_changes: list[tuple[str, dict[str, Any] | None]] = [
        ("PUT", MOCK_VERSION_NO_ID),
        ("DELETE", None),
    ]
    for method, version in version_changes:
        response = client.open(
            f"{TOOLS}/{tool_id}/versions/{version_id}",
            method=method,
            json=version,
            headers=make_headers(USER),
        )
        assert response.status_code == 200
        changed = tools.find_one({"id": tool_id})
        assert changed is not None
        assert changed[UPDATED_AT] >= updated
        updated = changed[UPDATED_AT]


def test_tool_classes(
    client: FlaskClient, toolclasses: Collection[dict[str, Any]]
) -> None:
    """Any user adds tool classes; only admins replace and delete them.

    Args:
        client: Test client.
        toolclasses: Collection `toolclasses`.
    """
    tool_class = {"name": "Workflow", "description": "A workflow."}
    path = f"{BASE_PATH}/toolClasses/new"
    response = client.put(path, json=tool_class, headers=make_headers(USER))
    assert response.status_code == 200
    response = client.put(path, json=tool_class, headers=make_headers(USER))
    assert response.status_code == 403
    assert client.delete(path, headers=make_headers(USER)).status_code == 403
    changed = {**tool_class, "name": "Changed"}
    response = client.put(path, json=changed, headers=make_headers(ADMIN))
    assert response.status_code == 200
    assert toolclasses.find_one({"id": "new"}, {"_id": False}) == {
        **changed,
        "id": "new",
    }
    response = client.post(
        f"{BASE_PATH}/toolClasses", json=tool_class, headers=make_headers(USER)
    )
    assert response.status_code == 200


def test_editors_no_roles(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Editors of the documented example may not change roles on tools.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(overlay, _doc_example("editors.yaml"))
    editors_client = create_app().app.test_client()
    tool_id = _register(editors_client)
    response = _grant(editors_client, tool_id, EDITOR, "owner", by=EDITOR)
    assert response.status_code == 403
    assert _roles(editors_client, tool_id, by=EDITOR).status_code == 403
    response = editors_client.delete(f"{TOOLS}/{tool_id}", headers=make_headers(EDITOR))
    assert response.status_code == 200


def test_delete_tool_concurrently(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool deleted meanwhile is not found.

    Args:
        client: Test client.
        monkeypatch: Patch of the existence check of tools.
    """
    # As if the tool still existed when the request checked it
    monkeypatch.setattr("trs_filer.ga4gh.trs.server.tool_exists", lambda id: True)
    response = client.delete(f"{TOOLS}/NOTOOL", headers=make_headers(ADMIN))
    assert response.status_code == 404


def test_restricted_adding(
    mongo_client: MongoClient[dict[str, Any]], overlay: Path
) -> None:
    """Without the rules for adding, users add neither with `POST` nor `PUT`.

    Admins still do.

    Args:
        mongo_client: MongoDB client.
        overlay: Config overlay.
    """
    _overlay(
        overlay,
        {
            "security": {
                "access_control": {
                    "policies": {"add-tool-classes": None, "register-tools": None}
                }
            }
        },
    )
    client = create_app().app.test_client()
    tool_class = {"name": "Workflow", "description": "A workflow."}
    writes = [
        ("POST", TOOLS, MOCK_TOOL),
        ("PUT", f"{TOOLS}/NEWTOOL", MOCK_TOOL),
        ("POST", f"{BASE_PATH}/toolClasses", tool_class),
        ("PUT", f"{BASE_PATH}/toolClasses/new", tool_class),
    ]
    for user, expected in ((USER, 403), (ADMIN, 200)):
        for method, path, body in writes:
            response = client.open(
                path, method=method, json=body, headers=make_headers(user)
            )
            assert response.status_code == expected, (user, method, path)


@pytest.mark.parametrize("again", [False, True], ids=["deleted", "registered again"])
def test_put_tool_replaced_concurrently(
    client: FlaskClient,
    tools: Collection[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    again: bool,
) -> None:
    """Only the tool checked is replaced, not one registered again meanwhile.

    Nor is a tool deleted meanwhile added again.

    Args:
        client: Test client.
        tools: Collection `tools`.
        monkeypatch: Patch of the registration of tools.
        again: Whether the tool is registered again after it is deleted.
    """
    path = f"{TOOLS}/NEWTOOL"
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 200
    register = RegisterTool.register_metadata

    def delete_first(tool: RegisterTool) -> None:
        # the tool is deleted (and registered again) after the check
        tools.delete_one({"id": "NEWTOOL"})
        if again:
            tools.insert_one({**MOCK_TOOL, "id": "NEWTOOL", "name": "other"})
        register(tool)

    monkeypatch.setattr(RegisterTool, "register_metadata", delete_first)
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 409
    stored = tools.find_one({"id": "NEWTOOL"})
    if again:
        assert stored is not None
        assert stored["name"] == "other"
    else:
        assert stored is None


def test_put_tool_deleted_while_replaced(
    client: FlaskClient,
    tools: Collection[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool deleted after it was read for replacing isn't added again.

    Args:
        client: Test client.
        tools: Collection `tools`.
        monkeypatch: Patch of the meta versions, called between reading and
            replacing the tool.
    """
    path = f"{TOOLS}/NEWTOOL"
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 200
    next_meta_version = register_objects.next_meta_version

    def delete_first(*args: Any, **kwargs: Any) -> str:
        tools.delete_one({"id": "NEWTOOL"})
        return next_meta_version(*args, **kwargs)

    monkeypatch.setattr(register_objects, "next_meta_version", delete_first)
    response = client.put(path, json=MOCK_TOOL, headers=make_headers(USER))
    assert response.status_code == 409
    assert tools.find_one({"id": "NEWTOOL"}) is None


@pytest.mark.parametrize("again", [False, True], ids=["deleted", "registered again"])
@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_version_of_tool_deleted_meanwhile(
    client: FlaskClient,
    tools: Collection[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    again: bool,
) -> None:
    """Versions go only to the tool checked, not to one registered again.

    Args:
        client: Test client.
        tools: Collection `tools`.
        monkeypatch: Patch of the processing of versions.
        method: Whether the version is added or replaced.
        again: Whether the tool is registered again after it is deleted.
    """
    response = client.put(
        f"{TOOLS}/NEWTOOL", json=MOCK_TOOL, headers=make_headers(USER)
    )
    assert response.status_code == 200
    stored = tools.find_one({"id": "NEWTOOL"})
    assert stored is not None
    version_id = stored["versions"][0]["id"]
    process = RegisterToolVersion.process_metadata

    def delete_first(version: RegisterToolVersion) -> None:
        # the tool is deleted (and registered again) while files are fetched
        tools.delete_one({"id": "NEWTOOL"})
        if again:
            tools.insert_one({"id": "NEWTOOL", "name": "other", "versions": []})
        process(version)

    monkeypatch.setattr(RegisterToolVersion, "process_metadata", delete_first)
    path = f"{TOOLS}/NEWTOOL/versions"
    if method == "PUT":
        path = f"{path}/{version_id}"
    response = client.open(
        path, method=method, json=MOCK_VERSION_NO_ID, headers=make_headers(USER)
    )
    assert response.status_code == 409
    stored = tools.find_one({"id": "NEWTOOL"})
    if again:
        assert stored is not None
        assert stored["versions"] == []
    else:
        assert stored is None
