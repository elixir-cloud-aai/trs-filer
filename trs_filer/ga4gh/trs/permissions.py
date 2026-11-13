"""Roles on tools: owners, maintainers and the permission controllers.

As for services in Cloud Registry: any authenticated user may register tools
and becomes their owner; roles on tools (`security.access_control.resource_roles`:
`owner` and `maintainer`) are granted to users (by their identifier, the `sub`
claim) and to groups (values of the group claim), with FOCA's resource
ownership helpers, which keep the last owner of a tool (`409 Conflict`) and
log changes of roles. What each role may do is decided by the policies in
`config.yaml` (`security.access_control.policies`), which FOCA enforces;
subjects with the role `admin` may do everything.

The permission controllers are FOCA's ready-made ones
(`foca.security.access_control.ownership_server`), with a check that the tool
exists, so that admins can grant the first owner of tools stored before tools
had owners.
"""

from collections.abc import Callable
import logging
from typing import Any

from foca.security.access_control import (
    add_owner,
    get_current_subject,
    ownership_server,
    remove_resource,
    remove_resource_role,
)
from foca.security.access_control.foca_casbin_adapter.casbin_rule import (
    validate_rule_value,
)
from foca.utils.logging import escape_log_value
from foca.utils.urls import get_resource_path

from trs_filer.utils import get_collection

logger = logging.getLogger(__name__)


def tool_path(id: str) -> str:
    """Get the resource path of a tool, i.e., the path roles are granted on.

    Args:
        id: Tool identifier.

    Returns:
        Request path of the tool, including the base path of the API (e.g.,
        `/ga4gh/trs/v2/tools/ABC123`).

    Raises:
        ValueError: The identifier can't be part of a resource path (cf.
            FOCA's `get_resource_path()`).
    """
    return get_resource_path("tools", id)


def is_usable_id(id: str) -> bool:
    """Check whether roles can be granted on a tool with an identifier.

    Args:
        id: Tool identifier.

    Returns:
        Whether the path of the tool is a valid resource of roles: not a
        wildcard or dot segment of policy rules, and a valid value of policy
        rules (e.g., without commas).
    """
    try:
        validate_rule_value(tool_path(id))
    except ValueError:
        return False
    return True


def tool_exists(id: str) -> bool:
    """Check whether a tool exists.

    Args:
        id: Tool identifier.

    Returns:
        Whether the tool is stored.
    """
    return get_collection("tools").count_documents({"id": id}, limit=1) > 0


def _exists(id: str) -> Callable[[], bool]:
    """Get the existence check of a tool, for FOCA's role controllers.

    Args:
        id: Tool identifier.

    Returns:
        Function checking whether the tool exists.
    """
    return lambda: tool_exists(id)


def own_tool(id: str) -> None:
    """Make the subject of the current request owner of a new tool.

    Roles left on the identifier (e.g., if revoking those of a deleted tool
    failed) are revoked first, as they don't apply to the new tool. Nothing
    is granted to requests without a subject, which only happen when
    authentication is disabled (see "Running without authentication" in
    `docs/development.md`). If the tool was deleted meanwhile, the role
    granted here is revoked again.

    Args:
        id: Tool identifier.

    Raises:
        ValueError: The role can't be stored, e.g., for identifiers with
            commas (cf. `is_usable_id()`).
    """
    subject = get_current_subject()
    if subject is None:
        return
    path = tool_path(id)
    remove_resource(path)
    add_owner(path)
    if not tool_exists(id):
        remove_resource_role(subject=subject, role="owner", resource=path)


def remove_roles(id: str) -> None:
    """Revoke all roles granted on a tool, e.g., when it is deleted.

    Args:
        id: Tool identifier.
    """
    if remove_resource(tool_path(id)):
        logger.info(
            "All roles on tool '%s' revoked by '%s'.",
            escape_log_value(id),
            escape_log_value(get_current_subject()),
        )


def _call(controller: Callable[..., Any], id: str, **kwargs: Any) -> Any:
    """Call a role controller of FOCA with the existence check of a tool.

    Args:
        controller: Controller of `foca.security.access_control.ownership_server`.
        id: Tool identifier.
        **kwargs: Further arguments that Connexion passes (path parameters,
            the request body as `body`).

    Returns:
        Response of the controller.
    """
    return controller(exists=_exists(id), **kwargs)


# GET /tools/{id}/permissions
def getToolPermissions(id: str, **kwargs: Any) -> list[dict[str, str]]:
    """List the roles granted on a tool.

    See FOCA's `getResourceRoles()`.

    Args:
        id: Tool identifier.
        **kwargs: Further arguments that Connexion passes.

    Returns:
        Subject type, subject and role of each role granted on the tool.
    """
    roles: list[dict[str, str]] = _call(ownership_server.getResourceRoles, id, **kwargs)
    return roles


# PUT /tools/{id}/permissions/users/{userId}
def putToolPermission(id: str, **kwargs: Any) -> dict[str, str]:
    """Grant a user a role on a tool, replacing any other role.

    See FOCA's `putUserRole()`.

    Args:
        id: Tool identifier.
        **kwargs: Further arguments that Connexion passes (`userId`, `body`).

    Returns:
        Subject type (`user`), user identifier and granted role.
    """
    role: dict[str, str] = _call(ownership_server.putUserRole, id, **kwargs)
    return role


# DELETE /tools/{id}/permissions/users/{userId}
def deleteToolPermission(id: str, **kwargs: Any) -> str:
    """Revoke the roles of a user on a tool.

    See FOCA's `deleteUserRole()`.

    Args:
        id: Tool identifier.
        **kwargs: Further arguments that Connexion passes (`userId`).

    Returns:
        User identifier.
    """
    user: str = _call(ownership_server.deleteUserRole, id, **kwargs)
    return user


# PUT /tools/{id}/permissions/groups/{group}
def putToolGroupPermission(id: str, **kwargs: Any) -> dict[str, str]:
    """Grant a group a role on a tool, replacing any other role.

    See FOCA's `putGroupRole()`: owners may only grant roles to groups they
    are members of, admins to any group.

    Args:
        id: Tool identifier.
        **kwargs: Further arguments that Connexion passes (`group`, `body`).

    Returns:
        Subject type (`group`), group and granted role.
    """
    role: dict[str, str] = _call(ownership_server.putGroupRole, id, **kwargs)
    return role


# DELETE /tools/{id}/permissions/groups/{group}
def deleteToolGroupPermission(id: str, **kwargs: Any) -> str:
    """Revoke the roles of a group on a tool.

    See FOCA's `deleteGroupRole()`.

    Args:
        id: Tool identifier.
        **kwargs: Further arguments that Connexion passes (`group`).

    Returns:
        The group.
    """
    group: str = _call(ownership_server.deleteGroupRole, id, **kwargs)
    return group
