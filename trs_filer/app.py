"""API server entry point."""

from pathlib import Path

from connexion import App
from foca import Foca

from trs_filer.ga4gh.trs.endpoints.service_info import RegisterServiceInfo


def init_app() -> App:
    """Initialize FOCA application.

    Returns:
        App: FOCA application.
    """
    # create app object
    foca = Foca(
        config_file=Path(__file__).resolve().parent / "config.yaml",
        custom_config_model="trs_filer.custom_config.CustomConfig",
    )
    app = foca.create_app()

    # register service info
    with app.app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
    return app


def run_app(app: App) -> None:
    """Run FOCA application."""
    app.run(port=app.port)


if __name__ == "__main__":
    my_app = init_app()
    run_app(my_app)
