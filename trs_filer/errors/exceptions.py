from connexion.exceptions import (
    ExtraParameterProblem,
    Forbidden,
    Unauthorized,
    BadRequestProblem
)

from werkzeug.exceptions import (
    BadRequest,
    BadGateway,
    GatewayTimeout,
    InternalServerError,
    NotFound,
    ServiceUnavailable,
)


class ObjectNotFound(Exception):
    """Exception raised when object with given object_id is not found"""
    pass


class URLNotFound(Exception):
    """Exception raised when Access URL for object is not found"""
    pass


exceptions = {
    Exception: {
        "msg": "An unexpected error occurred",
        "status_code": '500',
    },
    BadRequestProblem: {
        "msg": "The request is malformed",
        "status_code": '400',
    },
    BadRequest: {
        "msg": "Bad Request",
        "status_code": '400',
    },
    ExtraParameterProblem: {
        "msg": "Bad Request",
        "status_code": '400',
    },
    Unauthorized: {
        "msg": " The request is unauthorized.",
        "status_code": '401',
    },
    Forbidden: {
        "msg": "The requester is not authorized to perform this action",
        "status_code": '403',
    },
    NotFound: {
        "msg": "The requested `DrsObject` wasn't found",
        "status_code": '404',
    },
    ObjectNotFound: {
        "msg": "The requested `DrsObject` wasn't found",
        "status_code": '404',
    },
    URLNotFound: {
        "msg": "The requested access URL wasn't found",
        "status_code": '404',
    },
    InternalServerError: {
        "msg": "An unexpected error occurred",
        "status_code": '500',
    },
    BadGateway: {
        "msg": "Bad Gateway",
        "status_code": '502',
    },
    ServiceUnavailable: {
        "msg": "Service Unavailable",
        "status_code": '502',
    },
    GatewayTimeout: {
        "msg": "Gateway Timeout",
        "status_code": '504',
    }
}
