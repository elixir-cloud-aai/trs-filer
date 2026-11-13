"""Checks of GA4GH I/O Schema files on registration (experimental).

Cf. `custom.io_schema` and `docs/io-schema.md`.
"""

import json
import logging
import math
import subprocess
import sys
import threading
import time
from typing import NoReturn

from trs_filer.errors.exceptions import InternalServerError, InvalidRequest
from trs_filer.io_schema import META_SCHEMA_ID, PREFIX

logger = logging.getLogger(__name__)

# One validation process per app process at a time, so that concurrent
# registrations don't add up the memory and CPU of their validations
_SLOTS = threading.BoundedSemaphore(1)


def _reject_constant(name: str) -> NoReturn:
    """Reject the constants that Python's JSON parser accepts, but JSON hasn't.

    Args:
        name: The constant (`NaN`, `Infinity` or `-Infinity`).

    Raises:
        ValueError: Always.
    """
    raise ValueError(f"Not a JSON value: {name}")


def _too_slow(timeout: float) -> InvalidRequest:
    """Get the exception for I/O Schemas not checked within the time limit.

    Args:
        timeout: Time limit, in seconds.

    Returns:
        The exception.
    """
    logger.error("I/O Schema file not checked within %s s.", timeout)
    return InvalidRequest(
        f"{PREFIX} could not be checked within the time limit of "
        f"{timeout:g} s; simplify it (e.g., nest its schemas less deeply)."
    )


def _validate(content: bytes, timeout: float) -> str | None:
    """Validate an I/O Schema in a process of its own, with a time limit.

    The process runs `python -I -m trs_filer.io_schema` with the Python of
    the app, so the app must be installed (as in the image), not run from a
    source checkout. It is killed when the time limit is reached, and limits
    its own CPU time to it, so that slow validations don't hold up the app,
    also if the app is stopped. One validation runs at a time; waiting for
    another one counts against the time limit.

    Args:
        content: The I/O Schema, a JSON object, encoded in UTF-8.
        timeout: Time limit, in seconds, including the start of the process.

    Returns:
        Why the schema is invalid (cf. `trs_filer.io_schema.find_problem()`),
        or `None` if it is valid.

    Raises:
        InvalidRequest: The time limit was reached.
        InternalServerError: The validation failed.
    """
    deadline = time.monotonic() + timeout
    if not _SLOTS.acquire(timeout=timeout):
        raise _too_slow(timeout)
    try:
        remaining = max(deadline - time.monotonic(), 0.001)
        result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
            [
                sys.executable,
                "-I",
                "-m",
                "trs_filer.io_schema",
                str(math.ceil(remaining)),
            ],
            input=content,
            capture_output=True,
            timeout=remaining,
            check=True,
        )
        problem = json.loads(result.stdout)["problem"]
    except subprocess.TimeoutExpired as exc:
        raise _too_slow(timeout) from exc
    except subprocess.CalledProcessError as exc:
        # killed by a signal, e.g., at the limit of its CPU time (`SIGXCPU`)
        if exc.returncode < 0:
            raise _too_slow(timeout) from exc
        logger.error("Validation of I/O Schema file failed: %s", type(exc).__name__)
        raise InternalServerError from exc
    except (ValueError, KeyError, TypeError) as exc:
        logger.error("Validation of I/O Schema file failed: %s", type(exc).__name__)
        raise InternalServerError from exc
    finally:
        _SLOTS.release()
    if problem is not None and not isinstance(problem, str):
        logger.error("Validation of I/O Schema file returned no reason.")
        raise InternalServerError
    return problem


def check_io_schema(content: str, descriptor_type: str, timeout: float) -> None:
    """Check an I/O Schema file against the meta-schema of the profile.

    The reasons for rejecting a file say where the file breaks a rule of the
    meta-schema (as a JSON path, and the keyword of the meta-schema), but
    don't contain its values (see `InvalidRequest`).

    Args:
        content: Content of the file.
        descriptor_type: Descriptor type that the file is registered for (a
            supported one).
        timeout: Time limit of the validation against the meta-schema, in
            seconds.

    Raises:
        InvalidRequest: The file is not JSON (or not UTF-8), not a JSON
            object, doesn't name the meta-schema of the supported version of
            the profile in `$schema`, doesn't validate against it (also if it
            is nested too deeply, or can't be validated within the time
            limit), or names another descriptor type in
            `x-ga4gh-workflow.descriptor_type`.
        InternalServerError: The validation failed.
    """
    try:
        encoded = content.encode("utf-8")
        schema = json.loads(content, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        logger.error("I/O Schema file is not valid JSON.")
        raise InvalidRequest(f"{PREFIX} is not valid JSON.") from exc
    if not isinstance(schema, dict):
        logger.error("I/O Schema file is not a JSON object.")
        raise InvalidRequest(f"{PREFIX} must be a JSON object.")
    if schema.get("$schema") != META_SCHEMA_ID:
        logger.error("I/O Schema file names another meta-schema.")
        raise InvalidRequest(
            f"{PREFIX} must name the meta-schema of the GA4GH I/O Profile that "
            f"TRS-Filer supports in '$schema': '{META_SCHEMA_ID}'."
        )
    problem = _validate(encoded, timeout)
    if problem is not None:
        logger.error("I/O Schema file is invalid: %s", problem)
        raise InvalidRequest(problem)
    workflow = schema.get("x-ga4gh-workflow")
    if isinstance(workflow, dict) and workflow.get("descriptor_type") != (
        descriptor_type
    ):
        logger.error(
            "I/O Schema file of descriptor type '%s' names another one.",
            descriptor_type,
        )
        raise InvalidRequest(
            f"{PREFIX} of descriptor type {descriptor_type} names another "
            "descriptor type in 'x-ga4gh-workflow.descriptor_type'."
        )
