""""Controllers for TRS endpoints."""

import logging
from typing import (Optional, Dict, List, Tuple)

from flask import (request, current_app)
from foca.utils.logging import log_traffic

from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)
from trs_filer.ga4gh.trs.endpoints.register_objects import (
    RegisterTool,
    RegisterToolVersion,
)
from trs_filer.ga4gh.trs.endpoints.register_tool_classes import (
    RegisterToolClass
)
from trs_filer.ga4gh.trs.endpoints.service_info import (
    RegisterServiceInfo,
)

logger = logging.getLogger(__name__)


@log_traffic
def toolsIdGet(
    id: str
) -> Dict:
    """List one specific tool, acts as an anchor for self references.

    Args:
        id: Tool identifier.

    Returns:
        Tool object dict corresponding given tool id.

    Raise:
        NotFound if no object mapping with given id present.
    """
    db_coll_tools = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['tools'].client
    )
    obj = db_coll_tools.find_one({"id": id})
    if obj is None:
        raise NotFound
    del obj["_id"]
    return obj


@log_traffic
def toolsIdVersionsGet(
    id: str
) -> List[Dict]:
    """List versions of a tool.

    Args:
        id: Tool identifier.

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
        id: Tool identifier.
        version_id: Tool version identifier.

    Returns:
        Specific version dict of the given tool.

    Raises:
        NotFound if no tool object present for give id mapping. Also, if
        version with given id not found.
    """
    db_coll_tools = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['tools'].client
    )
    proj = {
        '_id': False,
        'versions': {
            '$elemMatch': {
                'id': version_id,
            },
        },
    }
    data = db_coll_tools.find_one(
        filter={'id': id},
        projection=proj,
    )
    try:
        return data['versions'][0]
    except (KeyError, TypeError):
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
        id: Return only entries with the given identifier.
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
        filt['name'] = toolname
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
    db_coll_tools = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['tools'].client
    )
    records = db_coll_tools.find(
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
) -> List[Dict]:
    """Get the container specification(s) for the specified tool version.

    Args:
        id: Tool identifier.
        version_id:  Tool version identifier.

    Returns:
        List of wrapped containerfile objects.
    """
    db_coll_files = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['files'].client
    )
    proj = {
        '_id': False,
        'versions': {
            '$elemMatch': {
                'id': version_id,
                'files': {
                    '$elemMatch': {
                        'toolFile.file_type': 'CONTAINERFILE',
                    },
                },
            },
        },
    }
    data = db_coll_files.find_one(
        filter={'id': id},
        projection=proj,
    )
    try:
        data = data['versions'][0]
        ret = [
            d['fileWrapper'] for d in data['files']
            if d['toolFile']['file_type'] == 'CONTAINERFILE'
        ]
    except (IndexError, KeyError, TypeError):
        raise NotFound
    return ret


@log_traffic
def toolClassesGet(
) -> List:
    """List all tool classes.

    Returns:
        List of tool class objects.
    """
    db_collection_class = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['toolclasses'].client
    )
    records = db_collection_class.find(
        filter={},
        projection={"_id": False},
    )
    return list(records)


@log_traffic
def getServiceInfo() -> Dict:
    """Show information about this service.

    Returns:
        An empty 201 response with headers.
    """
    service_info = RegisterServiceInfo()
    return service_info.get_service_info()


@log_traffic
def postServiceInfo() -> Tuple[None, str, Dict]:
    """Show information about this service.

    Returns:
        An empty 201 response with headers.
    """
    service_info = RegisterServiceInfo()
    headers = service_info.set_service_info_from_app_context(data=request.json)
    return None, '201', headers


@log_traffic
def postTool() -> str:
    """Add tool with an auto-generated ID.

    Returns:
        Identifier of created tool.
    """
    tool = RegisterTool(data=request.json)
    tool.register_metadata()
    return tool.data['id']


@log_traffic
def putTool(
    id: str,
) -> str:
    """Add/replace tool with a user-supplied ID.

    Args:
        id: Identifier of tool to be created/updated.

    Returns:
        Identifier of created/updated tool.
    """
    tool = RegisterTool(
        data=request.json,
        id=id,
    )
    tool.register_metadata()
    return tool.data['id']


@log_traffic
def deleteTool(
    id: str,
) -> str:
    """Delete tool.

    Args:
        id: Identifier of tool to be deleted.

    Returns:
        Previous identifier of deleted tool.
    """
    db_coll_tools = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['tools'].client
    )
    db_coll_files = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['files'].client
    )
    del_obj_tools = db_coll_tools.delete_one({'id': id})
    del_obj_files = db_coll_files.delete_one({'id': id})
    if (
        del_obj_tools.deleted_count and
        del_obj_files.deleted_count
    ):
        return id
    else:
        raise NotFound


@log_traffic
def postToolVersion(
    id: str,
) -> str:
    """Add tool version with an auto-generated ID.

    Args:
        id: Identifier of tool to be modified.

    Returns:
        Identifier of created tool version.
    """
    version = RegisterToolVersion(
        id=id,
        data=request.json,
    )
    version.register_metadata()
    return version.data['id']


@log_traffic
def putToolVersion(
    id: str,
    version_id: str,
) -> str:
    """Add/replace tool version with a user-supplied ID.

    Args:
        id: Identifier of tool to be modified.
        id: Identifier of tool to be created/updated.

    Returns:
        Identifier of created tool version.
    """
    version = RegisterToolVersion(
        id=id,
        version_id=version_id,
        data=request.json,
    )
    version.register_metadata()
    return version.data['id']


@log_traffic
def deleteToolVersion(
    id: str,
    version_id: str,
) -> str:
    """Delete tool version.

    Args:
        id: Identifier of tool to be modified.
        version_id: Identifier of tool version to be deleted.

    Returns:
        Previous identifier of deleted tool version. Note that a
        `BadRequest/400` error response is returned if attempting to delete
        the only remaining tool version.
    """
    db_coll_tools = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['tools'].client
    )
    db_coll_files = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['files'].client
    )

    # do not allow deleting the last version
    # TODO: race condition
    versions = toolsIdVersionsGet.__wrapped__(id)
    if len(versions) == 1:
        if version_id in [v.get('id', None) for v in versions]:
            logger.error("Will not delete only remaining tool version.")
            raise BadRequest
        else:
            raise NotFound

    del_ver_tools = db_coll_tools.update_one(
        filter={'id': id},
        update={
            '$pull': {
                'versions': {'id': version_id},
            },
        },
    )
    del_ver_files = db_coll_files.update_one(
        filter={'id': id},
        update={
            '$pull': {
                'versions': {'id': version_id},
            },
        },
    )
    if (
        del_ver_tools.modified_count and
        del_ver_files.modified_count
    ):
        return version_id
    else:
        raise InternalServerError


@log_traffic
def postToolClass() -> str:
    """Add tool class with an auto-generated ID.

    Returns:
        Identifier of created tool class.
    """
    tool_class = RegisterToolClass(data=request.json)
    tool_class.register_metadata()
    return tool_class.data['id']


@log_traffic
def putToolClass(
    id: str,
) -> str:
    """Add tool class with a user-supplied ID.

    Args:
        id: Identifier of tool class to be created/updated.

    Returns:
        Identifier of created/updated tool class.
    """
    tool_class = RegisterToolClass(
        data=request.json,
        id=id,
    )
    tool_class.register_metadata()
    print(tool_class.data['id'])
    return tool_class.data['id']


@log_traffic
def deleteToolClass(
    id: str,
) -> str:
    """Delete tool class.

    Args:
        id: Identifier of tool class to be deleted.

    Returns:
        Previous identifier of deleted tool class. Note that a `BadRequest/400`
        error response is returned if attempting to delete a tool class that
        is associated with any tool.
    """
    db_coll_classes = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['toolclasses'].client
    )

    # do not allow deleting tool class associated with tool
    if id in [t['toolclass']['id'] for t in toolsGet.__wrapped__()[0]]:
        raise BadRequest

    if db_coll_classes.delete_one({'id': id}).deleted_count:
        return id
    else:
        raise NotFound
