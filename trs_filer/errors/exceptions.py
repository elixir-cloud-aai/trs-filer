"""Exceptions for TRS-filer."""

from connexion.exceptions import (
    BadRequestProblem,
    ExtraParameterProblem,
    Forbidden,
    OAuthProblem,
    Unauthorized,
)
from werkzeug.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
    RequestEntityTooLarge,
)

__all__ = [
    "BadRequest",
    "InternalServerError",
    "NotFound",
    "RemoteFileError",
    "exceptions",
]


class RemoteFileError(BadRequest):
    """The content of a file could not be retrieved from its URL.

    Raised if retrieval fails, or isn't allowed by the configuration
    (`custom.remote_files`). The description says why; it is logged, not
    returned to clients.
    """


# Problem details (RFC 9457) of exceptions raised in app context, served by
# FOCA (`exceptions.mapping` in `config.yaml`); exceptions not listed get
# those of their closest listed base class
exceptions = {
    Exception: {
        "title": "Internal server error",
        "detail": "An unexpected error occurred.",
        "status": 500,
    },
    BadRequestProblem: {
        "title": "Bad request",
        "detail": "The request is malformed.",
        "status": 400,
    },
    BadRequest: {
        "title": "Bad request",
        "detail": "The request is malformed.",
        "status": 400,
    },
    RemoteFileError: {
        "title": "Bad request",
        "detail": (
            "The content of a file could not be retrieved from its URL. "
            "Check that the URL is reachable and uses an allowed scheme and "
            "destination, and that the content doesn't exceed the size "
            "limit; or provide the content instead."
        ),
        "status": 400,
    },
    ExtraParameterProblem: {
        "title": "Bad request",
        "detail": "The request is malformed.",
        "status": 400,
    },
    Unauthorized: {
        "title": "Unauthorized",
        "detail": "The request is unauthorized.",
        "status": 401,
    },
    OAuthProblem: {
        "title": "Unauthorized",
        "detail": "The request is unauthorized.",
        "status": 401,
    },
    Forbidden: {
        "title": "Forbidden",
        "detail": "The requester is not authorized to perform this action.",
        "status": 403,
    },
    NotFound: {
        "title": "Not found",
        "detail": "The requested resource wasn't found.",
        "status": 404,
    },
    RequestEntityTooLarge: {
        "title": "Content Too Large",
        "detail": "The request body exceeds the size limit.",
        "status": 413,
    },
    InternalServerError: {
        "title": "Internal server error",
        "detail": "An unexpected error occurred.",
        "status": 500,
    },
}
