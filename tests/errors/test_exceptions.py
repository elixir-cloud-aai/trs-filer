"""Tests for the problem details of exceptions."""

from copy import deepcopy
from typing import NoReturn

from connexion import App
from flask.testing import FlaskClient
from foca import get_config
from foca.errors.exceptions import _problem_handler_json
import pytest

from tests.mock_data import BASE_PATH, MOCK_TOOL_VERSION_ID
from trs_filer.errors.exceptions import (
    InvalidRequest,
    RemoteFileError,
    describe_invalid_request,
    exceptions,
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


def test_remote_file_error_response(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed retrievals keep the fixed detail, unlike invalid requests.

    Neither the reason nor the URL, which may hold credentials, is sent.

    Args:
        client: Test client.
        monkeypatch: Patch of the retrieval.
    """

    def _raise(**_: object) -> NoReturn:
        """Fail the retrieval.

        Args:
            **_: Arguments of the retrieval.

        Raises:
            RemoteFileError: Always.
        """
        raise RemoteFileError("reason-not-for-clients")

    monkeypatch.setattr(
        "trs_filer.ga4gh.trs.endpoints.register_objects.fetch_remote_file", _raise
    )
    data = deepcopy(MOCK_TOOL_VERSION_ID)
    wrapper = data["versions"][0]["files"][0]["file_wrapper"]
    del wrapper["content"]
    wrapper["url"] = "https://user:hidden@example.org/main.cwl"
    response = client.post(f"{BASE_PATH}/tools", json=data)
    assert response.status_code == 400
    # Exactly the fixed problem details, with nothing appended
    assert response.get_json() == exceptions[RemoteFileError]
    text = response.get_data(as_text=True)
    assert "reason-not-for-clients" not in text
    assert "hidden" not in text
