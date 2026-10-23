"""Tests for the problem details of exceptions."""

from flask import Flask
from foca.errors.exceptions import _problem_handler_json
from foca.models.config import Config

from trs_filer.errors.exceptions import RemoteFileError


def test_remote_file_error() -> None:
    """Files that can't be retrieved from their URLs are answered with
    `400 Bad Request` and a fixed message, without the reason.
    """
    app = Flask(__name__)
    app.config.foca = Config(
        exceptions={
            "exceptions": "trs_filer.errors.exceptions.exceptions",
            "required_members": [["message"], ["code"]],
            "status_member": ["code"],
        },
    )
    with app.app_context():
        response = _problem_handler_json(
            RemoteFileError("reason-not-for-clients")
        )
    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == 400
    assert "retrieved from its URL" in body["message"]
    assert "reason-not-for-clients" not in response.get_data(as_text=True)
