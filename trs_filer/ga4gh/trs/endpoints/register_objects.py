"""Controllers for registering new objects."""

from collections import defaultdict
import logging
import string  # noqa: F401
import socket
from typing import (Dict, Optional)
import urllib3

from flask import (current_app)
from pymongo.errors import DuplicateKeyError
import requests

from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)
from trs_filer.ga4gh.trs.endpoints.register_tool_classes import (
    RegisterToolClass
)
from trs_filer.ga4gh.trs.endpoints.utils import (
    generate_id,
)

logger = logging.getLogger(__name__)


class RegisterTool:
    """Class to register tools with the service."""

    def __init__(
        self,
        data: Dict,
        id: Optional[str] = None,
    ) -> None:
        """Initialize tool data.

        Args:
            data: Tool metadata consistent with the `ToolVersion` schema.
            id: Tool identifier. Auto-generated if not provided.

        Attributes:
            data: Tool metadata.
            replace: Whether it is allowed to replace an existing tool. Set
                to `True` if an `id` is provided, else set to `False`.
            id_charset: Allowed character set or expression evaluating to
                allowed character set for generating object identifiers.
            id_length: Length of generated object identifiers.
            meta_version_init: Initial value for tool meta version.
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
                into the tool class database collection on the fly.
            db_coll_tools: Database collection for storing tool objects.
            db_coll_classes: Database collection for storing tool class
                objects.
        """
        conf = current_app.config['FOCA'].endpoints
        self.data = data
        self.data['id'] = None if id is None else id
        self.replace = True
        self.id_charset: str = conf['tool']['id']['charset']
        self.id_length = int(conf['tool']['id']['length'])
        self.meta_version_init = int(conf['tool']['meta_version']['init'])
        self.url_prefix = conf['service']['url_prefix']
        self.host_name = conf['service']['external_host']
        self.external_port = conf['service']['external_port']
        self.api_path = conf['service']['api_path']
        self.tool_class_validation = conf['toolclass']['validation']
        self.db_coll_tools = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['tools'].client
        )
        self.db_coll_classes = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['toolclasses'].client
        )

    def process_metadata(self) -> None:
        """Process tool metadata."""
        # evaluate character set expression or interpret literal string as set
        try:
            self.id_charset = eval(self.id_charset)
        except Exception:
            self.id_charset = ''.join(sorted(set(self.id_charset)))
        # init meta version
        self.data['meta_version'] = str(self.meta_version_init)

    def register_metadata(self) -> None:
        """Register tool."""
        self.process_metadata()
        # keep trying to generate unique ID
        i = 0
        while i < 10:
            i += 1
            # set random ID unless ID is provided
            if self.data['id'] is None:
                self.replace = False
                self.data['id'] = generate_id(
                    charset=self.id_charset,
                    length=self.id_length
                )

            # set self reference URL
            self.data['url'] = (
                f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
                f"{self.api_path}/tools/{self.data['id']}"
            )

            # process version information
            version_list = [
                v.get('id', None) for v in self.data['versions']
                if v.get('id', None) is not None
            ]
            if len(version_list) != len(set(version_list)):
                logger.error("Duplicate tool version IDs specified.")
                raise BadRequest

            for version in self.data['versions']:
                version_proc = RegisterToolVersion(
                    id=self.data['id'],
                    version_id=version.get('id', None),
                    data=version,
                )
                version_proc.process_metadata()
                version = version_proc.data

            if self.replace:
                # replace tool in database
                result_tools = self.db_coll_tools.replace_one(
                    filter={'id': self.data['id']},
                    replacement=self.data,
                )

                # verify replacement
                if result_tools.modified_count:
                    logger.info(
                        f"Replaced tool with id '{self.data['id']}'."
                    )
                    break

            # insert tool into database
            try:
                self.db_coll_tools.insert_one(document=self.data)
            except DuplicateKeyError:
                continue

            # TODO: handle failures & race conditions for adding files & tool
            # classes

            # insert tool class into database
            if self.tool_class_validation:
                data = self.db_coll_classes.find_one(
                    filter={'id': self.data['toolclass']['id']},
                    projection={'_id': False},
                )
                if data is None:
                    raise BadRequest
            tool_class = RegisterToolClass(
                data=self.data['toolclass'],
                id=self.data['toolclass']['id'],
            )
            tool_class.register_metadata()

            logger.info(f"Added tool with id '{self.data['id']}'.")
            break
        else:
            raise InternalServerError
        logger.debug(
            "Entry in 'tools' collection: "
            f"{self.db_coll_tools.find_one({'id': self.data['id']})}"
        )


class RegisterToolVersion:
    """Class to register a version with a tool object."""

    descriptor_types = [
        'CWL',
        'WDL',
        'NFL',
        'GALAXY',
    ]
    image_types = [
        'Docker',
        'Singularity',
        'Conda',
    ]

    def __init__(
        self,
        data: Dict,
        id: str,
        version_id: str = None,
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
            id_charset: Allowed character set or expression evaluating to
                allowed character set for generating version identifiers.
            id_length: Length of generated version identifiers.
            meta_version_init: Initial value for version meta version.
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
        conf = current_app.config['FOCA'].endpoints
        self.data: Dict = data
        self.data['id'] = None if version_id is None else version_id
        self.id: str = id
        self.replace: bool = True
        self.id_charset: str = conf['version']['id']['charset']
        self.id_length: int = int(conf['version']['id']['length'])
        self.meta_version_init: int = int(
            conf['version']['meta_version']['init']
        )
        self.url_prefix: str = conf['service']['url_prefix']
        self.host_name: str = conf['service']['external_host']
        self.external_port: int = conf['service']['external_port']
        self.api_path: str = conf['service']['api_path']
        self.db_coll_tools = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['tools'].client
        )

    def process_metadata(self) -> None:
        """Process version metadata."""
        # evaluate character set expression or interpret literal string as set
        try:
            self.id_charset = eval(self.id_charset)
        except Exception:
            self.id_charset = ''.join(sorted(set(self.id_charset)))

        # init meta version
        self.data['meta_version'] = str(self.meta_version_init)

        # set random ID unless ID is provided
        if self.data['id'] is None:
            self.replace = False
            self.data['id'] = generate_id(
                charset=self.id_charset,
                length=self.id_length
            )

        # set self reference url
        self.data['url'] = (
            f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
            f"{self.api_path}/tools/{self.id}/versions/"
            f"{self.data['id']}"
        )

        # process files
        self.process_files()

    def process_files(self) -> None:
        """Process file (meta)data."""

        # validate file types and unique paths
        file_types = defaultdict(list)
        file_path_dict = defaultdict(list)
        for f in self.data.get('files', []):
            file_types[f['type']].append(f['tool_file']['file_type'])
            if f['tool_file']['path'] in file_path_dict.get(f['type'], []):
                logger.error("Duplicate file paths are not allowed")
                raise BadRequest
            file_path_dict[f['type']].append(f['tool_file']['path'])

        invalid = False
        for d_type, f_types in file_types.items():
            if f_types.count("PRIMARY_DESCRIPTOR") > 1:
                logger.error(
                    "More than one file is annotated as a "
                    f"'PRIMARY_DESCRIPTOR' file for descriptor type '{d_type}'"
                )
                invalid = True
            if (
                "SECONDARY_DESCRIPTOR" in f_types and
                "PRIMARY_DESCRIPTOR" not in f_types
            ):
                logger.error(
                    "At least one file is annotated as a "
                    "'SECONDARY_DESCRIPTOR' file for descriptor type "
                    f"'{d_type}', but no 'PRIMARY_DESCRIPTOR' file is "
                    "available."
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
        for _file in self.data.get('files', []):

            # validate conditionally required properties
            if (
                'url' not in _file['file_wrapper'] and
                'content' not in _file['file_wrapper']
            ):
                logger.error(
                    "FileWrapper must contain at least one of `url` or "
                    "`content`."
                )
                raise BadRequest
            if (
                self.data['is_production'] and
                'checksum' not in _file['file_wrapper'] or
                not _file['file_wrapper']['checksum']
            ):
                logger.error(
                    "Production tools must contain checksum information for "
                    "all files."
                )
                raise BadRequest

            # store contents accessible at url in database
            # TODO: this needs more checks on the content
            if (
                'url' in _file['file_wrapper'] and
                'content' not in _file['file_wrapper']
            ):
                _w = _file['file_wrapper']
                try:
                    _w['content'] = requests.get(_w['url']).text
                except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.MissingSchema,
                    socket.gaierror,
                    urllib3.exceptions.NewConnectionError,
                ):
                    logger.error(
                        "Could not retrieve content via the URL "
                        f"'{_w['url']}' provided for file "
                        f"'{_file['tool_file']['path']}'."
                    )
                    raise BadRequest

            # validate descriptor file types
            descriptor_set = (
                'PRIMARY_DESCRIPTOR',
                'SECONDARY_DESCRIPTOR',
                'TEST_FILE',
                'OTHER',
            )
            if _file['tool_file']['file_type'] in descriptor_set:
                if _file['type'] not in self.descriptor_types:
                    logger.error("Invalid descriptor type.")
                    raise BadRequest

            # validate image file types
            elif _file['tool_file']['file_type'] == "CONTAINERFILE":
                if _file['type'] not in self.image_types:
                    logger.error("Missing or invalid image file type.")
                    raise BadRequest

    def register_metadata(self) -> None:
        """Register version with tool."""
        # check if tool is available
        obj = self.db_coll_tools.find_one(filter={'id': self.id})
        if obj is None:
            raise NotFound

        # keep trying to generate unique ID
        i = 0
        while i < 10:
            i += 1
            self.process_metadata()
            if self.replace:

                # replace tool version in database
                result_tools = self.db_coll_tools.update_one(
                    filter={
                        'id': self.id,
                        'versions.id': self.data['id'],
                    },
                    update={
                        '$set': {
                            'versions.$': self.data,
                        },
                    },
                )

                # verify replacement
                if result_tools.raw_result['updatedExisting']:
                    logger.info(
                        f"Replaced version with id '{self.data['id']}' in "
                        f"tool '{self.id}'."
                    )
                    break

            # insert tool version into database
            result_tools = self.db_coll_tools.update_one(
                filter={
                    'id': self.id,
                    'versions.id': {'$ne': self.data['id']},
                },
                update={
                    '$push': {
                        'versions': self.data,
                    },
                },
            )

            # verify insertion
            if result_tools.modified_count:
                logger.info(
                    f"Added version with id '{self.data['id']}' to tool "
                    f"'{self.id}'."
                )
                break
        else:
            raise InternalServerError
        logger.debug(
            "Entry in 'tools' collection: "
            f"{self.db_coll_tools.find_one({'id': self.data['id']})}"
        )
