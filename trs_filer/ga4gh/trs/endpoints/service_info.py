import logging
from typing import (Union, Dict)

from flask import current_app
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


class RegisterService:
    """Tool class for registering service_info. Returns readily formatted service
    info; creates service_info database document if it does not exist.
    """

    def __init__(self) -> None:
        """Initialize class requirements.

        Attributes:
            db_collection: Database collection storing service info objects.
            service_info: Service info details as per enpoints config.
            collection_service_info: Latest service_info detail stored in
            database.
        """
        self.db_collection = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['service_info'].client
        )
        conf = current_app.config['FOCA'].endpoints
        self.service_info = conf['service_info']
        self.collection_service_info = self.get_latest_service_info()

    def get_latest_service_info(self) -> Union[Dict, None]:
        """Get latest service info details from database.

        Returns:
            Dict object corresponding the latest service info details.
            If not found, None.
        """
        try:
            return self.db_collection.find(
                {},
                {'_id': False}
            ).sort([('_id', -1)]).limit(1).next()
        except StopIteration:
            return None

    def get_service_info(self) -> Dict:
        """Get service info details from database. If requested config,
        not present, then creates a mapping in the database.

        Returns:
            Latest service info details from database.
        """
        # Write current service info to db if absent/different from latest
        if not self.service_info == self.collection_service_info:
            try:
                self.db_collection.insert_one(self.service_info)
                logger.info(f'Updated service info: {self.service_info}')
            except DuplicateKeyError:
                logger.warning(
                    f"Duplicate service info id: {self.service_info['id']}"
                    " present."
                )

        return self.get_latest_service_info()
