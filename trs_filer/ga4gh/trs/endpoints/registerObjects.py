"""Controller for adding new objects."""

from random import choice
from typing import (Dict, List)
import string

from flask import (current_app, request)
from pymongo.errors import DuplicateKeyError

from trs_filer.app import logger


class CreateToolPostObject:
    """ Tool creation class. """

    def __init__(self, request: request) -> None:
        """ Initialise the ToolPost object creation.

        Args:
            request: API request object.

        Returns:
            None type.
        """
        self.db_collection = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['objects'].client
        )
        self.tool_data = request.json
        self.id_charset = (
            current_app.config['FOCA'].endpoints['tools']['id_charset']
        )
        self.id_length = (
            current_app.config['FOCA'].endpoints['tools']['id_length']
        )
        self.host_name = current_app.config['FOCA'].server.host

    def create_id(
        self,
        charset: str = ''.join([string.ascii_letters, string.digits]),
        length: int = 6
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

    def create_tool_class(self) -> Dict:
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
        lst_versions: List[str]
    ) -> str:
        """Sort and give the latest version from version list.

        Args:
            lst_versions: List of versions of the tool.

        Returns:
            Latest version string from the list
            if semantic versioning else empty string.
        """
        try:
            lst_versions.sort(key=lambda s: list(map(int, s.split('.'))))
            return lst_versions[-1]
        except Exception as e:
            logger.info("Non semantic versioning", e)
            return ""

    def update_meta_version(self) -> None:
        """Sets the latest vesion as meta_version if not specified.
        """
        version_lst = self.tool_data.get("versions", None)
        current_meta = self.tool_data.get("meta_version", None)

        if current_meta:
            self.tool_data["meta_version"] = current_meta
        elif version_lst:
            lst_meta_versions = []
            for sub_version in version_lst:
                sub_version_meta = sub_version.get("meta_version", None)
                if sub_version_meta:
                    lst_meta_versions.append(sub_version_meta)
            if lst_meta_versions:
                self.tool_data["meta_version"] = self.get_latest_meta_version(
                    lst_meta_versions
                )
            else:
                self.tool_data["meta_version"] = ""
        else:
            self.tool_data["meta_version"] = ""

    def create_object(self) -> Dict:
        """Register tool with TRS.

        Returns:
            Tool object generated.

        Raises:
            DuplicateKeyError is duplicated key found.
        """

        # set checker variable
        if "checker_url" in self.tool_data:
            self.tool_data['has_checker'] = True
        else:
            self.tool_data['has_checker'] = False

        # set tool class (proper method needs to be added)
        self.create_tool_class()

        # set meta_version method
        self.update_meta_version()

        # set unique id and url and save object
        while True:
            generated_object_id = self.create_id(
                charset=self.id_charset,
                length=self.id_length
            )
            self.tool_data['id'] = generated_object_id
            self.tool_data['url'] = (
                f"{self.host_name}/tools/{self.tool_data['id']}"
            )
            try:
                self.db_collection.insert_one(self.tool_data)
            except DuplicateKeyError:
                continue
            logger.info(f"Tool with id: {self.tool_data['id']} created.")
            break

        return self.tool_data

    def get_tool_object_data(self) -> Dict:
        """Create and get required fields from tool object.

        Returns:
            Required fields from tool object.
        """
        tool_data = self.create_object()
        return tool_data['id']
