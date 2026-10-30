"""Tests for the problem details of exceptions."""

from connexion import App
from foca import get_config
from foca.errors.exceptions import _problem_handler_json

from trs_filer.errors.exceptions import RemoteFileError


def test_remote_file_error(app: App) -> None:
    """Files that can't be retrieved are answered with `400 Bad Request`.

    The response has a fixed detail, without the reason.

    Args:
        app: FOCA app.
    """
    with app.app.app_context():
        response = _problem_handler_json(
            RemoteFileError("reason-not-for-clients"),
            get_config().exceptions,
        )
    assert response.status_code == 400
    assert response.mimetype == "application/json"
    body = response.get_json()
    assert body["status"] == 400
    assert body["title"] == "Bad request"
    assert "retrieved from its URL" in body["detail"]
    assert "reason-not-for-clients" not in response.get_data(as_text=True)
