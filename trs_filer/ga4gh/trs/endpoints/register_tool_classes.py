"""Controller for registering new objects."""

import logging
from typing import Any

from foca.utils.logging import escape_log_value
from foca.utils.misc import generate_id
from pymongo.errors import DuplicateKeyError

from trs_filer.errors.exceptions import (
    Conflict,
    Forbidden,
    InternalServerError,
)
from trs_filer.ga4gh.trs.tool_classes import CREATED_BY, PENDING
from trs_filer.utils import get_collection, get_custom_config

logger = logging.getLogger(__name__)

# Fields of tool classes that requests set (`ToolClassRegister`), besides the
# identifier
FIELDS = ("name", "description")


class RegisterToolClass:
    """Class to register tool classes with the service."""

    def __init__(
        self,
        data: dict[str, Any],
        id: str | None = None,
        allow_replace: bool = True,
        replace_only: bool = False,
        created_by: str | None = None,
        pending: bool = False,
    ) -> None:
        """Initialize tool class data.

        Args:
            data: Tool class metadata consistent with the `ToolClass` schema.
            id: Tool class identifier. Auto-generated if not provided.
            allow_replace: With `id`, whether a stored tool class with the
                identifier may be replaced; if not, it is only created.
            replace_only: With `allow_replace`, whether the tool class must be
                stored: if it was deleted meanwhile, it isn't added again.
            created_by: Identifier of the user adding the tool class, stored
                with new tool classes (cf.
                `trs_filer.ga4gh.trs.tool_classes.CREATED_BY`); `None` if
                unknown.
            pending: Whether a new tool class is pending (cf.
                `trs_filer.ga4gh.trs.tool_classes.PENDING`).

        Attributes:
            data: Tool metadata.
            replace: Whether it is allowed to replace an existing tool class.
                Set to `allow_replace` if an `id` is provided, else set to
                `False`.
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
            created_by: Identifier of the user adding the tool class.
            pending: Whether a new tool class is pending.
            db_coll_classes: Database collection for storing tool class
                objects.
        """
        conf = get_custom_config()
        self.data = data
        self.data["id"] = None if id is None else id
        self.replace = allow_replace
        self.replace_only = replace_only
        self.created_by = created_by
        self.pending = pending
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

        New tool classes store who added them, and whether they are pending.
        Replaced tool classes keep these: replacing doesn't approve them.

        Raises:
            Conflict: The tool class to be replaced (`replace_only`) was
                deleted meanwhile.
            Forbidden: A tool class with the given identifier is stored, but
                may not be replaced (`allow_replace`): it was added meanwhile.
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
                # replace the fields of the tool class in the database,
                # keeping its internal fields
                update: dict[str, Any] = {
                    "$set": {
                        field: self.data[field]
                        for field in ("id", *FIELDS)
                        if field in self.data
                    }
                }
                unset = {field: "" for field in FIELDS if field not in self.data}
                if unset:
                    update["$unset"] = unset
                result = self.db_coll_classes.update_one(
                    filter={"id": self.data["id"]}, update=update
                )
                # verify replacement (also of identical tool classes)
                if result.matched_count:
                    logger.info("Replaced tool class with id '%s'.", self.data["id"])
                    break
                if self.replace_only:
                    logger.info(
                        "Tool class '%s' not replaced: deleted meanwhile.",
                        escape_log_value(self.data["id"]),
                    )
                    raise Conflict

            # insert tool class into database (a copy, as `insert_one()` adds
            # `_id`)
            internal: dict[str, Any] = {CREATED_BY: self.created_by}
            if self.pending:
                internal[PENDING] = True
            try:
                self.db_coll_classes.insert_one(document={**self.data, **internal})
            except DuplicateKeyError:
                if not generate_ids and not self.replace:
                    logger.info(
                        "Tool class '%s' not added: added meanwhile.",
                        escape_log_value(self.data["id"]),
                    )
                    raise Forbidden from None
                continue

            logger.info("Added tool class with id '%s'.", self.data["id"])
            break
        else:
            raise InternalServerError
        logger.debug(
            "Entry in 'toolclasses' collection: %s",
            self.db_coll_classes.find_one({"id": self.data["id"]}),
        )
