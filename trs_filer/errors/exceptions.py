"""Exceptions for TRS-filer."""

from connexion.exceptions import (
    BadRequestProblem,
    ExtraParameterProblem,
    Forbidden,
    OAuthProblem,
    Unauthorized,
)
from flask import Response
from foca.errors.exceptions import problem_response
from werkzeug.exceptions import (
    BadRequest,
    InternalServerError,
    NotAcceptable,
    NotFound,
    RequestEntityTooLarge,
)

__all__ = [
    "BadRequest",
    "InternalServerError",
    "InvalidRequest",
    "NotAcceptable",
    "NotFound",
    "RemoteFileError",
    "describe_invalid_request",
    "exceptions",
]


class InvalidRequest(BadRequest):
    """The app refuses a request that matches the API specification.

    E.g., a tool whose files break a rule of the app, or a query that the
    app doesn't support. The description says why and is sent to clients as
    `detail` (cf. `describe_invalid_request()`), so it must not contain
    submitted values, which may hold credentials (e.g., URLs). Unlike FOCA's
    error handler, `describe_invalid_request()` doesn't log: log the reason
    (with identifiers, if useful) where it is raised.
    """


class RemoteFileError(BadRequest):
    """The content of a file could not be retrieved from its URL.

    Raised if retrieval fails, or isn't allowed by the configuration
    (`custom.remote_files`). The description says why; it is logged, not
    returned to clients.
    """


def describe_invalid_request(exc: InvalidRequest) -> Response:
    """Answer an invalid request with its reason as `detail`.

    Error handler of the app for `InvalidRequest` (registered in
    `trs_filer.app.create_app()`): FOCA's error handler sends the fixed
    problem details of `exceptions` for all other exceptions, including
    other bad requests (e.g., `RemoteFileError`, whose description is not
    for clients). Like FOCA's, its responses are not validated against the
    API specification. Cf. FOCA's `problem_response()`, which
    cloud-registry's controllers return.

    Args:
        exc: Invalid request.

    Returns:
        `400 Bad Request` problem details response with the description of
        the exception as `detail`.
    """
    return problem_response(exc)


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
    # Only paths that the specification offers as JSON and plain text check
    # `Accept`
    NotAcceptable: {
        "title": "Not acceptable",
        "detail": (
            "The resource can't be served as any of the accepted media types; "
            "descriptor types are served as application/json, their PLAIN_ "
            "forms as text/plain."
        ),
        "status": 406,
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
