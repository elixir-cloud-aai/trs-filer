""""Controllers for TRS endpoints."""

from typing import (Optional, Dict, List, Tuple)

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
    """
    List one specific tool version, acts as an anchor for self references.

    Args:
        id: A unique identifier of the tool.
        version_id: Specific version corresponding tool version.

    Returns:
        Specific version dict of the given tool.

    Raises:
        NotFound if no tool object present for give id mapping. Also, if
        version with given id not found.
    """

    obj = toolsIdGet.__wrapped__(id)

    for version in obj["versions"]:
        if version['id'] == version_id:
            return version

    raise NotFound


@log_traffic
def toolsGet(
    id: Optional[str] = None,
    alias: Optional[str] = None,
    toolClass: Optional[str] = None,
    descriptorType: Optional[str] = None,
    registry: Optional[str] = None,
    organization: Optional[str] = None,
    name: Optional[str] = None,
    toolname: Optional[str] = None,
    description: Optional[str] = None,
    author: Optional[str] = None,
    checker: Optional[bool] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Tuple[List, str, Dict]:
    """List all tools.

    Filter parameters to subset the tools list can be specified. Filter
    parameters are additive.

    Args:
        id: Return only entries with given identifier.
        alias: Return only entries with the given alias.
        toolClass: Return only entries with the given subclass name.
        descriptorType: Return only entries with the given descriptor type.
        registry: Return only entries from the given registry.
        organization: Return only entries from the given organization.
        name: Return only entries with the given image name.
        toolname: Return only entries with the given tool name.
        description: Return only entries with the given description.
        author: Return only entries from the given author.
        checker: Return only checker workflows.
        limit: Number of records when paginating results.
        offset: Start index when paginating results.

    Returns:
        List of all tools consistent with all filters, if specified.
    """
    # set filters
    filt = {}
    if id is not None:
        filt['id'] = id
    if alias is not None:
        filt['aliases'] = {
            '$in': [alias],
        }
    if toolClass is not None:
        filt['toolclass.name'] = toolClass
    if descriptorType:
        filt['versions'] = {
            '$elemMatch': {
                'descriptor_type': {
                    '$in': [descriptorType],
                },
            },
        }
    if registry is not None:
        filt['versions'] = {
            '$elemMatch': {
                'images': {
                    '$elemMatch': {
                        'registry_host': registry,
                    },
                },
            },
        }
    if organization is not None:
        filt['organization'] = organization
    if name is not None:
        filt['versions'] = {
            '$elemMatch': {
                'images': {
                    '$elemMatch': {
                        'image_name': name,
                    },
                },
            },
        }
    if toolname is not None:
        filt['toolname'] = toolname
    if description is not None:
        filt['description'] = description
    if author:
        filt['versions'] = {
            '$elemMatch': {
                'author': {
                    '$in': [author],
                },
            },
        }
    if checker is not None:
        filt['has_checker'] = checker

    # fetch data
    db_collection = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['objects'].client
    )
    records = db_collection.find(
        filter=filt,
        projection={"_id": False},
    )

    # TODO: create dummy headers; implement pagination later
    headers = {}
    headers['next_page'] = None
    headers['last_page'] = None
    headers['self_link'] = None
    headers['current_offset'] = None
    headers['current_limit'] = None

    return list(records), '200', headers


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
