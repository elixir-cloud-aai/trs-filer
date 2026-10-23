"""Tests of the release pin check (`scripts/check_release_pins.py`)."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_release_pins.py"

# `scripts/` is not a package, so the script is loaded from its file
_spec = importlib.util.spec_from_file_location("check_release_pins", SCRIPT)
assert _spec and _spec.loader
check_release_pins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_release_pins)

DOCKERFILE = """## A comment
FROM elixircloud/foca:{tag}@sha256:{digest}
USER 1000
"""
CHART = """apiVersion: v2
name: app
version: 0.0.0
appVersion: "dev"
dependencies:
  # A comment
  - name: foca-common
    version: {version}
    repository: oci://ghcr.io/elixir-cloud-aai/charts
"""
DIGEST = "0" * 64


def _write(
    root: Path,
    requirements: str = "foca>=0.17.0,<0.18\n",
    dev_requirements: str = "pytest>=8.3\n",
    tag: str = "0.17.0-py3.13",
    chart_version: str = "0.2.0",
) -> Path:
    """Write the files that the script checks.

    Args:
        root: Directory to write them to.
        requirements: Contents of `requirements.txt`.
        dev_requirements: Contents of `requirements_dev.txt`.
        tag: Tag of the base image in the `Dockerfile`.
        chart_version: Version of the chart's dependency.

    Returns:
        The directory.
    """
    (root / "deployment").mkdir()
    (root / "requirements.txt").write_text(requirements)
    (root / "requirements_dev.txt").write_text(dev_requirements)
    (root / "Dockerfile").write_text(
        DOCKERFILE.format(tag=tag, digest=DIGEST)
    )
    (root / "deployment" / "Chart.yaml").write_text(
        CHART.format(version=chart_version)
    )
    return root


def test_release_pins(tmp_path: Path) -> None:
    """Pins of released versions are accepted, comments are ignored.

    Args:
        tmp_path: Temporary directory.
    """
    root = _write(
        tmp_path,
        requirements=(
            "# FOCA 0.17.0rc1 @ a comment\n"
            "\n"
            "connexion>=2.15.1,<3\n"
            "foca[x]>=0.17.0  # a comment: foca @ git+https://example.org\n"
        ),
    )
    assert check_release_pins.find_dev_pins(root) == []


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        (
            {
                "requirements": (
                    "foca @ git+https://github.com/elixir-cloud-aai/foca@"
                    + "a" * 40
                    + "\n"
                )
            },
            "requirements.txt: requirement 'foca @ git+https://github.com/"
            f"elixir-cloud-aai/foca@{'a' * 40}' is a direct reference",
        ),
        (
            {"requirements": "foca[x] @ https://example.org/foca.tar.gz\n"},
            "requirements.txt: requirement 'foca[x] @ "
            "https://example.org/foca.tar.gz' is a direct reference",
        ),
        (
            {"requirements": "Foca [x]@https://example.org/foca.tar.gz\n"},
            "requirements.txt: requirement 'Foca [x]@"
            "https://example.org/foca.tar.gz' is a direct reference",
        ),
        (
            {"requirements": "git+https://github.com/example/foca@dev\n"},
            "requirements.txt: requirement "
            "'git+https://github.com/example/foca@dev' can't be checked",
        ),
        (
            {"requirements": "foca-0.17.0rc1-py3-none-any.whl\n"},
            "requirements.txt: requirement 'foca-0.17.0rc1-py3-none-any.whl' "
            "can't be checked",
        ),
        (
            {
                "requirements": (
                    "FOCA-0.17.0RC1.TAR.GZ --hash=sha256:" + "0" * 64 + "\n"
                )
            },
            "requirements.txt: requirement 'FOCA-0.17.0RC1.TAR.GZ "
            f"--hash=sha256:{'0' * 64}' can't be checked",
        ),
        (
            {"requirements": "foca-0.17.0rc1-py3-none-any.whl#egg=foca\n"},
            "requirements.txt: requirement "
            "'foca-0.17.0rc1-py3-none-any.whl#egg=foca' can't be checked",
        ),
        (
            {"requirements": "-e ./foca\n"},
            "requirements.txt: requirement '-e ./foca' can't be checked",
        ),
        (
            {"requirements": "foca>=0.17.0rc1,<0.18\n"},
            "requirements.txt: requirement 'foca>=0.17.0rc1,<0.18' names a "
            "pre-release",
        ),
        (
            {"requirements": "connexion==3.0.dev0; python_version < '3.14'\n"},
            "requirements.txt: requirement 'connexion==3.0.dev0; "
            "python_version < '3.14'' names a pre-release",
        ),
        (
            {"requirements": "foca==0.17.0+gabc1234\n"},
            "requirements.txt: requirement 'foca==0.17.0+gabc1234' names a "
            "local version",
        ),
        (
            {"dev_requirements": "x @ https://example.org/x.zip\n"},
            "requirements_dev.txt: requirement 'x @ https://example.org/x.zip'"
            " is a direct reference",
        ),
        (
            {"tag": "20261023-py3.13"},
            "Dockerfile: base image tag '20261023-py3.13' is not a release "
            "tag (<X.Y.Z>-py<X.Y>)",
        ),
        (
            {"tag": "0.17.0"},
            "Dockerfile: base image tag '0.17.0' is not a release tag "
            "(<X.Y.Z>-py<X.Y>)",
        ),
        (
            {"chart_version": "0.2.0-rc1"},
            "deployment/Chart.yaml: dependency version '0.2.0-rc1' is not a "
            "release version",
        ),
        (
            {"chart_version": '"~0.2.0"'},
            "deployment/Chart.yaml: dependency version '~0.2.0' is not a "
            "release version",
        ),
    ],
    ids=[
        "git",
        "url",
        "extras-spaces",
        "unnamed-url",
        "wheel",
        "archive-hash",
        "wheel-fragment",
        "editable",
        "pre-release",
        "dev-marker",
        "local",
        "dev-requirements",
        "dated-image",
        "no-python",
        "chart-rc",
        "chart-range",
    ],
)
def test_dev_pins(
    tmp_path: Path, kwargs: dict[str, str], error: str
) -> None:
    """Pins of development versions are found.

    Args:
        tmp_path: Temporary directory.
        kwargs: Contents of the files that differ from releases.
        error: Expected description of the pin.
    """
    assert check_release_pins.find_dev_pins(
        _write(tmp_path, **kwargs)
    ) == [error]


@pytest.mark.parametrize(
    "requirement",
    [
        "foca>=0.17.0",
        "rcpackage>=1.0",
        "dev-tools[a]>=2.0.post1",
        "abc==1.0.0b1",
    ],
    ids=["release", "name-rc", "post-release", "beta"],
)
def test_requirement_versions(tmp_path: Path, requirement: str) -> None:
    """Only versions are checked for pre-releases, not names or extras.

    Args:
        tmp_path: Temporary directory.
        requirement: Requirement to check.
    """
    pins = check_release_pins.find_dev_pins(
        _write(tmp_path, requirements=f"{requirement}\n")
    )
    assert pins == (
        [
            f"requirements.txt: requirement '{requirement}' names a "
            "pre-release"
        ]
        if requirement == "abc==1.0.0b1"
        else []
    )


def test_chart_without_dependencies(tmp_path: Path) -> None:
    """Charts without dependencies pass.

    Args:
        tmp_path: Temporary directory.
    """
    root = _write(tmp_path)
    chart = root / "deployment" / "Chart.yaml"
    chart.write_text(
        "apiVersion: v2\nname: app\nversion: 2.0.0\nappVersion: 2.0.0\n"
    )
    assert check_release_pins.find_dev_pins(root) == []
    chart.write_text("name: app\ndependencies: []  # none\n")
    assert check_release_pins.find_dev_pins(root) == []


@pytest.mark.parametrize(
    "dependencies",
    [
        "dependencies: [{name: a, version: 1.0.0-rc1}]\n",
        "dependencies:\n  - {name: a, version: 1.0.0-rc1}\n",
    ],
    ids=["flow-list", "flow-item"],
)
def test_chart_dependencies_flow(tmp_path: Path, dependencies: str) -> None:
    """Dependencies in flow style are reported, as they can't be checked.

    Args:
        tmp_path: Temporary directory.
        dependencies: Dependencies section of the chart.
    """
    root = _write(tmp_path)
    (root / "deployment" / "Chart.yaml").write_text(
        f"name: app\n{dependencies}"
    )
    assert check_release_pins.find_dev_pins(root) == [
        "deployment/Chart.yaml: dependencies in flow style can't be checked"
    ]


def test_chart_dependencies(tmp_path: Path) -> None:
    """All dependencies of the chart are checked, and only their versions.

    Args:
        tmp_path: Temporary directory.
    """
    root = _write(tmp_path)
    (root / "deployment" / "Chart.yaml").write_text(
        """apiVersion: v2
name: app
version: 0.0.0
dependencies:  # A comment
  - name: foca-common
    version: 0.2.0
    repository: oci://ghcr.io/elixir-cloud-aai/charts
  # A comment
  - version: "1.0.0-rc1"
    name: other
- name: indentless
  version: 1.0.0-rc2

maintainers:
  - name: someone
    version: not-a-dependency
annotations:
  version: dev
"""
    )
    assert check_release_pins.find_dev_pins(root) == [
        "deployment/Chart.yaml: dependency version '1.0.0-rc1' is not a "
        "release version",
        "deployment/Chart.yaml: dependency version '1.0.0-rc2' is not a "
        "release version",
    ]


def test_no_base_image(tmp_path: Path) -> None:
    """A `Dockerfile` without the FOCA base image is reported.

    Args:
        tmp_path: Temporary directory.
    """
    root = _write(tmp_path)
    (root / "Dockerfile").write_text("FROM python:3.13\n")
    assert check_release_pins.find_dev_pins(root) == [
        "Dockerfile: no elixircloud/foca base image"
    ]


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`main()` reports pins as GitHub errors, and fails if there are any.

    Args:
        tmp_path: Temporary directory.
        capsys: Captured output.
    """
    released = tmp_path / "released"
    released.mkdir()
    assert check_release_pins.main([str(_write(released))]) == 0
    assert capsys.readouterr().err == ""
    dev = tmp_path / "dev"
    dev.mkdir()
    assert check_release_pins.main(
        [str(_write(dev, tag="20261023-py3.13"))]
    ) == 1
    assert capsys.readouterr().err == (
        "::error::Dockerfile: base image tag '20261023-py3.13' is not a "
        "release tag (<X.Y.Z>-py<X.Y>): pin the released version before "
        "releasing\n"
    )


def test_main_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without arguments, `main()` checks this repository.

    Args:
        monkeypatch: Patches of the check.
    """
    roots: list[Path] = []

    def find_dev_pins(root: Path) -> list[str]:
        """Record the checked root.

        Args:
            root: Root directory of the repository.

        Returns:
            No pins.
        """
        roots.append(root)
        return []

    monkeypatch.setattr(check_release_pins, "find_dev_pins", find_dev_pins)
    assert check_release_pins.main([]) == 0
    assert roots == [ROOT]


def test_repository_pins() -> None:
    """The repository's own files can be read by the check.

    While FOCA is pinned to a commit, exactly the FOCA requirement and the
    base image are reported.
    """
    pins = check_release_pins.find_dev_pins(ROOT)
    assert all(
        pin.startswith("requirements.txt: requirement 'foca @ ")
        or pin.startswith("Dockerfile: base image tag ")
        for pin in pins
    ), pins


def test_script(tmp_path: Path) -> None:
    """The script runs as the workflow calls it.

    Args:
        tmp_path: Temporary directory.
    """
    shutil.copytree(ROOT / "scripts", tmp_path / "scripts")
    _write(tmp_path, chart_version="0.2.0-rc1")
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [
            sys.executable,
            "-I",
            str(tmp_path / "scripts" / "check_release_pins.py"),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert (result.returncode, result.stdout) == (1, "")
    assert "dependency version '0.2.0-rc1'" in result.stderr
