"""Controllers for registering new objects."""

import logging
from random import choice
import string
from typing import (Dict, Optional)

from flask import (current_app)
from pymongo.errors import DuplicateKeyError

from trs_filer.errors.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
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
            db_coll_tools: Database collection for storing tool objects.
            db_coll_files: Database collection for storing file objects.
        """
        conf = current_app.config['FOCA'].endpoints
        self.data = data
        self.data['id'] = None if id is None else id
        self.replace = True
        self.id_charset = conf['tool']['id']['charset']
        self.id_length = int(conf['tool']['id']['length'])
        self.meta_version_init = int(conf['tool']['meta_version']['init'])
        self.url_prefix = conf['url_prefix']
        self.host_name = conf['external_host']
        self.external_port = conf['external_port']
        self.api_path = conf['api_path']
        self.db_coll_tools = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['tools'].client
        )
        self.db_coll_files = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['files'].client
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
            self.db_coll_files.insert_one(document=files)

            # TODO: handle failure
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

    def __init__(
        self,
        data: Dict,
        id: str,
    ) -> None:
        """Initialize tool version data.

        Args:
            data: Version metadata consistent with the `ToolVersionRegister`
                schema.
            id: Tool identifer.

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
            db_coll_tools: Database collection for storing tool objects.
            db_coll_files: Database collection for storing file objects.
        """
        conf = current_app.config['FOCA'].endpoints
        self.data = data
        self.id = id
        self.replace = True
        self.id_charset = conf['version']['id']['charset']
        self.id_length = int(conf['version']['id']['length'])
        self.meta_version_init = int(conf['version']['meta_version']['init'])
        self.url_prefix = conf['url_prefix']
        self.host_name = conf['external_host']
        self.external_port = conf['external_port']
        self.api_path = conf['api_path']
        self.files = {}
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
        if 'id' not in self.data:
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
            'files': [],
        }
        if 'files' in self.data:
            self.process_files()

    def process_files(self) -> None:
        """Process file (meta)data."""
        # validate required fields
        for _file in self.data['files']:
            if 'fileWrapper' in _file:
                data = _file['fileWrapper']
                if (
                    'url' not in data and
                    'content' not in data
                ):
                    logger.error(
                        "FileWrapper must contain at least one of url or"
                        " content."
                    )
                    raise BadRequest
                if (
                    self.data['is_production'] and
                    'checksum' not in data or
                    not data['checksum']
                ):
                    logger.error(
                        "Production tools must contain checksum "
                        "information."
                    )
                    raise BadRequest

        # create file object
        self.files['files'] = self.data.pop('files')

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


def generate_id(
    charset: str = ''.join([string.ascii_letters, string.digits]),
    length: int = 6,
) -> str:
    """Generate random string based on allowed set of characters.

    Args:
        charset: String of allowed characters.
        length: Length of returned string.

    Returns:
        Random string of specified length and composed of defined set of
        allowed characters.
    """
    return ''.join(choice(charset) for __ in range(length))
