"""Tests for the problem details of exceptions."""

from connexion import App
from foca import get_config
from foca.errors.exceptions import _problem_handler_json

from trs_filer.errors.exceptions import (
    InvalidRequest,
    RemoteFileError,
    describe_invalid_request,
)


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


def test_describe_invalid_request(app: App) -> None:
    """Invalid requests are answered with their reason as `detail`.

    Args:
        app: FOCA app.
    """
    with app.app.app_context():
        response = describe_invalid_request(InvalidRequest("The reason."))
    assert response.status_code == 400
    assert response.mimetype == "application/json"
    assert response.get_json() == {
        "title": "Bad request",
        "status": 400,
        "detail": "The reason.",
    }


def test_invalid_request_handler(app: App) -> None:
    """The app answers invalid requests, and only those, with their reason.

    Other bad requests (e.g., `RemoteFileError`) reach FOCA's handler.

    Args:
        app: FOCA app.
    """
    # Flask registers handlers of HTTP exceptions by their status code
    handlers = app.app.error_handler_spec[None][400]
    assert handlers[InvalidRequest] is describe_invalid_request
    assert RemoteFileError not in handlers
