"""Tests of the typed access to the config and collections."""

from flask import Flask
from foca.config.access import set_app_config
from foca.models.config import Config
import pytest

from trs_filer.utils import get_custom_config


def test_no_custom_config() -> None:
    """Apps without the custom config are refused."""
    app = Flask(__name__)
    set_app_config(app, Config())
    with (
        app.app_context(),
        pytest.raises(RuntimeError, match="No custom configuration"),
    ):
        get_custom_config()
