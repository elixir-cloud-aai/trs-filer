"""Controllers for TRS endpoints."""

import inspect
from io import BytesIO
import json
import logging
from typing import Any
from urllib.parse import unquote, urlencode
from zipfile import ZIP_DEFLATED, ZipFile

from flask import Response, after_this_request, request, send_file
from foca.security.access_control import (
    get_current_claims,
    get_current_subject,
    is_permitted,
    is_permitted_for,
)
from foca.utils.logging import escape_log_value, log_traffic
from werkzeug.datastructures import MIMEAccept

from trs_filer.errors.exceptions import (
    Forbidden,
    InternalServerError,
    InvalidRequest,
    NotAcceptable,
    NotFound,
    RemoteFileError,
)
from trs_filer.ga4gh.trs.endpoints.register_objects import (
    TOOL_PROJECTION,
    UPDATED_AT,
    RegisterTool,
    RegisterToolVersion,
    now,
    tool_meta_version_change,
)
from trs_filer.ga4gh.trs.endpoints.register_tool_classes import RegisterToolClass
from trs_filer.ga4gh.trs.permissions import (
    is_usable_id,
    own_tool,
    remove_roles,
    tool_class_exists,
)
from trs_filer.ga4gh.trs.tool_classes import (
    PENDING,
    TOOL_CLASS_PROJECTION,
    may_add_tool_classes,
    own_tools,
    sync_pending_flags,
    tool_classes_pending,
    visible_tool_classes,
    visible_tools,
)
from trs_filer.remote_files import fetch_remote_file
from trs_filer.storage import (
    ObjectMissing,
    file_content,
    plain_redirect,
    releases_objects,
    retries_missing_objects,
    served_wrapper,
)
from trs_filer.utils import get_collection, get_custom_config

logger = logging.getLogger(__name__)

# Default and maximum number of tools per page of `GET /tools` (the spec's
# default limit)
MAX_LIMIT = 1000
# Reasons of `400 Bad Request` for invalid offsets and limits of `GET /tools`
OFFSET_INVALID = "The offset must be a non-negative integer."
LIMIT_INVALID = "The limit must be at least 1."
# Media types of the paths that the specification offers as JSON and plain
# text (`{type}/descriptor`, `{type}/descriptor/{relative_path}`,
# `{type}/tests`): JSON for the descriptor types, plain text for their
# `PLAIN_` forms
JSON_MEDIA_TYPE = "application/json"
PLAIN_MEDIA_TYPE = "text/plain"
# Longest part of `Accept` headers that is logged
MAX_LOGGED_ACCEPT = 200


@log_traffic
def toolsIdGet(id: str) -> dict[str, Any]:
    """List one specific tool, acts as an anchor for self references.

    Args:
        id: Tool identifier.

    Returns:
        Tool object dict corresponding given tool id.

    Raises:
        NotFound: No tool with the given identifier exists, or it is pending
            and the user may not see it (cf.
            `trs_filer.ga4gh.trs.tool_classes.visible_tools()`).
    """
    db_coll_tools = get_collection("tools")
    obj = db_coll_tools.find_one(visible_tools({"id": id}), TOOL_PROJECTION)
    if obj is None:
        raise NotFound

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
        filter=visible_tools({"id": id}),
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
    tags: list[str] | None = None,
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
    parameters are additive. Pending tools are only listed to admins and the
    users with a role on them (cf.
    `trs_filer.ga4gh.trs.tool_classes.visible_tools()`).

    Args:
        id: Return only entries with the given identifier.
        alias: Return only entries with the given alias.
        toolClass: Return only entries with the given subclass name.
        descriptorType: Return only entries with the given descriptor type.
        tags: Return only entries that have all the given tags, of all
            `tags` parameters of the request, if repeated.
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
        The links to pages keep the other query parameters of the request.

    Raises:
        InvalidRequest: The offset is not a non-negative integer, or the
            limit is below 1.
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
    if tags is not None:
        # Connexion keeps only the last of repeated parameters (`explode:
        # false`), so the tags of all of them are taken from the request
        filt["tags"] = {
            "$all": [
                tag
                for value in request.args.getlist("tags")
                for tag in value.split(",")
            ]
        }
    if checker is not None:
        filt["has_checker"] = checker
    image_filt: dict[str, Any] = {}
    if registry is not None:
        image_filt["registry_host"] = registry
    if name is not None:
        image_filt["image_name"] = name
    version_filt: dict[str, Any] = {}
    if descriptorType is not None:
        version_filt["descriptor_type"] = descriptorType
    if author is not None:
        version_filt["author"] = author
    if image_filt:
        version_filt["images"] = {"$elemMatch": image_filt}
    if version_filt:
        filt["versions"] = {"$elemMatch": version_filt}

    # validate pagination
    try:
        offset_int = 0 if offset is None else int(offset)
    except ValueError as exc:
        logger.error("Offset '%s' is not an integer.", escape_log_value(offset))
        raise InvalidRequest(OFFSET_INVALID) from exc
    if offset_int < 0:
        logger.error("Invalid offset %s.", offset_int)
        raise InvalidRequest(OFFSET_INVALID)
    if limit < 1:
        logger.error("Invalid limit %s.", limit)
        raise InvalidRequest(LIMIT_INVALID)
    limit = min(limit, MAX_LIMIT)

    # fetch data
    filt = visible_tools(filt)
    db_coll_tools = get_collection("tools")
    total = db_coll_tools.count_documents(filter=filt)
    cursor = (
        db_coll_tools.find(
            filter=filt,
            projection=TOOL_PROJECTION,
        )
        # Sort by object ID: roughly the order in which tools were added
        # (see `docs/api.md`); stable, so that pages don't overlap
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

    # links to pages, with the other query parameters of the request; the
    # last page is the one with the last tool, in steps of `limit` from the
    # offset (as `next_page`), or else from 0
    query = [
        (key, value)
        for key, value in request.args.items(multi=True)
        if key not in ("offset", "limit")
    ]

    def page_link(page_offset: int) -> str:
        """Get the link to the page from an offset.

        Args:
            page_offset: Offset of the page.

        Returns:
            URL of the page.
        """
        params = urlencode([*query, ("offset", page_offset), ("limit", limit)])
        return f"{request.base_url}?{params}"

    start = offset_int if offset_int < total else 0
    last_offset = start + max(total - 1 - start, 0) // limit * limit
    headers: dict[str, Any] = {
        "last_page": page_link(last_offset),
        "self_link": f"{request.url}",
        "current_offset": str(offset_int),
        "current_limit": limit,
    }
    if offset_int + limit < total:
        headers["next_page"] = page_link(offset_int + limit)

    return records, 200, headers


@log_traffic
@retries_missing_objects
def toolsIdVersionsVersionIdTypeDescriptorGet(
    type: str,
    id: str,
    version_id: str,
) -> dict[str, Any] | Response:
    """Get the tool descriptor for the specified tool.

    Args:
        type: The output type of the descriptor. Allowable values include
            "CWL", "WDL", "NFL", "GALAXY", "SMK", and their `PLAIN_` forms.
        id: Tool identifier.
        version_id: Identifier to the tool version of the given tool `id`.

    Returns:
        The tool descriptor. Plain types return the bare descriptor (as
        `text/plain`) while the "non-plain" types return a descriptor wrapped
        with metadata.

    Raises:
        InvalidRequest: The descriptor type is invalid.
        NotAcceptable: The client doesn't accept the media type of the
            type.
        NotFound: The tool version or its primary descriptor of the given
            type does not exist, or, for plain types, its content is not
            available.
    """
    validate_descriptor_type(type=type)
    file_type, plain = _negotiate_type(type)
    files = _version_files(id=id, version_id=version_id)
    ret: dict[str, Any] = {}
    for _d in files:
        if (
            _d["tool_file"]["file_type"] == "PRIMARY_DESCRIPTOR"
            and _d["type"] == file_type
        ):
            ret = _d
    if not ret:
        raise NotFound
    return _plain_response(ret) if plain else served_wrapper(ret)


@log_traffic
@retries_missing_objects
def toolsIdVersionsVersionIdTypeDescriptorRelativePathGet(
    type: str,
    id: str,
    version_id: str,
    relative_path: str,
) -> dict[str, Any] | Response:
    """Get additional tool descriptor files relative to the main file.

    The relative path arrives percent-decoded (with `/` for `%2F`, as the
    parameter has format `path`). Paths that match no file are decoded
    once more, so that clients that encode paths twice (`%252F`) find them
    too.

    Args:
        type: The output type of the descriptor. Examples of allowable
            values are "CWL", "WDL", "NFL", "GALAXY", "SMK", and their
            `PLAIN_` forms.
        id: Tool identifier.
        version_id: Tool version identifier.
        relative_path: A relative path to the additional file (same
            directory or subdirectories), for example 'foo.cwl' would return
            a 'foo.cwl' from the same directory as the main descriptor;
            percent-encoded (`nested%2Ffoo.cwl`) or not (`nested/foo.cwl`).

    Returns:
        Additional files associated with a given descriptor type of a given
        tool version; for plain types, their bare content (as
        `text/plain`).

    Raises:
        InvalidRequest: The descriptor type is invalid.
        NotAcceptable: The client doesn't accept the media type of the
            type.
        NotFound: The tool version or a file with the given path and type
            does not exist, or, for plain types, its content is not available.
    """
    validate_descriptor_type(type=type)
    file_type, plain = _negotiate_type(type)
    files = _version_files(id=id, version_id=version_id)
    file_types = [
        "OTHER",
        "TEST_FILE",
        "PRIMARY_DESCRIPTOR",
        "SECONDARY_DESCRIPTOR",
    ]
    # The path as it arrives wins over the decoded one (e.g., for files with
    # `%` in their paths), so don't decode it unconditionally
    candidates = [relative_path]
    decoded = unquote(relative_path)
    if decoded != relative_path:
        candidates.append(decoded)
    ret: dict[str, Any] = {}
    for path in candidates:
        for _d in files:
            if (
                _d["tool_file"]["path"] == path
                and _d["tool_file"]["file_type"] in file_types
                and _d["type"] == file_type
            ):
                ret = _d
        if ret:
            logger.debug("Relative path found: '%s'", escape_log_value(path))
            break
    if not ret:
        raise NotFound
    return _plain_response(ret) if plain else served_wrapper(ret)


def _split_plain(type: str) -> tuple[str, bool]:
    """Split a descriptor type into the type of its files and its form.

    Args:
        type: Descriptor type, e.g., `CWL` or `PLAIN_CWL`.

    Returns:
        Type of the files (without the prefix `PLAIN_`) and whether the type
        is a plain one.
    """
    file_type = type.removeprefix("PLAIN_")
    return file_type, file_type != type


def _negotiate_type(type: str) -> tuple[str, bool]:
    """Check that the client accepts the media type of a descriptor type.

    The specification serves descriptor types as JSON (wrapped with
    metadata) and their `PLAIN_` forms as plain text, so the type sets the
    media type, and `Accept` only has to allow it. Parameters of media
    ranges (e.g., `charset`) are ignored, their quality (`q`) is not; no
    `Accept`, or an empty one, accepts any media type. Responses say that
    they depend on `Accept` (`Vary`), also errors.

    Args:
        type: Descriptor type, e.g., `CWL` or `PLAIN_CWL`.

    Returns:
        Type of the files (without the prefix `PLAIN_`) and whether to serve
        them as plain text.

    Raises:
        NotAcceptable: The client doesn't accept the media type of the
            type.
    """
    after_this_request(_vary_accept)
    file_type, plain = _split_plain(type)
    accept = request.accept_mimetypes
    if accept:
        media_type = PLAIN_MEDIA_TYPE if plain else JSON_MEDIA_TYPE
        # Werkzeug matches parameters of media ranges exactly, so that
        # `application/json; charset=utf-8` wouldn't accept JSON; without
        # them, ranges of the same media type count with their highest
        # quality
        ranges = MIMEAccept(
            [(value.split(";", 1)[0].strip(), quality) for value, quality in accept]
        )
        if ranges.best_match([media_type]) is None:
            logger.info(
                "Type '%s' is served as %s, which isn't accepted: %s",
                escape_log_value(type),
                media_type,
                escape_log_value(request.headers.get("Accept", "")[:MAX_LOGGED_ACCEPT]),
            )
            raise NotAcceptable
    return file_type, plain


def _vary_accept(response: Response) -> Response:
    """Tell caches that a response depends on `Accept`.

    Args:
        response: Response.

    Returns:
        The response, with `Accept` in `Vary`.
    """
    response.vary.add("Accept")
    return response


def _version_files(id: str, version_id: str) -> list[dict[str, Any]]:
    """Get the stored files of a tool version.

    Args:
        id: Tool identifier.
        version_id: Tool version identifier.

    Returns:
        Files of the tool version.

    Raises:
        NotFound: The tool version does not exist or has no files.
    """
    data = get_collection("tools").find_one(
        filter=visible_tools({"id": id}),
        projection={
            "_id": False,
            "versions": {"$elemMatch": {"id": version_id}},
        },
    )
    try:
        files: list[dict[str, Any]] = data["versions"][0]["files"]  # type: ignore[index]
    except (IndexError, KeyError, TypeError) as exc:
        raise NotFound from exc
    return files


def _file_content(entry: dict[str, Any]) -> bytes:
    """Get the content of a file, retrieving it from its URL if not stored.

    Args:
        entry: File of a stored version.

    Returns:
        Content of the file; text is encoded as UTF-8.

    Raises:
        InternalServerError: The content could not be read from object
            storage (see `trs_filer.storage.file_content()`).
        NotFound: The file has neither content nor URL, or the file can't be
            retrieved from its URL.
    """
    stored = file_content(entry)
    if stored is not None:
        return stored
    wrapper: dict[str, Any] = entry.get("file_wrapper", {})
    content = wrapper.get("content")
    if content is not None:
        if isinstance(content, bytes):
            return content
        # Text, or else converted to text
        return str(content).encode("utf-8")
    if wrapper.get("url"):
        try:
            return fetch_remote_file(
                url=wrapper["url"],
                config=get_custom_config().remote_files,
            ).content
        except RemoteFileError as exc:
            raise NotFound from exc
    raise NotFound


def _plain_response(entry: dict[str, Any]) -> Response:
    """Get the response with the bare content of a file, for plain types.

    Args:
        entry: File of a stored version.

    Returns:
        Response with the content of the file, as `text/plain` (see
        `_text_response()`), or, for files in object storage with presigned
        URLs, a redirect to the presigned URL of the file's object (see
        `trs_filer.storage.plain_redirect()`).
    """
    redirect = plain_redirect(entry)
    if redirect is not None:
        return redirect
    return _text_response(_file_content(entry))


def _text_response(body: bytes | str) -> Response:
    """Get a `text/plain` response.

    Args:
        body: Body of the response.

    Returns:
        Response with the body, as `text/plain`; browsers are told not to
        guess another media type from the content
        (`X-Content-Type-Options: nosniff`), because the content is supplied
        by whoever registered the files and may look like HTML.
    """
    return Response(
        body,
        mimetype=PLAIN_MEDIA_TYPE,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@log_traffic
@retries_missing_objects
def toolsIdVersionsVersionIdTypeTestsGet(
    type: str,
    id: str,
    version_id: str,
) -> list[dict[str, Any]] | Response:
    """Get a list of test JSONs.

    Args:
        type: The output type of the descriptor. Examples of allowable
            values are "CWL", "WDL", "NFL", "GALAXY", "SMK", and their
            `PLAIN_` forms.
        id: Tool identifier.
        version_id: Tool version identifier.

    Returns:
        List of JSONs associated with a given descriptor type of a given
        tool version; for plain types, the same list as `text/plain`, as
        the specification defines the plain response (an array of file
        wrappers).

    Raises:
        InvalidRequest: The descriptor type is invalid.
        NotAcceptable: The client doesn't accept the media type of the
            type.
        NotFound: The tool version or test files of the given type do not
            exist.
    """
    validate_descriptor_type(type=type)
    file_type, plain = _negotiate_type(type)
    files = _version_files(id=id, version_id=version_id)
    ret = [
        served_wrapper(_d)
        for _d in files
        if _d["tool_file"]["file_type"] == "TEST_FILE" and _d["type"] == file_type
    ]
    if not ret:
        raise NotFound
    return _text_response(json.dumps(ret)) if plain else ret


@log_traffic
@retries_missing_objects
def toolsIdVersionsVersionIdTypeFilesGet(
    type: str,
    id: str,
    version_id: str,
    format: str | None = None,
) -> list[dict[str, Any]] | Response:
    """Get the tool_file specification(s) for the specified tool version.

    Args:
        type: The output type of the descriptor. Examples of allowable
            values are "CWL", "WDL", "NFL", "GALAXY", "SMK".
        id: Tool identifier.
        version_id: Tool version identifier.
        format: `zip` to get the files as a ZIP archive instead of their
            specifications.

    Returns:
        List of file JSON responses, or, for format `zip`, a response with
        the ZIP archive of the files.

    Raises:
        InvalidRequest: The descriptor type is invalid.
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
        filter=visible_tools({"id": id}),
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
                    content = _file_content(file_entry)
                    zf.writestr(path_in_zip, content)
            mem_zip.seek(0)
            download_name = f"{id}_{version_id}_{type}.zip"
            return send_file(
                mem_zip,
                mimetype="application/zip",
                as_attachment=True,
                download_name=download_name,
            )
        # missing objects are retried (`retries_missing_objects()`)
        except (NotFound, ObjectMissing):
            raise
        except Exception as exc:
            raise InternalServerError from exc

    return ret


@log_traffic
@retries_missing_objects
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
        filter=visible_tools({"id": id}),
        projection=proj,
    )
    if data is None:
        raise NotFound
    try:
        version = data["versions"][0]
        ret = [
            served_wrapper(d)
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

    Pending tool classes are only listed to admins and the user who added
    them (cf. `trs_filer.ga4gh.trs.tool_classes.visible_tool_classes()`).

    Returns:
        List of tool class objects.
    """
    db_collection_class = get_collection("toolclasses")
    records = db_collection_class.find(
        filter=visible_tool_classes(),
        projection=TOOL_CLASS_PROJECTION,
    )
    return list(records)


def _check_put(kind: str, id: str, exists: bool) -> bool:
    """Check whether the current user may add or replace an object (`PUT`).

    For `PUT` operations that add objects with the identifier of no object,
    or replace the stored one, and don't enforce policies themselves
    (`x-foca-access-control: false`), as the policies of the paths of objects
    are for their owners: stored objects may be replaced by users whom the
    policies allow the request (e.g., owners of tools, and admins); new
    objects may be added only by users whom the policies allow to add objects
    to the collection (`POST`, e.g., any authenticated user), also if a rule
    for the path of the object would allow the request (e.g., a role left on
    the identifier). Without authentication (`disable_auth`), the request is
    allowed.

    Args:
        kind: Kind of the object, for logs (e.g., `tool`).
        id: Identifier of the object.
        exists: Whether the object is stored.

    Returns:
        Whether the user may replace the object (if stored meanwhile).

    Raises:
        Forbidden: The user may not replace the stored object, or may not
            add a new one.
    """
    # Only requests without authentication have no token
    if not get_current_claims():
        return True
    if exists:
        if is_permitted():
            return True
    elif is_permitted_for(request.path.rsplit("/", 1)[0], "POST"):
        return False
    logger.info(
        "%s '%s' not %s: '%s' may not %s it.",
        kind.capitalize(),
        escape_log_value(id),
        "replaced" if exists else "added",
        escape_log_value(get_current_subject()),
        "replace" if exists else "add",
    )
    raise Forbidden


def _register_tool(tool: RegisterTool) -> str:
    """Register a tool, and make the user registering it its owner if new.

    If the owner role can't be granted, the new tool is deleted again.

    Args:
        tool: Tool to register.

    Returns:
        Identifier of the tool.
    """
    tool.register_metadata()
    if tool.was_created:
        try:
            own_tool(tool.data["id"], tool.stored_id)
        except Exception:
            # only the tool added here, not one registered again meanwhile
            get_collection("tools").delete_one({"_id": tool.stored_id})
            remove_roles(tool.data["id"])
            raise
    return str(tool.data["id"])


@log_traffic
@releases_objects
def postTool() -> str:
    """Add tool with an auto-generated ID.

    The user registering the tool becomes its owner.

    Returns:
        Identifier of created tool.

    Raises:
        InvalidRequest: The tool is invalid, e.g., its version identifiers are
            duplicated or the files of a version are invalid, or its tool
            class does not exist while tool classes are validated.
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
        RemoteFileError: The content of a file could not be retrieved from its
            URL.
    """
    tool = RegisterTool(data=request.json, created_by=get_current_subject())
    return _register_tool(tool)


@log_traffic
@releases_objects
def putTool(
    id: str,
) -> str:
    """Add/replace tool with a user-supplied ID.

    Users who may register tools (`POST /tools`; by default, any
    authenticated user) may add a tool with the identifier of no tool, and
    become its owner; only those that the policies allow (owners of the tool
    and admins, by default) may replace it (cf. `_check_put()`).

    Args:
        id: Identifier of tool to be created/updated.

    Returns:
        Identifier of created/updated tool.

    Raises:
        Conflict: The tool checked was deleted or registered again meanwhile.
        Forbidden: The user may not replace the tool, or may not add it.
        InvalidRequest: The tool is invalid, e.g., its version identifiers are
            duplicated or the files of a version are invalid, or its tool
            class does not exist while tool classes are validated; or the
            identifier of a new tool can't be stored in roles (e.g., with
            commas).
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
        RemoteFileError: The content of a file could not be retrieved from its
            URL.
    """
    stored = get_collection("tools").find_one({"id": id}, {"_id": True})
    exists = stored is not None
    allow_replace = _check_put("tool", id, exists)
    if not exists and not is_usable_id(id):
        logger.info("Tool '%s' not added: unusable identifier.", escape_log_value(id))
        raise InvalidRequest(
            "The identifier can't be used for tools: it must not contain commas "
            "or line breaks, be `*`, `.` or `..`, start with `:` or `#`, or be "
            "too long."
        )
    # only the tool checked may be replaced, not one registered again with
    # the identifier meanwhile
    tool = RegisterTool(
        data=request.json,
        id=id,
        created_by=get_current_subject(),
        allow_replace=allow_replace,
        stored_id=stored["_id"] if stored is not None else None,
    )
    return _register_tool(tool)


@log_traffic
@releases_objects
def deleteTool(
    id: str,
) -> str:
    """Delete tool, with the roles granted on it.

    The roles are revoked before the tool is deleted, so that nobody can act
    on it meanwhile, and again afterwards, as roles may have been granted
    meanwhile. If deleting fails, the tool is left without roles: admins can
    still delete it, or grant it an owner.

    Args:
        id: Identifier of tool to be deleted.

    Returns:
        Previous identifier of deleted tool.

    Raises:
        NotFound: No tool with the given identifier exists.
    """
    db_coll_tools = get_collection("tools")
    stored = db_coll_tools.find_one({"id": id}, {"_id": True})
    if stored is None:
        raise NotFound
    remove_roles(id)
    # only the tool checked, not one registered again with the identifier
    del_obj_tools = db_coll_tools.delete_one({"_id": stored["_id"]})
    remove_roles(id)

    if del_obj_tools.deleted_count:
        return id
    else:
        raise NotFound


@log_traffic
@releases_objects
def postToolVersion(
    id: str,
) -> str:
    """Add tool version with an auto-generated ID.

    Args:
        id: Identifier of tool to be modified.

    Returns:
        Identifier of created tool version.

    Raises:
        InvalidRequest: The files of the version are invalid.
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
@releases_objects
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
        InvalidRequest: The files of the version are invalid.
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
@releases_objects
def deleteToolVersion(
    id: str,
    version_id: str,
) -> str:
    """Delete tool version.

    Args:
        id: Identifier of tool to be modified.
        version_id: Identifier of tool version to be deleted.

    Returns:
        Previous identifier of deleted tool version. The meta version of the
        tool is incremented, unless `custom.tool.meta_version.on_version_change`
        is `false`.

    Raises:
        InvalidRequest: The version is the last one of the tool.
        InternalServerError: The tool version could not be deleted.
        NotFound: No tool with the given identifier and version exists.
    """
    db_coll_tools = get_collection("tools")

    # tools keep at least one version
    filt = {
        "id": id,
        "versions.id": version_id,
        "versions.1": {"$exists": True},
    }
    update: dict[str, Any] = {
        "$pull": {
            "versions": {"id": version_id},
        },
        "$set": {
            **tool_meta_version_change(db_coll_tools, id),
            UPDATED_AT: now(),
        },
    }
    del_ver_tools = db_coll_tools.update_one(
        filter=filt,
        update=update,
    )

    if not del_ver_tools.matched_count:
        if db_coll_tools.count_documents({"id": id, "versions.id": version_id}):
            logger.error("Version '%s' is the last one of tool '%s'.", version_id, id)
            raise InvalidRequest(
                "The last version of a tool can't be deleted; delete the tool instead."
            )
        raise NotFound
    elif not del_ver_tools.modified_count:
        raise InternalServerError
    else:
        return version_id


@log_traffic
def postToolClass() -> str:
    """Add tool class with an auto-generated ID.

    Only users who may add tool classes may (cf.
    `trs_filer.ga4gh.trs.tool_classes.may_add_tool_classes()`); the tool
    class is pending if the user's tool classes are.

    Returns:
        Identifier of created tool class.

    Raises:
        Forbidden: The user may not add tool classes.
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
    """
    _check_add_tool_class()
    tool_class = RegisterToolClass(
        data=request.json,
        created_by=get_current_subject(),
        pending=tool_classes_pending(),
    )
    tool_class.register_metadata()
    return tool_class.data["id"]


def _check_add_tool_class() -> None:
    """Check that the current user may add tool classes.

    Raises:
        Forbidden: The user may not add tool classes (cf.
            `trs_filer.ga4gh.trs.tool_classes.may_add_tool_classes()`).
    """
    if not may_add_tool_classes():
        logger.info(
            "Tool class not added: '%s' may not add tool classes.",
            escape_log_value(get_current_subject()),
        )
        raise Forbidden


@log_traffic
def putToolClass(
    id: str,
) -> str:
    """Add/replace tool class with a user-supplied ID.

    Users who may add tool classes (`POST /toolClasses`, by default any
    authenticated user, and as the mode of
    `custom.access_control.tool_classes` allows, cf.
    `_check_add_tool_class()`) may add a tool class with the identifier of
    no tool class, which is pending if the user's tool classes are; only
    those that the policies allow (admins, by default) may replace it (cf.
    `_check_put()`), which keeps whether it is pending. Adding a tool class
    sets the pending flags of the tools that have it.

    Args:
        id: Identifier of tool class to be created/updated.

    Returns:
        Identifier of created/updated tool class.

    Raises:
        Forbidden: The user may not replace the tool class (also if it was
            added meanwhile), or may not add it.
        InternalServerError: No unique identifier could be generated, or the
            object could not be stored.
    """
    exists = tool_class_exists(id)
    allow_replace = _check_put("tool class", id, exists)
    if not exists:
        _check_add_tool_class()
    tool_class = RegisterToolClass(
        data=request.json,
        id=id,
        allow_replace=allow_replace,
        # replacing was checked for the stored tool class: if it was deleted
        # meanwhile, it isn't added again
        replace_only=allow_replace and exists,
        created_by=get_current_subject(),
        pending=tool_classes_pending(),
    )
    tool_class.register_metadata()
    if not exists:
        # tools may have the tool class already (e.g., if it was deleted
        # while they were registered with it as pending)
        sync_pending_flags(id)
    return tool_class.data["id"]


@log_traffic
def deleteToolClass(
    id: str,
) -> str:
    """Delete tool class.

    Args:
        id: Identifier of tool class to be deleted.

    Returns:
        Previous identifier of deleted tool class.

    Raises:
        InvalidRequest: The tool class is associated with a tool.
        NotFound: No tool class with the given identifier exists.
    """
    db_coll_classes = get_collection("toolclasses")

    # do not allow deleting tool class associated with tool
    if get_collection("tools").find_one({"toolclass.id": id}) is not None:
        logger.error("Tool class '%s' is used by tools.", id)
        raise InvalidRequest("The tool class is used by tools and can't be deleted.")

    if db_coll_classes.delete_one({"id": id}).deleted_count:
        return id
    else:
        raise NotFound


@log_traffic
def putToolClassApproval(
    id: str,
) -> str:
    """Approve a pending tool class, and so the tools that have it.

    Only for admins: no policy in `config.yaml` allows it to other users.

    Args:
        id: Identifier of the tool class.

    Returns:
        Identifier of the tool class, also if it was approved before.

    Raises:
        NotFound: No tool class with the given identifier exists.
    """
    approved = get_collection("toolclasses").find_one_and_update(
        {"id": id, PENDING: True}, {"$unset": {PENDING: ""}}
    )
    if approved is None and not tool_class_exists(id):
        raise NotFound
    # also if the tool class was approved before, to clear flags missed
    # meanwhile
    sync_pending_flags(id)
    if approved is not None:
        logger.info(
            "Tool class '%s' approved by '%s'.",
            escape_log_value(id),
            escape_log_value(get_current_subject()),
        )
    return id


@log_traffic
def getApprovals() -> dict[str, list[dict[str, Any]]]:
    """List the pending tool classes and tools the current user may see.

    Returns:
        Pending tool classes (`toolClasses`), sorted by identifier: all for
        admins, those the user added for other users; and pending tools
        (`tools`, without the files of their versions), sorted by
        identifier: all for admins, those the user has a role on for other
        users.
    """
    tool_classes = get_collection("toolclasses").find(
        {"$and": [{PENDING: True}, visible_tool_classes()]},
        TOOL_CLASS_PROJECTION,
        sort=[("id", 1)],
    )
    tools = list(
        get_collection("tools").find(
            {"$and": [{PENDING: True}, own_tools()]},
            TOOL_PROJECTION,
            sort=[("id", 1)],
        )
    )
    for tool in tools:
        for version in tool.get("versions", []):
            version.pop("files", None)
    return {"toolClasses": list(tool_classes), "tools": tools}


def validate_descriptor_type(type: str) -> None:
    """Validate tool descriptor type.

    Args:
        type: Descriptor type, e.g., "NFL".

    Raises:
        InvalidRequest: Provided descriptor type is invalid.
    """
    valid_types = [f"PLAIN_{t}" for t in RegisterToolVersion.descriptor_types]
    valid_types += RegisterToolVersion.descriptor_types

    if type not in valid_types:
        logger.error(
            "Specified type '%s' not among valid types: %s",
            escape_log_value(type),
            valid_types,
        )
        raise InvalidRequest(
            "The descriptor type is not supported; supported are: "
            f"{', '.join(RegisterToolVersion.descriptor_types)}, and their "
            "PLAIN_ forms."
        )
