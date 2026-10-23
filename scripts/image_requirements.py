"""Print the requirements that the image build installs on the base image.

Used by the `Dockerfile`: prints the requirements of the app
(`requirements.txt`), one per line, without comments, blank lines and a
direct reference to a FOCA commit (`foca @ git+https://...@<sha>`,
temporary, see `scripts/check_release_pins.py`), as the base image has no
Git. Instead, it fails unless the base image has FOCA of that commit, i.e., a
FOCA version whose local part is `g<abbreviated commit>`, as set by
setuptools-scm (e.g., `0.16.1.dev16+g29af8a64a`).

Usage: `python scripts/image_requirements.py <requirements.txt>`.

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
    r"\s*foca\s*@\s*git\+https://github\.com/elixir-cloud-aai/foca"
    r"@(?P<sha>[0-9a-f]{40})\s*",
    re.IGNORECASE,
)
# A comment in a requirements file (as for pip: `#` at the start of a line or
# after whitespace, e.g., not in URL fragments)
COMMENT = re.compile(r"(^|\s)#.*$")
# The abbreviated commit in the local part of a version set by setuptools-scm
SCM_COMMIT = re.compile(r"\+g(?P<sha>[0-9a-f]{7,40})(\.|$)")


def read_requirements(text: str) -> list[str]:
    """Read the requirements of a requirements file.

    Args:
        text: Contents of the requirements file, with one requirement per
            line; comments (from a `#` at the start of a line or after
            whitespace on, as for pip) and blank lines are ignored.

    Returns:
        The requirements, stripped of surrounding whitespace.
    """
    requirements = []
    for line in text.splitlines():
        requirement = COMMENT.sub("", line).strip()
        if requirement:
            requirements.append(requirement)
    return requirements


def image_requirements(
    dependencies: Sequence[str], installed: str
) -> list[str]:
    """Get the requirements to install on the base image.

    Args:
        dependencies: Dependencies of the app.
        installed: Version of FOCA in the base image.

    Returns:
        The dependencies, without a direct reference to a FOCA commit.

    Raises:
        ValueError: A direct reference of FOCA is not to a full commit SHA of
            FOCA's repository, or the base image has FOCA of another commit.
    """
    requirements = []
    for dependency in dependencies:
        if not FOCA_REFERENCE.match(dependency):
            requirements.append(dependency)
            continue
        pin = FOCA_COMMIT.fullmatch(dependency)
        if pin is None:
            raise ValueError(
                "FOCA must be pinned to a full commit SHA of its repository: "
                f"'{dependency}'"
            )
        scm = SCM_COMMIT.search(installed)
        if scm is None or not pin["sha"].startswith(scm["sha"]):
            raise ValueError(
                f"The base image has FOCA {installed}, not of commit "
                f"{pin['sha']}"
            )
    return requirements


def main(argv: Sequence[str] | None = None) -> int:
    """Print the requirements to install on the base image.

    Args:
        argv: Command line arguments, without the program name: the path of
            `requirements.txt`.

    Returns:
        The exit status: 0 on success, 1 otherwise.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    dependencies = read_requirements(Path(args[0]).read_text())
    try:
        requirements = image_requirements(
            dependencies, importlib.metadata.version("foca")
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("\n".join(requirements))
    return 0


if __name__ == "__main__":
    sys.exit(main())
