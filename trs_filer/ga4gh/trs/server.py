""""Controllers for TRS endpoints."""

from typing import (Optional, Dict, List)

from flask import (current_app, request)
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
        id: Tool id to be extracted.

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
        id: Tool id.

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
        id: Tool id.
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
) -> List:
    """ List all tools. """
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
