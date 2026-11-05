"""Print the locked requirements that the image build installs on the base image.

Used by the `Dockerfile`: reads the requirements that `uv export` writes from
`uv.lock` (the dependencies of the app, `project.dependencies` of
`pyproject.toml`, with all their own dependencies, at exact versions and with
hashes) and prints them without a direct reference to a FOCA commit
(`foca @ git+https://...@<sha>`, temporary, see
`scripts/check_release_pins.py`), as the base image has no Git and such a
reference has no hash. Instead, it fails unless the base image has FOCA of
that commit, i.e., a FOCA version whose local part is `g<abbreviated
commit>`, as set by setuptools-scm (e.g., `0.16.1.dev7+gdb6998cae`). The
dependencies of FOCA stay locked and hashed. A locked FOCA release is kept,
but the build fails unless the base image has exactly that release, so that
the lock doesn't install another FOCA on top of it (e.g., revert an update
of the base image): update the base image and the lock together.

Usage: `python scripts/image_requirements.py <requirements>`, where
`<requirements>` is the output of
`uv export --frozen --no-dev --no-emit-project`.

Only the stdlib is used, so the image build runs it before installing the app.
"""

from collections.abc import Sequence
import importlib.metadata
from pathlib import Path
import re
import sys

# A requirement of FOCA that is a direct reference, and one to a commit
FOCA_REFERENCE = re.compile(r"\s*foca\s*(\[[^\]]*\])?\s*@", re.IGNORECASE)
FOCA_COMMIT = re.compile(
    r"\s*foca\s*@\s*git\+https://github\.com/elixir-cloud-aai/foca@(?P<sha>[0-9a-f]{40})\s*",
    re.IGNORECASE,
)
# Any requirement of FOCA (not of a package whose name starts with `foca`), and
# a locked release of FOCA, as `uv export` writes it (hashes continued on the
# next lines)
FOCA = re.compile(r"\s*foca(?![A-Za-z0-9._-])", re.IGNORECASE)
FOCA_LOCKED = re.compile(
    r"\s*foca\s*==\s*(?P<version>[^\s;\\\[\]]+)\s*\\?\s*", re.IGNORECASE
)
# The abbreviated commit in the local part of a version set by setuptools-scm
SCM_COMMIT = re.compile(r"\+g(?P<sha>[0-9a-f]{7,40})(\.|$)")


def entries(requirements: str) -> list[list[str]]:
    """Split requirements, as written by `uv export`, into entries.

    Args:
        requirements: Requirements file with a requirement per entry, whose
            continuation lines (hashes, comments) are indented.

    Returns:
        The entries, as lists of lines: a requirement with its continuation
        lines, or a single line that is no requirement (e.g., a comment).
    """
    result: list[list[str]] = []
    for line in requirements.splitlines():
        if line[:1].isspace() and result:
            result[-1].append(line)
        else:
            result.append([line])
    return result


def image_requirements(requirements: str, installed: str) -> str:
    """Get the requirements to install on the base image.

    Args:
        requirements: Locked requirements of the app, as written by
            `uv export`.
        installed: Version of FOCA in the base image.

    Returns:
        The requirements, without a direct reference to a FOCA commit (and
        its continuation lines).

    Raises:
        ValueError: A direct reference of FOCA is not to a full commit SHA of
            FOCA's repository, another requirement of FOCA is not a plain
            locked release (`foca==<version>`, e.g., with a marker), or the
            base image has FOCA of another commit or another release than
            the locked one (compared as written).
    """
    kept = []
    for entry in entries(requirements):
        requirement = entry[0]
        if not FOCA.match(requirement):
            kept.extend(entry)
            continue
        if not FOCA_REFERENCE.match(requirement):
            locked = FOCA_LOCKED.fullmatch(requirement)
            if locked is None:
                raise ValueError(
                    f"FOCA must be locked as 'foca==<version>': '{requirement.strip()}'"
                )
            if locked["version"] != installed:
                raise ValueError(
                    f"The base image has FOCA {installed}, but "
                    f"{locked['version']} is locked"
                )
            kept.extend(entry)
            continue
        pin = FOCA_COMMIT.fullmatch(requirement)
        if pin is None:
            raise ValueError(
                f"FOCA must be pinned to a full commit SHA of its repository: "
                f"'{requirement.strip()}'"
            )
        scm = SCM_COMMIT.search(installed)
        if scm is None or not pin["sha"].startswith(scm["sha"]):
            raise ValueError(
                f"The base image has FOCA {installed}, not of commit {pin['sha']}"
            )
    return "".join(f"{line}\n" for line in kept)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the requirements to install on the base image.

    Args:
        argv: Command line arguments, without the program name: the path of
            the requirements written by `uv export`.

    Returns:
        The exit status: 0 on success, 1 otherwise.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        requirements = image_requirements(
            Path(args[0]).read_text(), importlib.metadata.version("foca")
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(requirements, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
