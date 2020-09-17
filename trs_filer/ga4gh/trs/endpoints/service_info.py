"""Controller for service info endpoint."""

import logging
from typing import Dict

from flask import current_app

from trs_filer.errors.exceptions import (
    NotFound,
    ValidationError,
)

logger = logging.getLogger(__name__)


class RegisterServiceInfo:
    """Tool class for registering service info.

    Creates service info upon first request, if it does not exist.
    """

    def __init__(self) -> None:
        """Initialize class requirements.

        Attributes:
            url_prefix: URL scheme of application. For constructing tool and
                version `url` properties.
            host_name: Name of application host. For constructing tool and
                version `url` properties.
            external_port: Port at which application is served. For
                constructing tool and version `url` properties.
            api_path: Base path at which API endpoints can be reached. For
                constructing tool and version `url` properties.
            db_coll_info: Database collection storing service info objects.
            conf_info: Service info details as per enpoints config.
        """
        conf = current_app.config['FOCA'].endpoints
        self.url_prefix = conf['service']['url_prefix']
        self.host_name = conf['service']['external_host']
        self.external_port = conf['service']['external_port']
        self.api_path = conf['service']['api_path']
        self.conf_info = conf['service_info']
        self.db_coll_info = (
            current_app.config['FOCA'].db.dbs['trsStore']
            .collections['service_info'].client
        )

    def get_service_info(self) -> Dict:
        """Get latest service info from database.

        Returns:
            Latest service info details.
        """
        try:
            return self.db_coll_info.find(
                {},
                {'_id': False}
            ).sort([('_id', -1)]).limit(1).next()
        except StopIteration:
            raise NotFound

    def set_service_info_from_config(
        self,
    ) -> None:
        """Create or update service info from service configuration.

        Will create service info if it does not exist or current
        configuration differs from available one.

        Raises:
            trs_filer.errors.exceptions.ValidationError: Service info
                configuration does not conform to API specification.
        """
        add = False
        try:
            db_info = self.get_service_info()
        except NotFound:
            db_info = {}
        add = False if db_info == self.conf_info else True
        if add:
            try:
                self._upsert_service_info(data=self.conf_info)
            except KeyError:
                logger.exception(
                    "The service info configuration does not conform to the "
                    "API specification."
                )
                raise ValidationError
            logger.info(
                "Service info registered."
            )
        else:
            logger.info(
                "Using available service info."
            )

    def set_service_info_from_app_context(
        self,
        data: Dict,
    ) -> Dict:
        """Return service info.

        Arguments:
            data: Service info according to API specification.

        Returns:
            Response headers.
        """
        self._upsert_service_info(data=data)
        return self._get_headers()

    def _upsert_service_info(
        self,
        data: Dict,
    ) -> None:
        """Insert or updated service info document."""
        self.db_coll_info.replace_one(
            filter={'id': data['id']},
            replacement=data,
            upsert=True,
        )

    def _get_headers(self) -> Dict:
        """Build dictionary of response headers.

        Returns:
            Response headers.
        """
        headers: Dict = {
            'Content-type': 'application/json',
        }
        headers['Location'] = (
            f"{self.url_prefix}://{self.host_name}:{self.external_port}/"
            f"{self.api_path}/service-info"
        )
        return headers
