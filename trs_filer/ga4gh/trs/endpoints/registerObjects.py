"""Controller for adding new objects."""

from random import choice
from typing import Dict
from trs_filer.app import logger
from flask import (current_app, request)
from pymongo.errors import DuplicateKeyError


class CreateToolPostObject:
    def __init__(self, request: request):
        self.db_collection = (
            current_app.config['FOCA'].db.dbs['trsStore'].
            collections['objects'].client
        )
        self.tool_data = request.json
        self.id_charset = current_app.config['FOCA'].\
            endpoints['objects']['id_charset']
        self.id_length = current_app.config['FOCA'].\
            endpoints['objects']['id_length']
        self.host_name = current_app.config['FOCA'].server.host

    def create_id(self, charset, length) -> str:
        """Creates random ID."""
        return ''.join(choice(charset) for __ in range(length))

    def create_tool_class(self):
        """Create tool class."""
        self.tool_data['toolclass'] = {
            "description": "Temporary tool class.",
            "id": "123456",
            "name": "ToolClass"
        }

    def create_object(self) -> Dict:
        """
        Add new tool post objects to TRS Registry.

        Args:
            request: API request object.

        Returns:
            A unique identifier for the object.
        """

        # set checker variable
        if "checker_url" in self.tool_data:
            self.tool_data['has_checker'] = True
        else:
            self.tool_data['has_checker'] = False

        # set tool class (proper method needs to be added)
        self.create_tool_class()

        # set meta_version method

        # set unique id and url and save object
        while True:
            try:
                generated_object_id = self.\
                    create_id(self.id_charset, self.id_length)
                self.tool_data['id'] = generated_object_id
                self.tool_data['url'] = \
                    f"{self.host_name}/tools/{self.tool_data['id']}"
                self.db_collection.insert_one(self.tool_data)
            except DuplicateKeyError:
                continue
            except Exception as e:
                raise e
            logger.info(f"object with id: {self.tool_data['id']} created.")
            break

        return self.tool_data
