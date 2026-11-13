"""Modes of adding tool classes, and pending tool classes and tools.

As the service types of Cloud Registry: who may add tool classes is
configured (`custom.access_control.tool_classes`). In mode `open` (the
default), any authenticated user, explicitly (`POST /toolClasses`, `PUT
/toolClasses/{id}` with the identifier of no tool class) or by registering a
tool with a new tool class; in mode `controlled`, admins only, and tools of
other users must have a stored tool class (cf. `may_add_tool_classes()`). In
every mode, only admins replace and delete tool classes (no policy in
`config.yaml` allows it to other users).

In mode `moderated`, any authenticated user may add tool classes, but those
that users other than admins add are pending (`PENDING`) until an admin
approves them (`PUT /toolClasses/{id}/approval`); there is no way back,
admins delete tool classes instead. Tools whose tool class is pending are
pending too: stored with an indexed flag (`PENDING`, as for tool classes),
which registrations set, approvals clear, and the app reconciles on startup
(cf. `sync_pending_tools()`). Pending tool classes are only listed (`GET
/toolClasses`) to admins and the user who added them (`CREATED_BY`), pending
tools (all reads of tools) to admins and the users with a role on them;
reads without a token have no user, so they don't list them (cf. `GET
/approvals`, which requires login). Pending tool classes stay pending if
the mode changes.

Without authentication (`disable_auth`), there are no users and no admins:
anybody may add tool classes, which are never pending, and all tools are
listed.
"""

import logging
from typing import Any

from foca import get_config
from foca.security.access_control import (
    get_current_subject,
    is_admin,
    resource_filter,
)
from foca.utils.urls import get_resource_path

from trs_filer.utils import get_collection, get_custom_config

logger = logging.getLogger(__name__)

# Internal fields of stored tool classes (not part of TRS, and not served):
# who added the tool class (the identifier of the user, as `_createdBy` of
# tools; `None` without authentication), and `True` while the tool class is
# pending (mode `moderated`), i.e., until an admin approves it; not set for
# approved tool classes. Pending tools have `PENDING` set, too
CREATED_BY = "_createdBy"
PENDING = "_pending"
# Query for approved tool classes, and for tools that are not pending
APPROVED = {PENDING: {"$ne": True}}
# Projection of tool classes as served (and as stored with tools): without
# MongoDB's `_id` and internal fields
TOOL_CLASS_PROJECTION: dict[str, bool] = {
    "_id": False,
    CREATED_BY: False,
    PENDING: False,
}
# Reason of `400 Bad Request` for tools of users who may not add tool classes
# with a tool class that is not stored
UNREGISTERED_TOOL_CLASS = (
    "The tool class doesn't exist: use a registered one (`GET /toolClasses`), "
    "or ask an admin to add it."
)


def auth_disabled() -> bool:
    """Check whether authentication is disabled.

    Returns:
        Whether an API of the app is served without authentication
        (`api.specs.<name>.disable_auth`), as for local tests (see "Running
        without authentication" in `docs/development.md`).
    """
    return any(spec.disable_auth for spec in get_config().api.specs)


def may_add_tool_classes() -> bool:
    """Check whether the current user may add tool classes.

    Returns:
        Whether the deployment lets any authenticated user add tool classes
        (`custom.access_control.tool_classes` is `open` or `moderated`), the
        user is an admin, or authentication is disabled.
    """
    mode = get_custom_config().access_control.tool_classes
    return mode != "controlled" or auth_disabled() or is_admin()


def tool_classes_pending() -> bool:
    """Check whether tool classes that the current user adds are pending.

    Returns:
        Whether the deployment moderates tool classes
        (`custom.access_control.tool_classes` is `moderated`) and the user
        is not an admin, so that their new tool classes are pending until an
        admin approves them; never without authentication.
    """
    mode = get_custom_config().access_control.tool_classes
    return mode == "moderated" and not auth_disabled() and not is_admin()


def is_approved(id: str) -> bool:
    """Check whether a tool class is stored and approved.

    Args:
        id: Tool class identifier.

    Returns:
        Whether the tool class is stored and not pending (cf. `PENDING`).
    """
    collection = get_collection("toolclasses")
    return collection.count_documents({"id": id, **APPROVED}, limit=1) > 0


def visible_tool_classes() -> dict[str, Any]:
    """Get the filter for the tool classes that the current user may see.

    Returns:
        Filter for all tool classes if the user is an admin or authentication
        is disabled; otherwise, for the approved tool classes, and the
        pending ones the user added.
    """
    if auth_disabled() or is_admin():
        return {}
    subject = get_current_subject()
    if subject is None:
        return dict(APPROVED)
    return {"$or": [dict(APPROVED), {CREATED_BY: subject}]}


def own_tools() -> dict[str, Any]:
    """Get the filter for the tools that the current user has a role on.

    Returns:
        Filter for all tools if authentication is disabled, or (FOCA's
        `resource_filter()` returns an empty filter for them) the user is an
        admin; otherwise, for the tools the user has a role on (also through
        groups), none without a user.
    """
    if auth_disabled():
        return {}
    return resource_filter(get_resource_path("tools"))


def visible_tools(query: dict[str, Any] | None = None) -> dict[str, Any]:
    """Restrict a query of tools to those the current user may see.

    The filter has the same size for any number of pending tool classes or
    tools.

    Args:
        query: Query of tools; all tools if `None`.

    Returns:
        The query if the user is an admin or authentication is disabled;
        otherwise, always the query restricted to the tools that aren't
        pending (also if none is), and, if any tool is pending (one indexed
        lookup), those the user has a role on.
    """
    query = {} if query is None else query
    if auth_disabled() or is_admin():
        return query
    tools = get_collection("tools")
    if tools.find_one({PENDING: True}, {"_id": True}) is None:
        # also for tools that become pending meanwhile
        visible: dict[str, Any] = dict(APPROVED)
    else:
        visible = {"$or": [dict(APPROVED), own_tools()]}
    return {"$and": [query, visible]} if query else visible


def sync_pending_flags(id: str, query: dict[str, Any] | None = None) -> None:
    """Set or clear the pending flags of tools by their tool class.

    Tools are pending unless their tool class is stored and approved (e.g.,
    also while it is deleted, or not yet added). Writes first, then checks
    the tool class again, and writes again if its state changed meanwhile
    (e.g., approved, or deleted and added again as pending), so that
    concurrent calls and approvals end with the flags of its last state:
    each change of the state is followed by a call (cf.
    `putToolClassApproval()`, `RegisterTool.register_metadata()`), and
    either that call or the check here sees the other's write.

    Args:
        id: Tool class identifier.
        query: Query of the tools to change (e.g., one tool); all tools of
            the tool class if `None`.
    """
    tools = get_collection("tools")
    query = {**(query or {}), "toolclass.id": id}
    pending = not is_approved(id)
    while True:
        if pending:
            tools.update_many({**query, **APPROVED}, {"$set": {PENDING: True}})
        else:
            tools.update_many({**query, PENDING: True}, {"$unset": {PENDING: ""}})
        changed = not is_approved(id)
        if changed == pending:
            return
        pending = changed


def sync_pending_tools() -> None:
    """Set the pending flags of the stored tools by their tool classes.

    Run on startup, so that flags missed by interrupted requests are
    corrected; idempotent, and safe to run concurrently (cf.
    `sync_pending_flags()`). Only checks the pending tool classes, and the
    tool classes of the tools flagged as pending, not all tool classes.
    """
    pending = get_collection("toolclasses").find({PENDING: True}, {"id": True})
    flagged = get_collection("tools").distinct("toolclass.id", {PENDING: True})
    ids = {*(tool_class["id"] for tool_class in pending), *flagged}
    for id in sorted(id for id in ids if isinstance(id, str)):
        sync_pending_flags(id)
