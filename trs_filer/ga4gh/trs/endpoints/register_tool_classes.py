"""Controller for registering new objects."""

import logging
from typing import Any

from foca.utils.misc import generate_id
from pymongo.errors import DuplicateKeyError

from trs_filer.errors.exceptions import (
    InternalServerError,
)
from trs_filer.utils import get_collection, get_custom_config

logger = logging.getLogger(__name__)


class RegisterToolClass:
    """Class to register tool classes with the service."""

    def __init__(
        self,
        data: dict[str, Any],
        id: str | None = None,
    ) -> None:
        """Initialize tool class data.

        Args:
            data: Tool class metadata consistent with the `ToolClass` schema.
            id: Tool class identifier. Auto-generated if not provided.

        Attributes:
            data: Tool metadata.
            replace: Whether it is allowed to replace an existing tool. Set
                to `True` if an `id` is provided, else set to `False`.
            id_charset: Allowed characters for generating object
                identifiers.
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
        conf = get_custom_config()
        self.data = data
        self.data["id"] = None if id is None else id
        self.replace = True
        self.id_charset = conf.toolclass.id.charset
        self.id_length = int(conf.toolclass.id.length)
        self.meta_version_init = int(conf.toolclass.meta_version.init)
        self.url_prefix = conf.service.url_prefix
        self.host_name = conf.service.external_host
        self.external_port = conf.service.external_port
        self.api_path = conf.service.api_path
        self.db_coll_classes = get_collection("toolclasses")

    def register_metadata(self) -> None:
        """Register toolClass with TRS.

        Raises:
            InternalServerError: No unique identifier could be generated, or the
                object could not be stored.
        """
        generate_ids = self.data["id"] is None
        if generate_ids:
            self.replace = False
        # set unique ID, dependent values and register object
        for _ in range(10):
            # set random ID unless ID is provided
            if generate_ids:
                self.data["id"] = generate_id(
                    charset=self.id_charset, length=self.id_length
                )

            if self.replace:
                # replace tool class in database (a copy, see below)
                result = self.db_coll_classes.replace_one(
                    filter={"id": self.data["id"]},
                    replacement=dict(self.data),
                )
                # verify replacement (also of identical tool classes)
                if result.matched_count:
                    logger.info("Replaced tool class with id '%s'.", self.data["id"])
                    break

            # insert tool class into database (a copy, as `insert_one()` adds
            # `_id`)
            try:
                self.db_coll_classes.insert_one(document=dict(self.data))
            except DuplicateKeyError:
                continue

            logger.info("Added tool class with id '%s'.", self.data["id"])
            break
        else:
            raise InternalServerError
        logger.debug(
            "Entry in 'toolclasses' collection: %s",
            self.db_coll_classes.find_one({"id": self.data["id"]}),
        )
