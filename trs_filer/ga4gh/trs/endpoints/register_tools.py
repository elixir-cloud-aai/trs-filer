"""Controller for adding new objects."""

from packaging.version import (Version, InvalidVersion)
from random import choice
import string
from typing import (Dict, List)

from flask import (current_app, Request)
from pymongo.errors import DuplicateKeyError

from trs_filer.app import logger


class RegisterObject:
    """ Tool creation class."""

    def __init__(self, request: Request) -> None:
        """ Initialise the ToolPost object creation.

        Args:
            request: API request object.

        Attributes:
            tool_data: Request object data.
            db_collection: Database collection storing tool objects.
            id_charset: Allowed character set or expression evaluating to
                allowed character set for generating object identifiers.
            id_charset_ver: Allowed character set or expression evaluating
                to allowed character set for generating version identifiers.
            id_length: Length of generated object identifiers.
            id_length_ver: Length of generated version identifiers.
            host_name: Name of host for generating TRS URL identifiers.

        Returns:
            None type.
        """
        self.tool_data = request.json
        self.db_collection = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['objects'].client
        )

        # configure attributes required for setting IDs and URLs
        endpoint_conf = current_app.config['FOCA'].endpoints
        self.id_charset = endpoint_conf['tools']['id_charset']
        self.id_charset_ver = endpoint_conf['tool_versions']['id_charset']
        self.id_length = int(endpoint_conf['tools']['id_length'])
        self.id_length_ver = int(endpoint_conf['tool_versions']['id_length'])
        self.host_name = current_app.config['FOCA'].server.host

        # evaluate character set expression or interpret literal string as set
        try:
            self.id_charset = eval(self.id_charset)
        except Exception:
            self.id_charset = ''.join(sorted(set(self.id_charset)))
        try:
            self.id_charset_ver = eval(self.id_charset_ver)
        except Exception:
            self.id_charset_ver = ''.join(sorted(set(self.id_charset_ver)))

    def register_object(self) -> Dict:
        """Register tool with TRS.

        Returns:
            Tool object.
        """

        # set checker variable
        if "checker_url" in self.tool_data:
            self.tool_data['has_checker'] = True
        else:
            self.tool_data['has_checker'] = False

        # set tool class (proper method needs to be added)
        self.create_tool_class()

        # set meta_version
        self.update_meta_version()

        # set unique ID/URL and register object
        while True:
            self.tool_data['id'] = self.generate_id(
                charset=self.id_charset,
                length=self.id_length
            )
            self.tool_data['url'] = (
                f"{self.host_name}/tools/{self.tool_data['id']}"
            )
            # update version information
            if 'versions' in self.tool_data:
                self.add_version_info()
            # insert tool into database
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

    def create_tool_class(self) -> None:
        """Create tool class.

        Returns:
            Generated tool class for the initialised tool object.
        """
        self.tool_data['toolclass'] = {
            "description": "Temporary tool class.",
            "id": "123456",
            "name": "ToolClass"
        }

    def get_latest_meta_version(
        self,
        versions: List[str],
    ) -> str:
        """Sort and give the latest version from list of version strings.

        Args:
            versions: List of version strings.

        Returns:
            Latest version string from the list if semantic versioning, else
            an empty string.
        """
        try:
            versions_tuple = [
                (Version(v), v) for v in versions
            ]
            versions_tuple.sort()
            return versions_tuple[-1][1]
        except InvalidVersion:
            logger.warning(
                    "Version strings do not appear to conform to semantic "
                    "versioning specification."
            )
            return ""

    def update_meta_version(self) -> None:
        """Sets the latest vesion as `meta_version` property if not specified
        by the user.
        """
        versions = self.tool_data.get("versions", None)
        current_meta = self.tool_data.get("meta_version", None)

        if current_meta:
            self.tool_data["meta_version"] = current_meta
        elif versions:
            meta_versions = []
            for sub_version in versions:
                sub_version_meta = sub_version.get('meta_version', None)
                if sub_version_meta:
                    meta_versions.append(sub_version_meta)
            if meta_versions:
                self.tool_data['meta_version'] = self.get_latest_meta_version(
                    versions=meta_versions
                )
            else:
                self.tool_data['meta_version'] = ""
        else:
            self.tool_data['meta_version'] = ""

    def add_version_info(
        self,
    ) -> None:
        """Generates and adds version ID and URL information for each version.
        """
        version_list = []

        for version in self.tool_data['versions']:
            while True:
                # set `verified` flag according to availability of verification
                # source
                if version.get('verified_source', None):
                    version['verified'] = True
                else:
                    version['verified'] = False
                # generate random version ID and set ID and URL accordingly
                version['id'] = self.generate_id(
                    charset=self.id_charset_ver,
                    length=self.id_length_ver
                )
                version['url'] = (
                    f"{self.host_name}/tools/{self.tool_data['id']}/"
                    f"versions/{version['id']}"
                )
                # ensure that generated version has not been assigned
                if version['id'] not in version_list:
                    version_list.append(version)
                    break

        self.tool_data['versions'] = version_list
