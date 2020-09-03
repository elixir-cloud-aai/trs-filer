""""Controllers for TRS endpoints."""

from typing import (Optional, Dict, List)

from flask import (request, current_app)
from foca.utils.logging import log_traffic

from trs_filer.ga4gh.trs.endpoints.register_tools import (
    RegisterObject,
)
from trs_filer.errors.exceptions import NotFound


@log_traffic
def toolsIdGet(
    id: str
) -> Dict:
    """List one specific tool, acts as an anchor for self references.

    Args:
        id: A unique identifier of the tool.

    Returns:
        Tool object dict corresponding given tool id.

    Raise:
        NotFound if no object mapping with given id present.
    """
    db_collection = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['objects'].client
    )
    obj = db_collection.find_one({"id": id})
    if not obj:
        raise NotFound
    del obj["_id"]
    return obj


@log_traffic
def toolsIdVersionsGet(
    id: str
) -> List[Dict]:
    """List versions of a tool.

    Args:
        id: A unique identifier of the tool.

    Returns:
        List of version dicts corresponding given tool id.
    """
    obj = toolsIdGet.__wrapped__(id)
    return obj["versions"]


@log_traffic
def toolsIdVersionsVersionIdGet(
    id: str,
    version_id: str,
) -> Dict:
    """List one specific tool version, acts as an anchor for self references.
    """
    return {}  # pragma: no cover


@log_traffic
def toolsGet(
    id: Optional[str] = None,
    alias: Optional[str] = None,
    toolClass: Optional[str] = None,
    registry: Optional[str] = None,
    organization: Optional[str] = None,
    name: Optional[str] = None,
    toolname: Optional[str] = None,
    description: Optional[str] = None,
    author: Optional[str] = None,
    checker: Optional[bool] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> List:
    """List all tools.
    Args:
        id: A unique identifier of the tool.
        alias: Tool alias identifier.
        toolClass: Tool sub class.
        registry: The image registry that contains the image.
        organization: The organization in the registry that published
        the image.
        name: Name of the image.
        toolname: Name of the tool.
        description: Description of the tool.
        author: Author of the tool.
        checker: Flag for identifying checker workflows.

    Returns:
        Returns a list of all tools if no filters applied.
        Filters and returns tools if params provided.
    """
    filter_list = []

    if id is not None:
        filter_list.append({"id": id})

    if organization is not None:
        filter_list.append({"organization": organization})

    if toolClass is not None:
        filter_list.append({"toolClass": toolClass})

    if description is not None:
        filter_list.append({"description": description})

    if toolname is not None:
        filter_list.append({"name": toolname})

    # add support for registry, name, author and checker.

    # Apply filter
    db_collection = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['objects'].client
    )

    if filter_list:
        records = db_collection.find(
            {"$and": filter_list},
            {"_id": False}
        )
    else:
        records = db_collection.find({}, {"_id": False})
    records = list(records)

    if alias is not None:
        records = [rec for rec in records if alias in rec["aliases"]]

    if offset:
        records = records[offset:]
    if limit:
        records = records[:limit]

    # headers = {}
    # headers['next_page'] = None
    # headers['last_page'] = None
    # headers['self_link'] = None
    # headers['current_offset'] = None
    # headers['current_limit'] = None
    return records


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorGet(
    type: str,
    id: str,
    version_id: str,
) -> Dict:
    """Get the tool descriptor for the specified tool."""
    return {}  # pragma: no cover


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorRelativePathGet(
    type: str,
    id: str,
    version_id: str,
    relative_path: str,
) -> Dict:
    """Get additional tool descriptor files relative to the main file."""
    return {}  # pragma: no cover


@log_traffic
def toolsIdVersionsVersionIdTypeTestsGet(
    type: str,
    id: str,
    version_id: str,
) -> List:
    """Get a list of test JSONs."""
    return []  # pragma: no cover


@log_traffic
def toolsIdVersionsVersionIdTypeFilesGet(
    type: str,
    id: str,
    version_id: str,
    format: Optional[str] = None,
) -> List:
    """Get a list of objects that contain the relative path and file type."""
    return []  # pragma: no cover


@log_traffic
def toolsIdVersionsVersionIdContainerfileGet(
    id: str,
    version_id: str,
) -> List:
    """Get the container specification(s) for the specified image."""
    return []  # pragma: no cover


@log_traffic
def toolClassesGet() -> List:
    """List all tool types."""
    return []  # pragma: no cover


@log_traffic
def getServiceInfo() -> Dict:
    """Show information about this service."""
    return {}  # pragma: no cover


@log_traffic
def postTool() -> Dict:
    """Add tool with an auto-generated ID.

    Returns:
        Identifier of created object.
    """
    tool_creator = RegisterObject(request=request)
    tool = tool_creator.register_object()
    return tool['id']


@log_traffic
def putTool(
    id: str,
) -> Dict:
    """Add tool with a user-supplied ID.

    Args:
        id: Identifier of tool to be created/updated.

    Returns:
        Identifier of created/updated object.
    """
    tool_creator = RegisterObject(
        request=request,
        id=id,
    )
    tool = tool_creator.register_object()
    return tool['id']


@log_traffic
def deleteTool(
    id: str,
) -> str:
    """Delete tool object.

    Args:
        id: Identifier of tool object to be deleted.

    Returns:
        Previous identifier of deleted object.
    """
    db_collection = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['objects'].client
    )
    del_obj = db_collection.delete_one({'id': id})
    if not del_obj.deleted_count:
        raise NotFound
    else:
        return id
