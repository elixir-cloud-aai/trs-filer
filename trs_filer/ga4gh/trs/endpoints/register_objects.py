"""Controllers for registering new objects."""

import logging
import string  # noqa: F401
from typing import (Dict, Optional)

from flask import (current_app)
from pymongo.errors import DuplicateKeyError
import urllib.error
import urllib.request

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
            db_coll_files: Database collection for storing file objects.
            db_coll_classes: Database collection for storing tool class
                objects.
        """
        conf = current_app.config['FOCA'].endpoints
        self.data = data
        self.data['id'] = None if id is None else id
        self.replace = True
        self.id_charset = conf['tool']['id']['charset']
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
        self.db_coll_files = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['files'].client
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
            version_list = [v.get('id', None) for v in self.data['versions']]
            if len(version_list) != len(set(version_list)):
                logger.error("Duplicate tool version IDs specified.")
                raise BadRequest
            files = {
                'id': self.data['id'],
                'versions': [],
            }
            for version in self.data['versions']:
                version_proc = RegisterToolVersion(
                    id=self.data['id'],
                    version_id=version.get('id', None),
                    data=version,
                )
                version_proc.process_metadata()
                version = version_proc.data
                files['versions'].append(version_proc.files)

            if self.replace:
                # replace tool in database
                result_tools = self.db_coll_tools.replace_one(
                    filter={'id': self.data['id']},
                    replacement=self.data,
                )

                # replace tool version files in database
                result_files = self.db_coll_files.replace_one(
                    filter={'id': self.data['id']},
                    replacement=files,
                )

                # verify replacement
                if (
                    result_tools.modified_count and
                    result_files.modified_count
                ):
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

            # insert files into database
            self.db_coll_files.insert_one(document=files)

            # insert tool class into database
            if self.tool_class_validation:
                data = self.db_coll_classes.find_one(
                    filter={'id': self.data['toolclass']['id']},
                    projection={'_id': False},
                )
                print(data)
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
        logger.debug(
            "Entry in 'files' collection: "
            f"{self.db_coll_files.find_one({'id': self.data['id']})}"
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
            files: Container for storing file (meta)data.
            primary_descriptor_flags: Dictionary to keep track of which
                descriptor types have a `PRIMARY_DESCRIPTOR` file associated
                with them.
            db_coll_tools: Database collection for storing tool objects.
            db_coll_files: Database collection for storing file objects.
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
        self.files: Dict = {}
        self.primary_descriptor_flags: Dict[str, bool] = {
            k: False for k in self.descriptor_types
        }
        self.db_coll_tools = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['tools'].client
        )
        self.db_coll_files = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['files'].client
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
        self.files = {
            'id': self.data['id'],
            "descriptors": [],
            "containers": [],
            "tests": [],
            "others": []
        }
        if 'files' in self.data:
            # Set `containerfile` property
            self.data['containerfile'] = False
            for f in self.data['files']:
                try:
                    if f['tool_file']['file_type'] == "CONTAINERFILE":
                        self.data['containerfile'] = True
                        break
                except KeyError:
                    continue
            self.process_files()

    def validate_file_wrapper(self, file_data_wrapper: Dict) -> None:
        """Validate the contents of file_wrapper for a given file object."""
        if (
            'url' not in file_data_wrapper and
            'content' not in file_data_wrapper
        ):
            logger.error(
                "FileWrapper must contain at least one of url or"
                " content."
            )
            raise BadRequest
        if (
            self.data['is_production'] and
            'checksum' not in file_data_wrapper or
            not file_data_wrapper['checksum']
        ):
            logger.error(
                "Production tools must contain checksum "
                "information."
            )
            raise BadRequest

    def process_file_type_register(self, file_data: Dict) -> None:
        """Validate file type for a given file data object and appends files object
        to the respective file dictionary array.

        Args:
            file_data: File data object.
        """

        # validate descriptor file types
        descriptor_set = ('PRIMARY_DESCRIPTOR', 'SECONDARY_DESCRIPTOR')
        if file_data['tool_file']['file_type'] in descriptor_set:
            if (
                'type' not in file_data or
                file_data['type'] not in self.descriptor_types
            ):
                logger.error("Missing or invalid descriptor type.")
                raise BadRequest
            else:
                if file_data['tool_file']['file_type'] == "PRIMARY_DESCRIPTOR":
                    if self.primary_descriptor_flags[file_data['type']]:
                        logger.error(
                            "Multiple PRIMARY_DESCRIPTOR files for the same "
                            "descriptor type are not supported."
                        )
                        raise BadRequest
                    self.primary_descriptor_flags[file_data['type']] = True
                self.files['descriptors'].append(file_data)

        # validate image file types
        elif file_data['tool_file']['file_type'] == "CONTAINERFILE":
            if (
                'type' not in file_data or
                file_data['type'] not in self.image_types
            ):
                logger.error("Missing or invalid image file type.")
                raise BadRequest
            else:
                self.files['containers'].append(file_data)

        # validate test file types
        elif file_data['tool_file']['file_type'] == "TEST_FILE":
            if (
                'type' in file_data and
                file_data['type'] != "JSON"
            ):
                logger.error("Invalid test file type.")
                raise BadRequest
            else:
                file_data['type'] = 'JSON'
                self.files['tests'].append(file_data)

        # validate other file types
        elif file_data['tool_file']['file_type'] == "OTHER":
            if (
                'type' in file_data and
                file_data['type'] != "OTHER"
            ):
                logger.error("Invalid file type.")
                raise BadRequest
            else:
                file_data['type'] = 'OTHER'
                self.files['others'].append(file_data)

    def process_files(self) -> None:
        """Process file (meta)data."""
        # validate required fields
        for _file in self.data['files']:
            curr_file_data = _file

            if 'file_wrapper' in curr_file_data:
                data = curr_file_data['file_wrapper']
                self.validate_file_wrapper(data)

                # store contents accessible at url in database
                # TODO: this needs more checks
                if (
                    'url' in curr_file_data['file_wrapper'] and
                    'content' not in curr_file_data['file_wrapper']
                ):
                    wrapper = curr_file_data['file_wrapper']
                    try:
                        with urllib.request.urlopen(wrapper['url']) as f:
                            wrapper['content'] = f.read().decode('utf-8')
                    except urllib.error.URLError as e:
                        logger.error(f"'{wrapper['url']}' '{e.reason}'")

                if 'tool_file' not in curr_file_data:
                    logger.error(
                        "ToolFile information must be provided."
                    )
                    raise BadRequest
                if 'file_type' not in curr_file_data['tool_file']:
                    curr_file_data['tool_file']['file_type'] = 'OTHER'

                self.process_file_type_register(curr_file_data)
        self.data.pop('files')

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

                # replace tool version files in database
                result_files = self.db_coll_files.update_one(
                    filter={
                        'id': self.id,
                        'versions.id': self.data['id'],
                    },
                    update={
                        '$set': {
                            'versions.$': self.files,
                        },
                    },
                )

                # verify replacement
                if (
                    result_tools.raw_result['updatedExisting'] and
                    result_files.raw_result['updatedExisting']
                ):
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

            # insert tool version files into database
            result_files = self.db_coll_files.update_one(
                filter={
                    'id': self.id,
                    'versions.id': {'$ne': self.data['id']},
                },
                update={
                    '$push': {
                        'versions': self.files,
                    },
                },
            )

            # verify insertion
            if (
                result_tools.modified_count and
                result_files.modified_count
            ):
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
        logger.debug(
            "Entry in 'files' collection: "
            f"{self.db_coll_files.find_one({'id': self.data['id']})}"
        )
