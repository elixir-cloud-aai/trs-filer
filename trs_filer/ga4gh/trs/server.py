""""Controllers for TRS endpoints."""

from typing import (Optional, Dict, List)

from flask import (current_app, request, Response)
from foca.utils.logging import log_traffic

from trs_filer.ga4gh.trs.endpoints.register_tools import (
    RegisterObject,
)
from trs_filer.errors.exceptions import NotFound
from trs_filer.app import logger


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
        logger.info(f"Tool object mapping for id:{id} cannot be found.")
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

    Raise:
        NotFound if no object mapping with given id present.
    """

    db_collection = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['objects'].client
    )

    obj = db_collection.find_one({"id": id})

    if not obj:
        logger.info(f"Tool object mapping for id:{id} cannot be found.")
        raise NotFound

    return obj["versions"]


@log_traffic
def toolsIdVersionsVersionIdGet(
    id: str,
    version_id: str,
) -> Dict:
    """
    List one specific tool version, acts
    as an anchor for self references.

    Args:
        id: A unique identifier of the tool.
        version_id: Specific version corresponding tool version.

    Returns:
        Specific version dict of the given tool.

    Raises:
        NotFound if no tool object present.
        Also, if version with given id not found.
    """

    db_collection = (
        current_app.config['FOCA'].db.dbs['trsStore']
        .collections['objects'].client
    )

    obj = db_collection.find_one({"id": id})

    if not obj:
        logger.info(f"Tool object mapping for id:{id} cannot be found.")
        raise NotFound

    for version in obj["versions"]:
        if version['id'] == version_id:
            return version

    logger.info(
        f"Version mapping for version_id: {version_id} cannot "
        "be found for tool object with id: {id}."
    )
    raise NotFound


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
    offset: Optional[int] = None
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
    # filter_list = []
    
    # if id is not None:
    #     filter_list.append({"id": id})
    
    # if organization is not None:
    #     filter_list.append({"organization": organization})
    
    # if toolClass is not None:
    #     filter_list.append({"toolClass": toolClass})
    
    # if description is not None:
    #     filter_list.append({"description": description})

    # if toolname is not None:
    #     filter_list.append({"name": toolname})

    # # add support for registry, name, author and checker.

    # # Apply filter 
    # db_collection = (
    #     current_app.config['FOCA'].db.dbs['trsStore']
    #     .collections['objects'].client
    # )
    
    # if filter_list:
    #     records = db_collection.find(
    #         {"$and": filter_list},
    #         {"_id": False}
    #     )
    # else:
    #     records = db_collection.find({}, {"_id": False})
    # records = list(records)
    
    # if alias is not None:
    #     records = [rec for rec in records if alias in rec["aliases"]]

    # if offset:
    #     records = records[offset:]
    # if limit:
    #     records = records[:limit]
    
    # response = Response(records)
    # response.headers['next_page'] = None
    # response.headers['last_page'] = None
    # response.headers['self_link'] = None
    # response.headers['current_offset'] = None
    # response.headers['current_limit'] = None
    # return response
    return []


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorGet(
    type: str,
    id: str,
    version_id: str,
) -> Dict:
    """ Get the tool descriptor for the specified tool. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorRelativePathGet(
    type: str,
    id: str,
    version_id: str,
    relative_path: str,
) -> Dict:
    """ Get additional tool descriptor files relative to the main file. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdTypeTestsGet(
    type: str,
    id: str,
    version_id: str,
) -> List:
    """ Get a list of test JSONs. """
    return []


@log_traffic
def toolsIdVersionsVersionIdTypeFilesGet(
    type: str,
    id: str,
    version_id: str,
    format: Optional[str] = None,
) -> List:
    """ Get a list of objects that contain the relative path and file type. """
    return []


@log_traffic
def toolsIdVersionsVersionIdContainerfileGet(
    id: str,
    version_id: str,
) -> List:
    """ Get the container specification(s) for the specified image. """
    return []


@log_traffic
def toolClassesGet() -> List:
    """ List all tool types. """
    return []


@log_traffic
def getServiceInfo() -> Dict:
    """ Show information about this service. """
    return {}


@log_traffic
def addTool() -> Dict:
    """ Add new tool object to the database. """
    tool_creator = RegisterObject(request)
    tool = tool_creator.register_object()
    return tool['id']
