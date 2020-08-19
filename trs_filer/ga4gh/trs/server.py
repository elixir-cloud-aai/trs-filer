""""Controllers for TRS endpoints."""

from typing import (Optional, Dict, List)

from flask import request
from foca.utils.logging import log_traffic

from trs_filer.ga4gh.trs.endpoints.registerObjects import (
    CreateToolPostObject,
)


@log_traffic
def toolsIdGet(
    id: str
) -> Dict:
    """ List one specific tool, acts as an anchor for self references. """
    return {}


@log_traffic
def toolsIdVersionsGet(
    id: str
) -> List:
    """ List versions of a tool. """
    return []


@log_traffic
def toolsIdVersionsVersionIdGet(
    id: str,
    version_id: str,
) -> Dict:
    """
    List one specific tool version, acts
    as an anchor for self references.
    """
    return {}


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
    tool_create_instance = CreateToolPostObject(request)
    return tool_create_instance.get_tool_object_data()
