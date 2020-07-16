from connexion.exceptions import (
    ExtraParameterProblem,
    Forbidden,
    Unauthorized,
)

from werkzeug.exceptions import (
    BadRequest,
    BadGateway,
    GatewayTimeout,
    InternalServerError,
    NotFound,
    ServiceUnavailable,
)

exceptions = {
    Exception: {
        "title": "Internal Server Error",
        "status": 500,
    },
    BadRequest: {
        "title": "Bad Request",
        "status": 400,
    },
    ExtraParameterProblem: {
        "title": "Bad Request",
        "status": 400,
    },
    Unauthorized: {
        "title": "Unauthorized",
        "status": 401,
    },
    Forbidden: {
        "title": "Forbidden",
        "status": 403,
    },
    NotFound: {
        "title": "Not Found",
        "status": 404,
    },
    InternalServerError: {
        "title": "Internal Server Error",
        "status": 500,
    },
    BadGateway: {
        "title": "Bad Gateway",
        "status": 502,
    },
    ServiceUnavailable: {
        "title": "Service Unavailable",
        "status": 502,
    },
    GatewayTimeout: {
        "title": "Gateway Timeout",
        "status": 504,
    }
}
