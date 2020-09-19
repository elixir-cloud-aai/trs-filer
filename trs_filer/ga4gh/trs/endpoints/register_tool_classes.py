"""Controller for registering new objects."""

import logging
import string  # noqa: F401
from typing import (Dict, Optional)

from flask import current_app
from pymongo.errors import DuplicateKeyError

from trs_filer.errors.exceptions import (
    InternalServerError,
)
from trs_filer.ga4gh.trs.endpoints.utils import (
    generate_id,
)

logger = logging.getLogger(__name__)


class RegisterToolClass:
    """Class to register tool classes with the service."""

    def __init__(
        self,
        data: Dict,
        id: Optional[str] = None,
    ) -> None:
        """Initialize tool class data.

        Args:
            data: Tool class metadata consistent with the `ToolClass` schema.
            id: Tool class identifier. Auto-generated if not provided.

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
        self.db_coll_classes = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['toolclasses'].client
        )

    def process_metadata(self) -> None:
        """Process tool class metadata."""
        # evaluate character set expression or interpret literal string as set
        try:
            self.id_charset = eval(self.id_charset)
        except Exception:
            self.id_charset = ''.join(sorted(set(self.id_charset)))

    def register_metadata(self) -> None:
        """Register toolClass with TRS.

        Returns:
            ToolClass object.
        """
        self.process_metadata()

        # set unique ID, dependent values and register object
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

            if self.replace:
                # replace tool class in database
                result = self.db_coll_classes.replace_one(
                    filter={'id': self.data['id']},
                    replacement=self.data,
                )
                # verify replacement
                if result.modified_count:
                    logger.info(
                        f"Replaced tool class with id '{self.data['id']}'."
                    )
                    break

            # insert tool class into database
            try:
                self.db_coll_classes.insert_one(document=self.data)
            except DuplicateKeyError:
                continue

            logger.info(f"Added tool class with id '{self.data['id']}'.")
            break
        else:
            raise InternalServerError
        logger.debug(
            "Entry in 'toolclasses' collection: "
            f"{self.db_coll_classes.find_one({'id': self.data['id']})}"
        )
