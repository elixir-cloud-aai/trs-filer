"""" Controllers for TRS endpoints """

import logging
from foca.utils.logging import log_traffic

logger = logging.getLogger(__name__)


@log_traffic
def toolsIdGet(id):
    """ List one specific tool, acts as an anchor for self references. """
    return {}


@log_traffic
def toolsIdVersionsGet(id):
    """ List versions of a tool. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdGet(
    id,
    version_id,
):
    """
    List one specific tool version, acts
    as an anchor for self references.
    """
    return {}


@log_traffic
def toolsGet(
    id,
    alias,
    toolClass,
    registry,
    organization,
    name,
    toolname,
    description,
    author,
    checker,
):
    """ List all tools. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorGet(
    type,
    id,
    version_id,
):
    """ Get the tool descriptor for the specified tool. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorRelativePathGet(
    type,
    id,
    version_id,
    relative_path,
):
    """ Get additional tool descriptor files relative to the main file. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdTypeTestsGet(
    type,
    id,
    version_id,
):
    """ Get a list of test JSONs. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdTypeFilesGet(
    type,
    id,
    version_id,
    format,
):
    """ Get a list of objects that contain the relative path and file type. """
    return {}


@log_traffic
def toolsIdVersionsVersionIdContainerfileGet(
    id,
    version_id
):
    """ Get the container specification(s) for the specified image. """
    return {}


@log_traffic
def toolClassesGet():
    """ List all tool types. """
    return {}


@log_traffic
def getServiceInfo():
    """ Show information about this service. """
    return {}
