"""Controllers for TRS endpoints."""

import inspect
from io import BytesIO
import logging
from typing import Any
from urllib.parse import unquote
from zipfile import ZIP_DEFLATED, ZipFile

from flask import Response, request, send_file
from foca.utils.logging import log_traffic

from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
    RemoteFileError,
)
from trs_filer.ga4gh.trs.endpoints.register_objects import (
    RegisterTool,
    RegisterToolVersion,
)
from trs_filer.ga4gh.trs.endpoints.register_tool_classes import RegisterToolClass
from trs_filer.remote_files import fetch_remote_file
from trs_filer.utils import get_collection, get_custom_config

logger = logging.getLogger(__name__)

# Default and maximum number of tools per page of `GET /tools` (the spec's
# default limit)
MAX_LIMIT = 1000


@log_traffic
def toolsIdGet(id: str) -> dict[str, Any]:
    """List one specific tool, acts as an anchor for self references.

    Args:
        id: Tool identifier.

    Returns:
        Tool object dict corresponding given tool id.

    Raises:
        NotFound: No tool with the given identifier exists.
    """
    db_coll_tools = get_collection("tools")
    obj = db_coll_tools.find_one({"id": id})
    if obj is None:
        raise NotFound
    del obj["_id"]

    if "versions" in obj:
        for _version in obj["versions"]:
            if "files" in _version:
                del _version["files"]
    return obj


@log_traffic
def toolsIdVersionsGet(id: str) -> list[dict[str, Any]]:
    """List versions of a tool.

    Args:
        id: Tool identifier.

    Returns:
        List of version dicts corresponding given tool id.

    Raises:
        NotFound: No tool with the given identifier exists.
    """
    obj = inspect.unwrap(toolsIdGet)(id)
    return obj["versions"]


@log_traffic
def toolsIdVersionsVersionIdGet(
    id: str,
    version_id: str,
) -> dict[str, Any]:
    """List one specific tool version, acts as an anchor for self references.

    Args:
        id: Tool identifier.
        version_id: Tool version identifier.

    Returns:
        Specific version dict of the given tool.

    Raises:
        NotFound: No tool with the given identifier exists, or it has no
            version with the given identifier.
    """
    db_coll_tools = get_collection("tools")
    proj = {
        "_id": False,
        "versions": {
            "$elemMatch": {
                "id": version_id,
            },
        },
    }
    data = db_coll_tools.find_one(
        filter={"id": id},
        projection=proj,
    )
    if data is None:
        raise NotFound
    try:
        version = data["versions"][0]
        if version and "files" in version:
            del version["files"]
        return version
    except (KeyError, TypeError) as exc:
        raise NotFound from exc


@log_traffic
def toolsGet(
    id: str | None = None,
    alias: str | None = None,
    toolClass: str | None = None,
    descriptorType: str | None = None,
    registry: str | None = None,
    organization: str | None = None,
    name: str | None = None,
    toolname: str | None = None,
    description: str | None = None,
    author: str | None = None,
    checker: bool | None = None,
    limit: int = MAX_LIMIT,
    offset: str | None = None,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
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
        limit: Number of records when paginating results; at most
            `MAX_LIMIT`, larger limits are reduced to it.
        offset: Start index when paginating results.

    Returns:
        List of all tools consistent with all filters, if specified, the
        status code and the pagination headers: `self_link`,
        `current_offset`, `current_limit` (after reducing it to `MAX_LIMIT`),
        `last_page` (the page in the sequence of pages from `offset` that has
        the last tool; if `offset` is beyond the last tool, the last page of
        the sequence from 0) and `next_page` (only if there are more tools).

    Raises:
        BadRequest: The offset is not a non-negative integer, or the limit is
            below 1.
    """
    # set filters; those of versions apply to the same version, those of
    # images to the same image of that version
    filt: dict[str, Any] = {}
    if id is not None:
        filt["id"] = id
    if alias is not None:
        filt["aliases"] = alias
    if toolClass is not None:
        filt["toolclass.name"] = toolClass
    if organization is not None:
        filt["organization"] = organization
    if toolname is not None:
        filt["name"] = toolname
    if description is not None:
        filt["description"] = description
    if checker is not None:
        filt["has_checker"] = checker
    image_filt: dict[str, Any] = {}
    if registry is not None:
        image_filt["registry_host"] = registry
    if name is not None:
        image_filt["image_name"] = name
    version_filt: dict[str, Any] = {}
    if descriptorType:
        version_filt["descriptor_type"] = descriptorType
    if author:
        version_filt["author"] = author
    if image_filt:
        version_filt["images"] = {"$elemMatch": image_filt}
    if version_filt:
        filt["versions"] = {"$elemMatch": version_filt}

    # validate pagination
    try:
        offset_int = 0 if offset is None else int(offset)
    except ValueError as exc:
        logger.error("Offset '%s' is not an integer.", offset)
        raise BadRequest from exc
    if offset_int < 0 or limit < 1:
        logger.error("Invalid offset %s or limit %s.", offset_int, limit)
        raise BadRequest
    limit = min(limit, MAX_LIMIT)

    # fetch data
    db_coll_tools = get_collection("tools")
    total = db_coll_tools.count_documents(filter=filt)
    cursor = (
        db_coll_tools.find(
            filter=filt,
            projection={"_id": False},
        )
        # Sort by object ID (+/- oldest to newest)
        .sort("_id", 1)
        .skip(offset_int)
        .limit(limit)
    )

    records = list(cursor)
    for record in records:
        if "versions" in record:
            for _version in record["versions"]:
                if "files" in _version:
                    del _version["files"]

    # links to pages; the last page is the one with the last tool, in steps
    # of `limit` from the offset (as `next_page`), or else from 0
    start = offset_int if offset_int < total else 0
    last_offset = start + max(total - 1 - start, 0) // limit * limit
    headers: dict[str, Any] = {
        "last_page": f"{request.base_url}?offset={last_offset}&limit={limit}",
        "self_link": f"{request.url}",
        "current_offset": str(offset_int),
        "current_limit": limit,
    }
    if offset_int + limit < total:
        headers["next_page"] = (
            f"{request.base_url}?offset={offset_int + limit}&limit={limit}"
        )

    return records, 200, headers


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorGet(
    type: str,
    id: str,
    version_id: str,
) -> dict[str, Any]:
    """Get the tool descriptor for the specified tool.

    Args:
        type: The output type of the descriptor. Allowable values include
            "CWL", "WDL", "NFL", "GALAXY".
        id: Tool identifier.
        version_id: Identifier to the tool version of the given tool `id`.

    Returns:
        The tool descriptor. Plain types return the bare descriptor while the
        "non-plain" types return a descriptor wrapped with metadata.

    Raises:
        BadRequest: The descriptor type is invalid.
        NotFound: The tool version or its primary descriptor of the given
            type does not exist.
    """
    validate_descriptor_type(type=type)
    ret: dict[str, Any] = {}
    db_coll_tools = get_collection("tools")
    proj = {
        "_id": False,
        "versions": {
            "$elemMatch": {
                "id": version_id,
            },
        },
    }
    data = db_coll_tools.find(
        filter={"id": id},
        projection=proj,
    )
    try:
        version_files_data = data[0]["versions"][0]["files"]
        for _d in version_files_data:
            if (
                _d["tool_file"]["file_type"] == "PRIMARY_DESCRIPTOR"
                and _d["type"] == type
            ):
                ret = _d["file_wrapper"]
    except (IndexError, KeyError, TypeError) as exc:
        raise NotFound from exc
    if not ret:
        raise NotFound
    return ret


@log_traffic
def toolsIdVersionsVersionIdTypeDescriptorRelativePathGet(
    type: str,
    id: str,
    version_id: str,
    relative_path: str,
) -> dict[str, Any]:
    """Get additional tool descriptor files relative to the main file.

    Args:
        type: The output type of the descriptor. Examples of allowable
            values are "CWL", "WDL", "NFL", "GALAXY".
        id: Tool identifier.
        version_id: Tool version identifier.
        relative_path: A relative path to the additional file (same
            directory or subdirectories), for example 'foo.cwl' would return
            a 'foo.cwl' from the same directory as the main descriptor. Needs
            to be percent/url encoded/quoted.

    Returns:
        Additional files associated with a given descriptor type of a given
        tool version.

    Raises:
        BadRequest: The descriptor type is invalid.
        NotFound: The tool version or a file with the given path and type
            does not exist.
    """
    logger.debug("Encoded relative path: '%s'", relative_path)
    relative_path = unquote(relative_path)
    logger.debug("Decoded relative path: '%s'", relative_path)
    ret: dict[str, Any] = {}
    validate_descriptor_type(type=type)
    db_coll_tools = get_collection("tools")
    proj = {
        "_id": False,
        "versions": {
            "$elemMatch": {
                "id": version_id,
            },
        },
    }
    data = db_coll_tools.find(
        filter={"id": id},
        projection=proj,
    )

    file_types = [
        "OTHER",
        "TEST_FILE",
        "PRIMARY_DESCRIPTOR",
        "SECONDARY_DESCRIPTOR",
    ]
    try:
        version_data = data[0]["versions"][0]["files"]
        for _d in version_data:
            if (
                _d["tool_file"]["path"] == relative_path
                and _d["tool_file"]["file_type"] in file_types
                and _d["type"] == type
            ):
                ret = _d["file_wrapper"]
    except (IndexError, KeyError, TypeError) as exc:
        raise NotFound from exc
    if not ret:
        raise NotFound
    return ret


@log_traffic
def toolsIdVersionsVersionIdTypeTestsGet(
    type: str,
    id: str,
    version_id: str,
) -> list[dict[str, Any]]:
    """Get a list of test JSONs.

    Args:
        type: The output type of the descriptor. Examples of allowable
            values are "CWL", "WDL", "NFL", "GALAXY".
        id: Tool identifier.
        version_id: Tool version identifier.

    Returns:
        List of JSONs associated with a given descriptor type of a given
        tool version.

    Raises:
        BadRequest: The descriptor type is invalid.
        NotFound: The tool version or test files of the given type do not
            exist.
    """
    validate_descriptor_type(type=type)

    db_coll_tools = get_collection("tools")

    proj = {
        "_id": False,
        "versions": {
            "$elemMatch": {
                "id": version_id,
                "files": {
                    "$elemMatch": {
                        "type": type,
                        "tool_file.file_type": "TEST_FILE",
                    },
                },
            },
        },
    }

    data = db_coll_tools.find(
        filter={"id": id},
        projection=proj,
    )

    try:
        ret_array = []
        version_data = data[0]["versions"][0]["files"]
        for _d in version_data:
            if _d["tool_file"]["file_type"] == "TEST_FILE" and _d["type"] == type:
                ret_array.append(_d["file_wrapper"])
    except (IndexError, KeyError, TypeError) as exc:
        raise NotFound from exc
    return ret_array


@log_traffic
def toolsIdVersionsVersionIdTypeFilesGet(
    type: str,
    id: str,
    version_id: str,
    format: str | None = None,
) -> list[dict[str, Any]] | Response:
    """Get the tool_file specification(s) for the specified tool version.

    Args:
        type: The output type of the descriptor. Examples of allowable
            values are "CWL", "WDL", "NFL", "GALAXY".
        id: Tool identifier.
        version_id: Tool version identifier.
        format: `zip` to get the files as a ZIP archive instead of their
            specifications.

    Returns:
        List of file JSON responses, or, for format `zip`, a response with
        the ZIP archive of the files.

    Raises:
        BadRequest: The descriptor type is invalid.
        InternalServerError: The ZIP archive could not be created.
        NotFound: The tool version does not exist, or, for format `zip`, the
            content of a file is not available.
    """
    validate_descriptor_type(type=type)
    db_coll_tools = get_collection("tools")
    proj = {
        "_id": False,
        "versions": {"$elemMatch": {"id": version_id}},
    }
    data = db_coll_tools.find_one(
        filter={"id": id},
        projection=proj,
    )

    file_types = [
        "OTHER",
        "TEST_FILE",
        "PRIMARY_DESCRIPTOR",
        "SECONDARY_DESCRIPTOR",
    ]
    if data is None:
        raise NotFound
    try:
        version = data["versions"][0]
        selected_files = [
            d
            for d in version["files"]
            if d["type"] == type and d["tool_file"]["file_type"] in file_types
        ]
        ret = [d["tool_file"] for d in selected_files]
    except (IndexError, KeyError, TypeError) as exc:
        raise NotFound from exc

    if format == "zip":
        try:
            mem_zip = BytesIO()
            with ZipFile(mem_zip, mode="w", compression=ZIP_DEFLATED) as zf:
                for file_entry in selected_files:
                    path_in_zip = file_entry["tool_file"]["path"]
                    wrapper = file_entry.get("file_wrapper", {})
                    content_bytes = None
                    if "content" in wrapper and wrapper["content"] is not None:
                        content = wrapper["content"]
                        if isinstance(content, bytes):
                            content_bytes = content
                        elif isinstance(content, str):
                            content_bytes = content.encode("utf-8")
                        else:
                            # Fallback: convert to string then encode
                            content_bytes = str(content).encode("utf-8")
                    elif wrapper.get("url"):
                        try:
                            content_bytes = fetch_remote_file(
                                url=wrapper["url"],
                                config=get_custom_config().remote_files,
                            ).content
                        except RemoteFileError as exc:
                            raise NotFound from exc
                    else:
                        # No content available
                        raise NotFound

                    # Ensure we have bytes to write
                    if content_bytes is None:
                        raise NotFound
                    zf.writestr(path_in_zip, content_bytes)
            mem_zip.seek(0)
            download_name = f"{id}_{version_id}_{type}.zip"
            return send_file(
                mem_zip,
                mimetype="application/zip",
                as_attachment=True,
                download_name=download_name,
            )
        except NotFound:
            raise
        except Exception as exc:
            raise InternalServerError from exc

    return ret


@log_traffic
def toolsIdVersionsVersionIdContainerfileGet(
    id: str,
    version_id: str,
) -> list[dict[str, Any]]:
    """Get the container specification(s) for the specified tool version.

    Args:
        id: Tool identifier.
        version_id: Tool version identifier.

    Returns:
        List of wrapped containerfile objects.

    Raises:
        NotFound: The tool version or its containerfiles do not exist.
    """
    db_coll_tools = get_collection("tools")
    proj = {
        "_id": False,
        "versions": {"$elemMatch": {"id": version_id}},
    }
    data = db_coll_tools.find_one(
        filter={"id": id},
        projection=proj,
    )
    if data is None:
        raise NotFound
    try:
        version = data["versions"][0]
        ret = [
            d["file_wrapper"]
            for d in version["files"]
            if d["tool_file"]["file_type"] == "CONTAINERFILE"
        ]
    except (IndexError, KeyError, TypeError) as exc:
        raise NotFound from exc
    if not ret:
        raise NotFound
    return ret


@log_traffic
def toolClassesGet() -> list[dict[str, Any]]:
    """List all tool classes.

    Returns:
        List of tool class objects.
    """
    db_collection_class = get_collection("toolclasses")
    records = db_collection_class.find(
        filter={},
        projection={"_id": False},
    )
    return list(records)


@log_traffic
def postTool() -> str:
    """Add tool with an auto-generated ID.

    Returns:
        Identifier of created tool.

    Raises:
        BadRequest: The tool is invalid, e.g., its version identifiers are
            duplicated or the files of a version are invalid, or its tool
            class does not exist while tool classes are validated.
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
        RemoteFileError: The content of a file could not be retrieved from its
            URL.
    """
    tool = RegisterTool(data=request.json)
    tool.register_metadata()
    return tool.data["id"]


@log_traffic
def putTool(
    id: str,
) -> str:
    """Add/replace tool with a user-supplied ID.

    Args:
        id: Identifier of tool to be created/updated.

    Returns:
        Identifier of created/updated tool.

    Raises:
        BadRequest: The tool is invalid, e.g., its version identifiers are
            duplicated or the files of a version are invalid, or its tool
            class does not exist while tool classes are validated.
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
        RemoteFileError: The content of a file could not be retrieved from its
            URL.
    """
    tool = RegisterTool(
        data=request.json,
        id=id,
    )
    tool.register_metadata()
    return tool.data["id"]


@log_traffic
def deleteTool(
    id: str,
) -> str:
    """Delete tool.

    Args:
        id: Identifier of tool to be deleted.

    Returns:
        Previous identifier of deleted tool.

    Raises:
        NotFound: No tool with the given identifier exists.
    """
    db_coll_tools = get_collection("tools")
    del_obj_tools = db_coll_tools.delete_one({"id": id})

    if del_obj_tools.deleted_count:
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

    Raises:
        BadRequest: The files of the version are invalid.
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
        NotFound: No tool with the given identifier exists.
        RemoteFileError: The content of a file could not be retrieved from its
            URL.
    """
    version = RegisterToolVersion(
        id=id,
        data=request.json,
    )
    version.register_metadata()
    return version.data["id"]


@log_traffic
def putToolVersion(
    id: str,
    version_id: str,
) -> str:
    """Add/replace tool version with a user-supplied ID.

    Args:
        id: Identifier of tool to be modified.
        version_id: Identifier of tool version to be created/updated.

    Returns:
        Identifier of created tool version.

    Raises:
        BadRequest: The files of the version are invalid.
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
        NotFound: No tool with the given identifier exists.
        RemoteFileError: The content of a file could not be retrieved from its
            URL.
    """
    version = RegisterToolVersion(
        id=id,
        version_id=version_id,
        data=request.json,
    )
    version.register_metadata()
    return version.data["id"]


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
        Previous identifier of deleted tool version.

    Raises:
        InternalServerError: The tool version could not be deleted.
        NotFound: No tool with the given identifier and version exists.
    """
    db_coll_tools = get_collection("tools")

    filt = {
        "id": id,
        "versions.id": version_id,
    }
    update = {
        "$pull": {
            "versions": {"id": version_id},
        },
    }
    del_ver_tools = db_coll_tools.update_one(
        filter=filt,
        update=update,
    )

    if not del_ver_tools.matched_count:
        raise NotFound
    elif not del_ver_tools.modified_count:
        raise InternalServerError
    else:
        return version_id


@log_traffic
def postToolClass() -> str:
    """Add tool class with an auto-generated ID.

    Returns:
        Identifier of created tool class.

    Raises:
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
    """
    tool_class = RegisterToolClass(data=request.json)
    tool_class.register_metadata()
    return tool_class.data["id"]


@log_traffic
def putToolClass(
    id: str,
) -> str:
    """Add tool class with a user-supplied ID.

    Args:
        id: Identifier of tool class to be created/updated.

    Returns:
        Identifier of created/updated tool class.

    Raises:
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
    """
    tool_class = RegisterToolClass(
        data=request.json,
        id=id,
    )
    tool_class.register_metadata()
    return tool_class.data["id"]


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

    Raises:
        BadRequest: The tool class is associated with a tool.
        NotFound: No tool class with the given identifier exists.
    """
    db_coll_classes = get_collection("toolclasses")

    # do not allow deleting tool class associated with tool
    if get_collection("tools").find_one({"toolclass.id": id}) is not None:
        logger.error("Tool class '%s' is used by tools.", id)
        raise BadRequest

    if db_coll_classes.delete_one({"id": id}).deleted_count:
        return id
    else:
        raise NotFound


def validate_descriptor_type(type: str) -> None:
    """Validate tool descriptor type.

    Args:
        type: Descriptor type, e.g., "NFL".

    Raises:
        BadRequest: Provided descriptor type is invalid.
    """
    valid_types = [f"PLAIN_{t}" for t in RegisterToolVersion.descriptor_types]
    valid_types += RegisterToolVersion.descriptor_types

    if type not in valid_types:
        logger.error("Specified type '%s' not among valid types: %s", type, valid_types)
        raise BadRequest
