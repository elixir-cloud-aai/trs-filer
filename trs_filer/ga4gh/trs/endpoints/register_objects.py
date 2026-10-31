"""Controllers for registering new objects."""

from collections import defaultdict
import logging
from typing import Any, ClassVar

from foca.utils.misc import generate_id
from pymongo.errors import DuplicateKeyError

from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)
from trs_filer.remote_files import fetch_remote_file
from trs_filer.utils import get_collection, get_custom_config

logger = logging.getLogger(__name__)


def next_meta_version(previous: object, init: int, increment: int) -> str:
    """Get the meta version of a replaced object.

    Args:
        previous: Meta version of the stored object.
        init: Initial meta version, for stored objects without a valid one.
        increment: Increment of meta versions.

    Returns:
        The previous meta version plus the increment, as a string (as in the
        TRS specification).
    """
    try:
        return str(int(str(previous)) + increment)
    except ValueError:
        return str(init)


class RegisterTool:
    """Class to register tools with the service."""

    def __init__(
        self,
        data: dict[str, Any],
        id: str | None = None,
    ) -> None:
        """Initialize tool data.

        Args:
            data: Tool metadata consistent with the `ToolVersion` schema.
            id: Tool identifier. Auto-generated if not provided.

        Attributes:
            data: Tool metadata.
            replace: Whether it is allowed to replace an existing tool. Set
                to `True` if an `id` is provided, else set to `False`.
            id_charset: Allowed characters for generating object
                identifiers.
            id_length: Length of generated object identifiers.
            meta_version_init: Initial value for tool meta version.
            meta_version_increment: Increment of the tool meta version when
                the tool is replaced (not when its versions are added,
                replaced or deleted on their own).
            version_meta_version_init: Initial value for version meta
                versions.
            version_meta_version_increment: Increment of the meta version of
                a version when the tool replaces it.
            url_prefix: URL scheme of application. For constructing tool and
                version `url` properties.
            host_name: Name of application host. For constructing tool and
                version `url` properties.
            external_port: Port at which application is served. For
                constructing tool and version `url` properties.
            api_path: Base path at which API endpoints can be reached. For
                constructing tool and version `url` properties.
            tool_class_validation: Whether a tool is only allowed to be added
                if it is associated with a pre-existing tool class; if `False`,
                the tool class associated with the tool to be added is inserted
                into the tool class database collection on the fly, unless
                it exists (existing tool classes are not changed).
            db_coll_tools: Database collection for storing tool objects.
            db_coll_classes: Database collection for storing tool class
                objects.
        """
        conf = get_custom_config()
        self.data = data
        self.data["id"] = None if id is None else id
        self.replace = True
        self.id_charset: str = conf.tool.id.charset
        self.id_length = int(conf.tool.id.length)
        self.meta_version_init = int(conf.tool.meta_version.init)
        self.meta_version_increment = int(conf.tool.meta_version.increment)
        self.version_meta_version_init = int(conf.version.meta_version.init)
        self.version_meta_version_increment = int(conf.version.meta_version.increment)
        self.url_prefix = conf.service.url_prefix
        self.host_name = conf.service.external_host
        self.external_port = conf.service.external_port
        self.api_path = conf.service.api_path
        self.tool_class_validation = conf.toolclass.validation
        self.db_coll_tools = get_collection("tools")
        self.db_coll_classes = get_collection("toolclasses")

    def process_metadata(self) -> None:
        """Process tool metadata."""
        # init meta version
        self.data["meta_version"] = str(self.meta_version_init)

    def register_metadata(self) -> None:
        """Register tool.

        Tools with a given identifier replace a stored tool with that
        identifier, if any; their meta version, and those of their versions
        that replace stored versions, are incremented. Unless tool classes are
        validated, the tool class is created if it does not exist; existing
        tool classes are not changed, and tools store a copy of them.

        Raises:
            BadRequest: Version identifiers are duplicated, the files of a
                version are invalid, or the tool class does not exist while
                tool classes are validated.
            InternalServerError: No unique identifier could be generated, or the
                object could not be stored.
            trs_filer.errors.exceptions.RemoteFileError: The content of a file
                could not be retrieved from its URL.
        """
        self.process_metadata()
        generate_ids = self.data["id"] is None
        if generate_ids:
            self.replace = False

        # set tool class identifier if not present
        tool_class_id = self.data["toolclass"].get("id", None)
        if tool_class_id is None:
            tool_class_id = generate_id(charset=self.id_charset, length=self.id_length)
            self.data["toolclass"]["id"] = tool_class_id
        # tools store a copy of their tool class: that of an existing one
        stored_class = self.db_coll_classes.find_one(
            filter={"id": tool_class_id}, projection={"_id": False}
        )
        if stored_class is not None:
            self.data["toolclass"] = stored_class
        elif self.tool_class_validation:
            logger.error("Tool class '%s' does not exist.", tool_class_id)
            raise BadRequest

        version_list = [
            v.get("id", None)
            for v in self.data["versions"]
            if v.get("id", None) is not None
        ]
        if len(version_list) != len(set(version_list)):
            logger.error("Duplicate tool version IDs specified.")
            raise BadRequest

        # process versions once (their files included); retries below only
        # change the identifier of the tool, and so the versions' URLs
        if generate_ids:
            self.data["id"] = generate_id(
                charset=self.id_charset, length=self.id_length
            )
        versions = [
            RegisterToolVersion(
                id=self.data["id"],
                version_id=version.get("id", None),
                data=version,
            )
            for version in self.data["versions"]
        ]
        for version_proc in versions:
            # Modifies the version's dict in place
            version_proc.process_metadata()

        # keep trying to generate unique ID
        for attempt in range(10):
            # set another random ID unless ID is provided
            if generate_ids and attempt:
                self.data["id"] = generate_id(
                    charset=self.id_charset, length=self.id_length
                )
                for version_proc in versions:
                    version_proc.set_tool_id(self.data["id"])

            # set self reference URL
            self.data["url"] = (
                f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
                f"{self.api_path}/tools/{self.data['id']}"
            )

            if self.replace and self._replace():
                logger.info("Replaced tool with id '%s'.", self.data["id"])
                break

            # insert tool into database (a copy, as `insert_one()` adds `_id`)
            try:
                self.db_coll_tools.insert_one(document=dict(self.data))
            except DuplicateKeyError:
                continue
            logger.info("Added tool with id '%s'.", self.data["id"])
            break
        else:
            raise InternalServerError

        if stored_class is None:
            self._create_tool_class()
        logger.debug(
            "Entry in 'tools' collection: %s",
            self.db_coll_tools.find_one({"id": self.data["id"]}),
        )

    def _create_tool_class(self) -> None:
        """Create the tool class of the tool, unless it exists.

        Existing tool classes are shared by tools and not changed. If another
        registration created the tool class in the meantime (with other
        content), the tool stores a copy of that one instead, unless the tool
        was replaced in the meantime, too.
        """
        tool_class = dict(self.data["toolclass"])
        try:
            result = self.db_coll_classes.update_one(
                filter={"id": tool_class["id"]},
                update={"$setOnInsert": tool_class},
                upsert=True,
            )
        except DuplicateKeyError:
            # concurrent upserts of the same identifier: another one inserted
            # the tool class
            pass
        else:
            if result.upserted_id is not None:
                logger.info("Added tool class with id '%s'.", tool_class["id"])
                return
        stored = self.db_coll_classes.find_one(
            filter={"id": tool_class["id"]}, projection={"_id": False}
        )
        if stored is None or stored == tool_class:
            return
        self.data["toolclass"] = stored
        self.db_coll_tools.update_one(
            filter={"id": self.data["id"], "toolclass": tool_class},
            update={"$set": {"toolclass": stored}},
        )
        logger.info(
            "Tool '%s' stores tool class '%s' as created concurrently.",
            self.data["id"],
            tool_class["id"],
        )

    def _replace(self) -> bool:
        """Replace the stored tool with the same identifier, if any.

        The meta versions of the tool, and of its versions that replace
        stored versions, are those of the stored ones plus the increments.

        Returns:
            Whether a stored tool was replaced.
        """
        stored = self.db_coll_tools.find_one(filter={"id": self.data["id"]})
        if stored is None:
            return False
        self.data["meta_version"] = next_meta_version(
            stored.get("meta_version"),
            init=self.meta_version_init,
            increment=self.meta_version_increment,
        )
        stored_versions = {
            version.get("id"): version for version in stored.get("versions", [])
        }
        for version in self.data["versions"]:
            if version["id"] in stored_versions:
                version["meta_version"] = next_meta_version(
                    stored_versions[version["id"]].get("meta_version"),
                    init=self.version_meta_version_init,
                    increment=self.version_meta_version_increment,
                )
        result = self.db_coll_tools.replace_one(
            filter={"id": self.data["id"]},
            replacement=dict(self.data),
        )
        return bool(result.matched_count)


class RegisterToolVersion:
    """Class to register a version with a tool object."""

    descriptor_types: ClassVar[list[str]] = [
        "CWL",
        "WDL",
        "NFL",
        "GALAXY",
    ]
    image_types: ClassVar[list[str]] = [
        "Docker",
        "Singularity",
        "Conda",
    ]

    def __init__(
        self,
        data: dict[str, Any],
        id: str,
        version_id: str | None = None,
    ) -> None:
        """Initialize tool version data.

        Args:
            data: Version metadata consistent with the `ToolVersionRegister`
                schema.
            id: Tool identifer.
            version_id: Version identifier.

        Attributes:
            data: Version metadata.
            id: Tool identifer.
            replace: Whether it is allowed to replace an existing version. Set
                to `True` if a `version_id` is provided, else set to `False`.
            id_charset: Allowed characters for generating version
                identifiers.
            id_length: Length of generated version identifiers.
            meta_version_init: Initial value for version meta version.
            meta_version_increment: Increment of the version meta version
                when the version is replaced.
            url_prefix: URL scheme of application. For constructing tool and
                version `url` properties.
            host_name: Name of application host. For constructing tool and
                version `url` properties.
            external_port: Port at which application is served. For
                constructing tool and version `url` properties.
            api_path: Base path at which API endpoints can be reached. For
                constructing tool and version `url` properties.
            db_coll_tools: Database collection for storing tool objects.
        """
        conf = get_custom_config()
        self.data: dict[str, Any] = data
        self.data["id"] = None if version_id is None else version_id
        self.id: str = id
        self.replace: bool = True
        self.id_charset: str = conf.version.id.charset
        self.id_length: int = int(conf.version.id.length)
        self.meta_version_init: int = int(conf.version.meta_version.init)
        self.meta_version_increment: int = int(conf.version.meta_version.increment)
        self.url_prefix: str = conf.service.url_prefix
        self.host_name: str | None = conf.service.external_host
        self.external_port: int | None = conf.service.external_port
        self.api_path: str | None = conf.service.api_path
        self.db_coll_tools = get_collection("tools")

    def process_metadata(self) -> None:
        """Process version metadata.

        Raises:
            BadRequest: The files of the version are invalid.
            trs_filer.errors.exceptions.RemoteFileError: The content of a file
                could not be retrieved from its URL.
        """
        # init meta version
        self.data["meta_version"] = str(self.meta_version_init)

        # set random ID unless ID is provided
        if self.data["id"] is None:
            self.replace = False
            self.set_id(generate_id(charset=self.id_charset, length=self.id_length))
        else:
            self.set_id(self.data["id"])

        # process files
        self.process_files()

    def set_id(self, version_id: str) -> None:
        """Set the identifier of the version, and its self reference URL.

        Args:
            version_id: Version identifier.
        """
        self.data["id"] = version_id
        self.data["url"] = (
            f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
            f"{self.api_path}/tools/{self.id}/versions/"
            f"{self.data['id']}"
        )

    def set_tool_id(self, tool_id: str) -> None:
        """Set the identifier of the tool, and the version's self reference URL.

        Args:
            tool_id: Tool identifier.
        """
        self.id = tool_id
        self.set_id(self.data["id"])

    def process_files(self) -> None:
        """Process file (meta)data.

        Raises:
            BadRequest: The files of the version are invalid.
            trs_filer.errors.exceptions.RemoteFileError: The content of a file
                could not be retrieved from its URL.
        """
        # validate file types and unique paths
        file_types: defaultdict[str, list[str]] = defaultdict(list)
        file_path_dict: defaultdict[str, list[str]] = defaultdict(list)
        for f in self.data.get("files", []):
            file_types[f["type"]].append(f["tool_file"]["file_type"])
            if f["tool_file"]["path"] in file_path_dict.get(f["type"], []):
                logger.error("Duplicate file paths are not allowed")
                raise BadRequest
            file_path_dict[f["type"]].append(f["tool_file"]["path"])

        invalid = False
        for d_type, f_types in file_types.items():
            if f_types.count("PRIMARY_DESCRIPTOR") > 1:
                logger.error(
                    "More than one file is annotated as a "
                    "'PRIMARY_DESCRIPTOR' file for descriptor type '%s'",
                    d_type,
                )
                invalid = True
            if (
                "SECONDARY_DESCRIPTOR" in f_types
                and "PRIMARY_DESCRIPTOR" not in f_types
            ):
                logger.error(
                    "At least one file is annotated as a "
                    "'SECONDARY_DESCRIPTOR' file for descriptor type "
                    "'%s', but no 'PRIMARY_DESCRIPTOR' file is "
                    "available.",
                    d_type,
                )
                invalid = True
        if invalid:
            logger.error(
                "If there are any descriptor files associated with a "
                "a given descriptor type of a given tool version, exactly "
                "one of the files must be desginaed the 'PRIMARY_DESCRIPTOR' "
                "file"
            )
            raise BadRequest

        # validate required fields
        for _file in self.data.get("files", []):
            # validate conditionally required properties
            if (
                "url" not in _file["file_wrapper"]
                and "content" not in _file["file_wrapper"]
            ):
                logger.error(
                    "FileWrapper must contain at least one of `url` or `content`."
                )
                raise BadRequest
            if self.data.get("is_production", False) and (
                "checksum" not in _file["file_wrapper"]
                or not _file["file_wrapper"]["checksum"]
            ):
                logger.error(
                    "Production tools must contain checksum information for all files."
                )
                raise BadRequest

            # store contents accessible at url in database
            # TODO: this needs more checks on the content
            if (
                "url" in _file["file_wrapper"]
                and "content" not in _file["file_wrapper"]
            ):
                # Failures raise `RemoteFileError` and are logged
                _w = _file["file_wrapper"]
                _w["content"] = fetch_remote_file(
                    url=_w["url"],
                    config=get_custom_config().remote_files,
                ).text

            # validate descriptor file types
            descriptor_set = (
                "PRIMARY_DESCRIPTOR",
                "SECONDARY_DESCRIPTOR",
                "TEST_FILE",
                "OTHER",
            )
            if _file["tool_file"]["file_type"] in descriptor_set:
                if _file["type"] not in self.descriptor_types:
                    logger.error("Invalid descriptor type.")
                    raise BadRequest

            # validate image file types
            elif (
                _file["tool_file"]["file_type"] == "CONTAINERFILE"
                and _file["type"] not in self.image_types
            ):
                logger.error("Missing or invalid image file type.")
                raise BadRequest

    def register_metadata(self) -> None:
        """Register version with tool.

        Versions with a given identifier replace a stored version of the tool
        with that identifier, if any; their meta version is incremented.

        Raises:
            BadRequest: The files of the version are invalid.
            InternalServerError: No unique identifier could be generated, or the
                object could not be stored.
            NotFound: The tool does not exist.
            trs_filer.errors.exceptions.RemoteFileError: The content of a file
                could not be retrieved from its URL.
        """
        # check if tool is available
        obj = self.db_coll_tools.find_one(filter={"id": self.id})
        if obj is None:
            raise NotFound

        generate_ids = self.data["id"] is None
        self.process_metadata()

        # keep trying to generate unique ID
        for attempt in range(10):
            if generate_ids and attempt:
                self.set_id(generate_id(charset=self.id_charset, length=self.id_length))
            if self.replace and self._replace():
                logger.info(
                    "Replaced version with id '%s' in tool '%s'.",
                    self.data["id"],
                    self.id,
                )
                break

            # insert tool version into database
            result_tools = self.db_coll_tools.update_one(
                filter={
                    "id": self.id,
                    "versions.id": {"$ne": self.data["id"]},
                },
                update={
                    "$push": {
                        "versions": self.data,
                    },
                },
            )

            # verify insertion
            if result_tools.modified_count:
                logger.info(
                    "Added version with id '%s' to tool '%s'.",
                    self.data["id"],
                    self.id,
                )
                break
        else:
            raise InternalServerError
        logger.debug(
            "Entry in 'tools' collection: %s",
            self.db_coll_tools.find_one({"id": self.id}),
        )

    def _replace(self) -> bool:
        """Replace the stored version of the tool with the same identifier.

        The meta version is that of the stored version plus the increment.

        Returns:
            Whether a stored version was replaced.
        """
        stored = self.db_coll_tools.find_one(
            filter={"id": self.id, "versions.id": self.data["id"]},
            projection={"versions": {"$elemMatch": {"id": self.data["id"]}}},
        )
        if stored is None:
            return False
        self.data["meta_version"] = next_meta_version(
            stored["versions"][0].get("meta_version"),
            init=self.meta_version_init,
            increment=self.meta_version_increment,
        )
        result = self.db_coll_tools.update_one(
            filter={
                "id": self.id,
                "versions.id": self.data["id"],
            },
            update={
                "$set": {
                    "versions.$": self.data,
                },
            },
        )
        return bool(result.matched_count)
