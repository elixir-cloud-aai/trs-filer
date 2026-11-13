"""App factory, and entry point for development.

The image serves the app with Gunicorn (`trs_filer.app:create_app()`, see
`trs_filer.gunicorn_config`); `python -m trs_filer.app` runs it with Flask's
development server.
"""

import logging
from pathlib import Path

from connexion import App
from foca import Foca, get_config
from foca.security.auth import require_no_service_clients

from trs_filer.errors.exceptions import InvalidRequest, describe_invalid_request
from trs_filer.ga4gh.trs.tool_classes import sync_pending_tools
from trs_filer.utils import get_custom_config

logger = logging.getLogger(__name__)


def create_app() -> App:
    """Create the app from the config, with the app's checks.

    FOCA validates the config, including the custom config
    (`trs_filer.custom_config.CustomConfig`) and the service info
    (`service_info`), and limits the size of request bodies
    (`server.max_content_length`). FOCA also warns of placeholders in the
    service info (values in reserved example domains, RFC 2606, as those of
    `config.yaml`). For access control, FOCA requires trusted token issuers
    (`security.auth.issuers`) with an audience, and refuses to start without
    admins (`security.access_control.require_admin`). The app additionally
    requires a size limit, refuses service clients (FOCA's
    `require_no_service_clients()`), as service clients (or the users they
    act for) would need their own roles on tools, and answers invalid
    requests
    (`trs_filer.errors.exceptions.InvalidRequest`) with their reason as
    `detail`. It warns of the deprecated `custom.toolclass.validation`, and
    corrects the pending flags of tools (cf.
    `trs_filer.ga4gh.trs.tool_classes.sync_pending_tools()`).

    Gunicorn calls this in each worker, after forking (MongoDB clients must
    not be shared across forks), so the checks run in each worker; if they
    fail, the worker fails to boot and Gunicorn exits.

    Returns:
        Connexion app.

    Raises:
        RuntimeError: Request bodies are not limited in size
            (`server.max_content_length` is null), or service clients are
            configured (`security.auth.service_clients`,
            `security.auth.on_behalf_of_header`), which the app doesn't
            support.
        ValueError: The custom config is invalid, e.g., it still sets
            `custom.service_info`, or an ID character set is an expression
            (FOCA raises it from a plain `ValueError` that names the invalid
            setting and the reason, without the invalid value), or there are
            no admins (unless admins are optional,
            `security.access_control.require_admin`).
        pydantic.ValidationError: FOCA's config is invalid, e.g., the
            service info, or no token issuers are trusted, or they have no
            audience.
    """
    foca = Foca(
        config_file=Path(__file__).resolve().parent / "config.yaml",
        custom_config_model="trs_filer.custom_config.CustomConfig",
    )
    app = foca.create_app()
    require_no_service_clients(app.app)
    # Invalid requests are answered with their reason (more specific than
    # FOCA's handler of all exceptions)
    app.add_error_handler(InvalidRequest, describe_invalid_request)
    with app.app.app_context():
        # `null` would remove FOCA's size limit of request bodies, so that
        # bodies of any size are read
        if get_config().server.max_content_length is None:
            raise RuntimeError(
                "Request bodies must be limited in size: set "
                "`server.max_content_length` (bytes), not null"
            )
        if get_custom_config().toolclass.validation:
            logger.warning(
                "`custom.toolclass.validation` is deprecated and will be removed "
                "in the next breaking release: set "
                "`custom.access_control.tool_classes: controlled` instead (applied)"
            )
        sync_pending_tools()
    return app


def main() -> None:
    """Run the app with Flask's development server, on the configured port.

    For development; not for production.
    """
    app = create_app()
    app.run(port=app.port)


if __name__ == "__main__":
    main()
