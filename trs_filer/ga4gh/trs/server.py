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
    limit: int = 1000,  # default as per specs
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
        limit: Number of records when paginating results.
        offset: Start index when paginating results.

    Returns:
        List of all tools consistent with all filters, if specified, the
        status code and the pagination headers.
    """
    # set filters
    filt: dict[str, Any] = {}
    if id is not None:
        filt["id"] = id
    if alias is not None:
        filt["aliases"] = {
            "$in": [alias],
        }
    if toolClass is not None:
        filt["toolclass.name"] = toolClass
    if descriptorType:
        filt["versions"] = {
            "$elemMatch": {
                "descriptor_type": {
                    "$in": [descriptorType],
                },
            },
        }
    if registry is not None:
        filt["versions"] = {
            "$elemMatch": {
                "images": {
                    "$elemMatch": {
                        "registry_host": registry,
                    },
                },
            },
        }
    if organization is not None:
        filt["organization"] = organization
    if name is not None:
        filt["versions"] = {
            "$elemMatch": {
                "images": {
                    "$elemMatch": {
                        "image_name": name,
                    },
                },
            },
        }
    if toolname is not None:
        filt["name"] = toolname
    if description is not None:
        filt["description"] = description
    if author:
        filt["versions"] = {
            "$elemMatch": {
                "author": {
                    "$in": [author],
                },
            },
        }
    if checker is not None:
        filt["has_checker"] = checker

    logger.info("offset %s limit %s ", offset, limit)
    # offset validation
    if offset is None:
        offset_int = 0
    elif int(offset) < 0:
        return [], 422, {}
    else:
        offset_int = int(offset)

    # limit validation
    if int(limit) < 0:
        return [], 422, {}

    # fetch data
    db_coll_tools = get_collection("tools")
    cursor = (
        db_coll_tools.find(
            filter=filt,
            projection={"_id": False},
        )
        .sort(
            # Sort results by descending object ID (+/- oldest to newest)
            "_id",
            1,
        )
        .skip(
            # Skip number of records by given offset
            offset_int
        )
        .limit(
            # Implement page size limit
            limit
        )
    )

    records = list(cursor)
    for record in records:
        if "versions" in record:
            for _version in record["versions"]:
                if "files" in _version:
                    del _version["files"]

    previous_page_url = (
        f"{request.base_url}?offset={max(offset_int - limit, 0)}&limit={limit}"
    )
    next_page_url = f"{request.base_url}?offset={offset_int + limit}&limit={limit}"

    headers: dict[str, Any] = {}
    headers["next_page"] = next_page_url
    headers["last_page"] = previous_page_url
    headers["self_link"] = f"{request.url}"
    headers["current_offset"] = str(offset_int)
    headers["current_limit"] = limit

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
        Previous identifier of deleted tool version. Note that a
        `BadRequest/400` error response is returned if attempting to delete
        the only remaining tool version.

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
    if id in [t["toolclass"]["id"] for t in inspect.unwrap(toolsGet)()[0]]:
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
