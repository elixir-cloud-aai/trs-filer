"""Tests for the Docker build context rules."""

from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

import pytest

DOCKERIGNORE = Path(__file__).parents[1] / ".dockerignore"


def _matches(pattern: str, path: str) -> bool:
    """Check whether a pattern matches a path or one of its parent folders.

    Covers only the forms used in the file (`*`, `dir/`, `name`, `**/name`), not
    all of Docker's syntax.

    Args:
        pattern: The `.dockerignore` pattern, without a leading `!`.
        path: The path relative to the build context.

    Returns:
        Whether the pattern applies to the path.
    """
    candidate = PurePosixPath(path)
    any_depth = pattern.startswith("**/")
    name = pattern.removeprefix("**/").rstrip("/")
    return any(
        fnmatchcase(current.name if any_depth else str(current), name)
        for current in (candidate, *candidate.parents[:-1])
    )


def _in_build_context(path: str) -> bool:
    """Apply the `.dockerignore` rules in order; the last matching rule wins.

    Args:
        path: The path relative to the build context.

    Returns:
        Whether the path is sent to the build.
    """
    included = True
    for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and _matches(line.removeprefix("!"), path):
            included = line.startswith("!")
    return included


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "trs_filer/.env",
        "trs_filer/.env.local",
        "trs_filer/.envrc",
        "trs_filer/sub/.env",
        "trs_filer/prod.env",
        "trs_filer/server.pem",
        "trs_filer/tls.key",
        "trs_filer/credentials.json",
        "trs_filer/.netrc",
        "trs_filer/id_rsa",
        "trs_filer/id_ed25519",
        "trs_filer/id_ecdsa",
        "trs_filer/keystore.p12",
        "trs_filer/keystore.pfx",
        "trs_filer/.git-credentials",
        "trs_filer/.pypirc",
    ],
)
def test_secret_files_are_excluded(path: str) -> None:
    """Local secret files never reach the build, also not in included paths."""
    assert not _in_build_context(path)


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        "trs_filer/.env.example",
        ".git/config",
        "docs/index.md",
        "tests/test_dockerignore.py",
    ],
)
def test_other_files_are_excluded(path: str) -> None:
    """Paths outside the allowlist, and `.env` examples, stay out of the build."""
    assert not _in_build_context(path)


@pytest.mark.parametrize(
    "path",
    [
        "trs_filer/app.py",
        "trs_filer/config.yaml",
        "trs_filer/api/spec.yaml",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "LICENSE",
        "scripts/image_requirements.py",
        "update-config-map.sh",
    ],
)
def test_files_of_the_build_are_included(path: str) -> None:
    """The files that the image build copies stay in the build context."""
    assert _in_build_context(path)
