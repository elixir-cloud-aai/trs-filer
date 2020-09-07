"""Controller for registering new objects."""

import logging
from random import choice
import string
from typing import (Dict, Optional)
from pymongo.errors import DuplicateKeyError
from flask import (current_app, Request)

logger = logging.getLogger(__name__)


class RegisterToolClass:
    """Class to register tools with the service."""

    def __init__(
        self,
        request: Request,
        id: Optional[str] = None,
    ) -> None:
        """Initialize tool data.

        Args:
            request: API request object.
            id: ToolClass ID. Auto-generated if not provided.

        Attributes:
            description: A longer explanation of what this class is and what it can accomplish.

            id: The unique identifier for the class.

            name: A short friendly name for the class.
        """
        self.toolclass_data = request.json
        if id:
            self.toolclass_data['id'] = id
        self.db_collection_toolclass = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['toolclasses'].client
        )
        conf = current_app.config['FOCA'].endpoints
        self.toolclass_id_charset = conf['toolclass']['id']['charset']
        self.toolclass_id_length = int(conf['toolclass']['id']['length'])
        self.url_prefix = conf['url_prefix']
        self.host_name = conf['external_host']
        self.external_port = conf['external_port']
        self.api_path = conf['api_path']
        # evaluate character set expression or interpret literal string as set
        try:
            self.toolclass_id_charset = eval(self.toolclass_id_charset)
        except Exception:
            self.toolclass_id_charset = ''.join(
                sorted(set(self.toolclass_id_charset)))

    def register_toolclass(self) -> Dict:
        """Register tool with TRS.

        Returns:
            Tool object.
        """

        # set unique ID, dependent values and register object
        while True:

            # set random tool ID unless ID is provided
            if 'id' not in self.toolclass_data:
                replace = False
                self.toolclass_data['id'] = self.generate_id(
                    charset=self.toolclass_id_charset,
                    length=self.toolclass_id_length
                )
            else:
                replace = True

            # set toolclass self reference URL
            self.toolclass_data['url'] = (
                f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
                f"{self.api_path}/toolClasses/{self.toolclass_data['id']}"
            )

            # update(insert) toolclass in(to) database
            if replace:
                self.db_collection_toolclass.replace_one(
                    filter={'id': self.toolclass_data['id']},
                    replacement=self.toolclass_data,
                    upsert=True,
                )
            else:
                try:
                    self.db_collection_toolclass.insert_one(
                        self.toolclass_data)
                except DuplicateKeyError:
                    continue

            logger.info(f"Created toolClass with id: {self.toolclass_data['id']}")
            break

        return self.toolclass_data

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
