"""Checks of GA4GH I/O Schema files on registration (experimental).

Cf. `custom.io_schema` and `docs/io-schema.md`.
"""

import json
import logging
import subprocess
import sys

from trs_filer.errors.exceptions import InternalServerError, InvalidRequest
from trs_filer.io_schema import META_SCHEMA_ID, PREFIX

logger = logging.getLogger(__name__)


def _validate(content: str, timeout: float) -> str | None:
    """Validate an I/O Schema in a process of its own, with a time limit.

    The process runs `python -I -m trs_filer.io_schema` with the Python of
    the app; it is killed when the time limit is reached, so that slow
    validations don't hold up the app.

    Args:
        content: The I/O Schema, a JSON object.
        timeout: Time limit, in seconds, including the start of the process.

    Returns:
        Why the schema is invalid (cf. `trs_filer.io_schema.find_problem()`),
        or `None` if it is valid.

    Raises:
        InvalidRequest: The time limit was reached.
        InternalServerError: The validation failed.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-m", "trs_filer.io_schema"],
            input=content,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=True,
        )
        problem = json.loads(result.stdout)["problem"]
    except subprocess.TimeoutExpired as exc:
        logger.error("I/O Schema file not checked within %s s.", timeout)
        raise InvalidRequest(
            f"{PREFIX} could not be checked within the time limit of "
            f"{timeout:g} s; simplify it (e.g., nest its schemas less deeply)."
        ) from exc
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
        logger.error("Validation of I/O Schema file failed: %s", type(exc).__name__)
        raise InternalServerError from exc
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
        InvalidRequest: The file is not JSON, not a JSON object, doesn't name
            the meta-schema of the supported version of the profile in
            `$schema`, doesn't validate against it (also if it is nested too
            deeply, or can't be validated within the time limit), or names
            another descriptor type in `x-ga4gh-workflow.descriptor_type`.
        InternalServerError: The validation failed.
    """
    try:
        schema = json.loads(content)
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
    problem = _validate(content, timeout)
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
