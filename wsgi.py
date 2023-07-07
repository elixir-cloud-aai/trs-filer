"""WSGI entry point."""

from trs_filer.app import init_app

app = init_app()
