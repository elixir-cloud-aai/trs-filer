"""Controller for registering new objects."""

import logging
from random import choice
import string
from typing import (Dict, Optional, List)

from flask import (current_app, Request)
from pymongo.errors import DuplicateKeyError

from trs_filer.errors.exceptions import BadRequest

logger = logging.getLogger(__name__)


class RegisterObject:
    """Class to register tools with the service."""

    def __init__(
        self,
        request: Request,
        id: Optional[str] = None,
    ) -> None:
        """Initialize tool data.

        Args:
            request: API request object.
            id: Tool ID. Auto-generated if not provided.

        Attributes:
            tool_data: Request object data.
            db_collection: Database collection storing tool objects.
            tool_id_charset: Allowed character set or expression evaluating to
                allowed character set for generating object identifiers.
            tool_id_length: Length of generated object identifiers.
            tool_meta_version_init: Initial value for tool meta version.
            url_prefix: URL scheme of application. For constructing tool and
                version `url` properties.
            host_name: Name of application host. For constructing tool and
                version `url` properties.
            external_port: Port at which application is served. For
                constructing tool and version `url` properties.
            api_path: Base path at which API endpoints can be reached. For
                constructing tool and version `url` properties.
        """
        self.tool_data = request.json
        if id:
            self.tool_data['id'] = id
        self.db_collection = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['objects'].client
        )
        conf = current_app.config['FOCA'].endpoints
        self.tool_id_charset = conf['tool']['id']['charset']
        self.tool_id_length = int(conf['tool']['id']['length'])
        self.tool_meta_version_init = int(conf['tool']['meta_version']['init'])
        self.url_prefix = conf['url_prefix']
        self.host_name = conf['external_host']
        self.external_port = conf['external_port']
        self.api_path = conf['api_path']
        # evaluate character set expression or interpret literal string as set
        try:
            self.tool_id_charset = eval(self.tool_id_charset)
        except Exception:
            self.tool_id_charset = ''.join(sorted(set(self.tool_id_charset)))

    def register_object(self) -> Dict:
        """Register tool with TRS.

        Returns:
            Tool object.
        """
        # set tool meta version
        self.tool_data['meta_version'] = str(self.tool_meta_version_init)

        # set unique ID, dependent values and register object
        while True:
            # set random tool ID unless ID is provided
            if 'id' not in self.tool_data:
                replace = False
                self.tool_data['id'] = self.generate_id(
                    charset=self.tool_id_charset,
                    length=self.tool_id_length
                )
            else:
                replace = True

            # set tool self reference URL
            self.tool_data['url'] = (
                f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
                f"{self.api_path}/tools/{self.tool_data['id']}"
            )

            # process version information
            if 'versions' in self.tool_data:
                version_controller = RegisterToolVersion(
                    version_data=self.tool_data['versions'],
                    id=self.tool_data['id'],
                    replace=replace,
                )
                self.tool_data['versions'] = version_controller \
                    .create_update_versions()

            # update(insert) tool in(to) database
            if replace:
                self.db_collection.replace_one(
                    filter={'id': self.tool_data['id']},
                    replacement=self.tool_data,
                    upsert=True,
                )
            else:
                try:
                    self.db_collection.insert_one(self.tool_data)
                except DuplicateKeyError:
                    continue

            logger.info(f"Created tool with id: {self.tool_data['id']}")
            break
        return self.tool_data

    def generate_id(
        self,
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


class RegisterToolVersion:
    """Class to register tools with the service."""

    def __init__(
        self,
        id: str,
        request: Optional[Request] = None,
        version_data: Optional[List] = None,
        replace: bool = False,
        append: bool = False,
    ) -> None:
        """Initialize tool data.

        Args:
            id: Tool ID.
            version_data: Version list information.
            request: API request object. Used if version_data not available.
            append: Boolean flag to differentiate different instance. False if
                complete version list changed, other wise True if a new version
                needs to be appended.

        Attributes:
            append: Flag to check if new version is being added or entire
                version list is being updated.
            tool_id: Tool data id that needs to be updated.
            version_data: New version list with which old version list will be
                updated/replaced.
            db_collection: Database collection storing tool objects.
            db_collection_files: Database collection storing tool files.
            version_id_charset: Allowed character set or expression evaluating
                to allowed character set for generating version identifiers.
            version_id_length: Length of generated version identifiers.
            versoin_meta_version_init: Initial value for version meta version.
            url_prefix: URL scheme of application. For constructing tool and
                version `url` properties.
            host_name: Name of application host. For constructing tool and
                version `url` properties.
            external_port: Port at which application is served. For
                constructing tool and version `url` properties.
            api_path: Base path at which API endpoints can be reached. For
                constructing tool and version `url` properties.
            tool_version_files_map: Map between tool_version and corresponding
                file information.
            replace: Identifier of an existing tool_object.
        """
        self.append = append
        self.tool_id = id

        if version_data is not None:
            self.version_data = version_data
        if request:
            self.version_data = request.json

        self.db_collection = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['objects'].client
        )
        self.db_collection_files = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['files'].client
        )
        conf = current_app.config['FOCA'].endpoints
        self.version_id_charset = conf['tool_version']['id']['charset']
        self.version_id_length = int(conf['tool_version']['id']['length'])
        self.version_meta_version_init = int(
            conf['tool_version']['meta_version']['init']
        )
        self.url_prefix = conf['url_prefix']
        self.host_name = conf['external_host']
        self.external_port = conf['external_port']
        self.api_path = conf['api_path']
        # evaluate character set expression or interpret literal string as set
        try:
            self.version_id_charset = eval(self.version_id_charset)
        except Exception:
            self.version_id_charset = ''.join(
                sorted(set(self.version_id_charset))
            )
        self.version_files_map = {}
        self.version_files_map[self.tool_id] = {}
        self.replace = replace

    def add_versions(
        self,
        versions: List[Dict]
    ) -> List[Dict]:
        """Adds version properties.

        Args:
            versions: New/updated version list.

        Returns:
            Version list with added db properties.
        """
        # get list of available version IDs
        version_list = [
            v.get('id', None) for v in versions
        ]

        # ensure that all supplied version IDs are unique
        if len(version_list) != len(set(version_list)):
            raise BadRequest

        flag_files = False

        for version in versions:

            # set version meta version
            version['meta_version'] = str(self.version_meta_version_init)

            # generate random ID if not supplied
            if 'id' not in version:

                # set unique ID
                while True:
                    # set random version ID
                    version['id'] = self.generate_id(
                        charset=self.version_id_charset,
                        length=self.version_id_length
                    )

                    # ensure that generated version has not been assigned
                    if version['id'] not in version_list:
                        break

            # set version self reference URL
            version['url'] = (
                f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
                f"{self.api_path}/tools/{self.tool_id}/versions/"
                f"{version['id']}"
            )

            if 'files' in version:
                flag_files = True
                self.version_files_map[self.tool_id][
                    version['id']
                ] = self.check_file_data(version)
                version.pop('files', None)
        if flag_files:
            self.create_file_mappings()
        return versions

    def generate_id(
        self,
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

    def create_update_versions(self) -> List[Dict]:
        """Create/Updates version list.

        Returns:
            Updated new version list.
        """
        if self.tool_id and self.append:
            old_version = self.db_collection.find_one(
                filter={"id": self.tool_id},
                projection={"_id": False, "versions": True}
            )
            old_version = old_version['versions']
            if old_version:
                self.version_data = old_version+self.version_data
        return self.add_versions(self.version_data)

    def check_file_data(
        self,
        version_data: Dict
    ) -> List[Dict]:
        """Validates file data corresponding a version.

        Args:
            version_data: version specific data.

        Returns:
            List of validated file objects.

        Raises:
            BadRequest if data not validated.
        """
        data_files = version_data['files']
        for _file in data_files:
            if 'fileWrapper' in _file:
                data = _file['fileWrapper']
                if 'url' not in data and 'content' not in data:
                    logger.error(
                        "FileWrapper must contain at least one of url or"
                        " content."
                    )
                    raise BadRequest
                if version_data['is_production']:
                    if 'checksum' not in data or not data['checksum']:
                        logger.error("Please include checksum information.")
                        raise BadRequest
        return version_data['files']

    def create_file_mappings(self) -> None:
        """Create file objcts for every versions of a particular tool
        object.
        """
        if self.version_files_map and self.tool_id in self.version_files_map:
            if self.replace:
                self.db_collection_files.replace_one(
                    filter={'tool_id': self.tool_id},
                    replacement=self.version_files_map[self.tool_id],
                    upsert=True,
                )
            else:
                try:
                    self.db_collection_files.insert_one(self.version_files_map)
                except DuplicateKeyError:
                    logger.error("Tool id already present.")
