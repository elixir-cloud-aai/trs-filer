"""Exceptions for TRS-filer."""

from connexion.exceptions import (
    BadRequestProblem,
    ExtraParameterProblem,
    Forbidden,
    Unauthorized,
)
from werkzeug.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)


class RemoteFileError(BadRequest):
    """The content of a file could not be retrieved from its URL.

    Raised if retrieval fails, or isn't allowed by the configuration
    (`custom.remote_files`). The description says why; it is logged, not
    returned to clients.
    """


# exceptions raised in app context
exceptions = {
    Exception: {
        "message": "An unexpected error occurred.",
        "code": 500,
    },
    BadRequestProblem: {
        "message": "The request is malformed",
        "code": 400,
    },
    BadRequest: {
        "message": "The request is malformed.",
        "code": 400,
    },
    RemoteFileError: {
        "message": (
            "The content of a file could not be retrieved from its URL. "
            "Check that the URL is reachable and uses an allowed scheme and "
            "destination, and that the content doesn't exceed the size "
            "limit; or provide the content instead."
        ),
        "code": 400,
    },
    ExtraParameterProblem: {
        "message": "The request is malformed.",
        "code": 400,
    },
    Unauthorized: {
        "message": "The request is unauthorized.",
        "code": 401,
    },
    Forbidden: {
        "message": "The requester is not authorized to perform this action.",
        "code": 403,
    },
    NotFound: {
        "message": "The requested resource wasn't found.",
        "code": 404,
    },
    InternalServerError: {
        "message": "An unexpected error occurred.",
        "code": 500,
    }
}


# exceptions raised outside of app context
class ValidationError(Exception):
    """Value or object is not compatible with required type or schema."""
