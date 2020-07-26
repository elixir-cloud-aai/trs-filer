from connexion.exceptions import (
    ExtraParameterProblem,
    Forbidden,
    Unauthorized,
)

from werkzeug.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
)

exceptions = {
    Exception: {
        "message": "Internal Server Error",
        "code": 500,
    },
    BadRequest: {
        "message": "Bad Request",
        "code": 400,
    },
    ExtraParameterProblem: {
        "message": "Bad Request",
        "code": 400,
    },
    Unauthorized: {
        "message": "Unauthorized",
        "code": 401,
    },
    Forbidden: {
        "message": "Forbidden",
        "code": 403,
    },
    NotFound: {
        "message": "Not Found",
        "code": 404,
    },
    InternalServerError: {
        "message": "Internal Server Error",
        "code": 500,
    }
}
