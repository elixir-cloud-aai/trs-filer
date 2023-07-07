"""API server entry point."""

from pathlib import Path

from foca import Foca

from trs_filer.ga4gh.trs.endpoints.service_info import RegisterServiceInfo


def main():
    # create app object
    foca = Foca(
        config_file=Path(__file__).resolve().parent / "config.yaml",
    )
    app = foca.create_app()

    # register service info
    with app.app.app_context():
        service_info = RegisterServiceInfo()
        service_info.set_service_info_from_config()
    # start app

    app.run(port=app.port)


if __name__ == '__main__':
    main()
