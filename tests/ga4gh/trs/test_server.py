from trs_filer.ga4gh.trs.server import (
    toolsGet,
    toolsIdGet,
    getServiceInfo,
    toolClassesGet,
    toolsIdVersionsGet,
    toolsIdVersionsVersionIdGet,
    toolsIdVersionsVersionIdTypeTestsGet,
    toolsIdVersionsVersionIdTypeFilesGet,
    toolsIdVersionsVersionIdContainerfileGet,
    toolsIdVersionsVersionIdTypeDescriptorGet,
    toolsIdVersionsVersionIdTypeDescriptorRelativePathGet,
)
from typing import (Dict, List)

TEMP_ID = "id"
TEMP_VERSION_ID = "version_id"
TEMP_TYPE = "type"
TEMP_RELATIVE_PATH = "/a/b/c"


def test_toolIdGet():
    """Test for getting tool id.
    """
    res = toolsIdGet.__wrapped__(TEMP_ID)
    assert isinstance(res, Dict)


def test_toolsIdVersionsGet():
    """Test for getting version list for a given tool id.
    """
    res = toolsIdVersionsGet.__wrapped__(TEMP_ID)
    assert isinstance(res, List)


def test_toolsIdVersionsVersionIdGet():
    """Test for getting particular version of a particular
    tool.
    """
    res = toolsIdVersionsVersionIdGet.__wrapped__(
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, Dict)


def test_toolsGet():
    """Test for getting list of tools.
    """
    res = toolsGet.__wrapped__()
    assert isinstance(res, List)


def test_toolsIdVersionsVersionIdTypeDescriptorGet():
    """Test for addional tool descriptor.
    """
    res = toolsIdVersionsVersionIdTypeDescriptorGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, Dict)


def test_toolsIdVersionsVersionIdTypeDescriptorRelativePathGet():
    """Test for addional tool descriptor relative path.
    """
    res = toolsIdVersionsVersionIdTypeDescriptorRelativePathGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID,
        TEMP_RELATIVE_PATH
    )
    assert isinstance(res, Dict)


def test_toolsIdVersionsVersionIdTypeTestsGet():
    """Test for getting test jsons.
    """
    res = toolsIdVersionsVersionIdTypeTestsGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, List)


def test_toolsIdVersionsVersionIdTypeFilesGet():
    """Test for getting list of objects with file path and type.
    """
    res = toolsIdVersionsVersionIdTypeFilesGet.__wrapped__(
        TEMP_TYPE,
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, List)


def test_toolsIdVersionsVersionIdContainerfileGet():
    """Test for getting container specs.
    """
    res = toolsIdVersionsVersionIdContainerfileGet.__wrapped__(
        TEMP_ID,
        TEMP_VERSION_ID
    )
    assert isinstance(res, List)


def test_toolClassesGet():
    """Test for getting tool classes.
    """
    res = toolClassesGet.__wrapped__()
    assert isinstance(res, List)


def test_getServiceInfo():
    """Test get service info.
    """
    res = getServiceInfo.__wrapped__()
    assert isinstance(res, Dict)
