"""Tests of the requirements of the image build.

Cf. `scripts/image_requirements.py`.
"""

import importlib.metadata
import importlib.util
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/image_requirements.py"

# `scripts/` is not a package, so the script is loaded from its file
_spec = importlib.util.spec_from_file_location("image_requirements", SCRIPT)
assert _spec and _spec.loader
image_requirements = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(image_requirements)

SHA = "29af8a64a2b0aae21845fa37a4a54076811f62bf"
PIN = f"foca @ git+https://github.com/elixir-cloud-aai/foca@{SHA}"


@pytest.mark.parametrize(
    "installed",
    [
        "0.16.1.dev16+g29af8a64a",
        "0.16.1.dev16+g29af8a6",
        "0.16.1.dev16+g29af8a64a.d20261023",
        f"0.16.1.dev16+g{SHA}",
    ],
)
def test_commit_pin(installed: str) -> None:
    """A pin of the base image's FOCA commit is left out.

    Args:
        installed: Version of FOCA in the base image.
    """
    dependencies = ["connexion>=2.15.1,<3", PIN, "gunicorn==22.0.0"]
    assert image_requirements.image_requirements(
        dependencies, installed
    ) == ["connexion>=2.15.1,<3", "gunicorn==22.0.0"]


def test_release() -> None:
    """Requirements of FOCA releases are kept."""
    dependencies = ["foca>=0.17.0,<0.18", "gunicorn==22.0.0"]
    assert image_requirements.image_requirements(
        dependencies, "0.17.0"
    ) == dependencies


@pytest.mark.parametrize(
    "installed",
    [
        "0.17.0",
        "0.16.1.dev7+gdb6998cae",
        "0.16.1.dev16+g29af8",
        "0.16.1+local",
    ],
)
def test_other_commit(installed: str) -> None:
    """The build fails unless the base image has FOCA of the pinned commit.

    Args:
        installed: Version of FOCA in the base image.
    """
    with pytest.raises(
        ValueError, match=f"has FOCA {re.escape(installed)}, not of commit"
    ):
        image_requirements.image_requirements([PIN], installed)


@pytest.mark.parametrize(
    "dependency",
    [
        "foca @ git+https://github.com/elixir-cloud-aai/foca@dev",
        "foca @ git+https://github.com/example/foca@" + SHA,
        "foca[x] @ https://example.org/foca.tar.gz",
        "FOCA@https://example.org/foca.tar.gz",
    ],
)
def test_other_reference(dependency: str) -> None:
    """Direct references of FOCA other than to a commit are refused.

    Args:
        dependency: Requirement of FOCA.
    """
    with pytest.raises(ValueError, match="full commit SHA"):
        image_requirements.image_requirements(
            [dependency], "0.16.1.dev16+g29af8a64a"
        )


def test_read_requirements() -> None:
    """Comments and blank lines of requirements files are left out."""
    text = (
        "# A comment\n"
        "\n"
        "connexion>=2.15.1,<3  # a comment\n"
        "  gunicorn==22.0.0\n"
        "x @ https://example.org/x.zip#egg=x\n"
    )
    assert image_requirements.read_requirements(text) == [
        "connexion>=2.15.1,<3",
        "gunicorn==22.0.0",
        "x @ https://example.org/x.zip#egg=x",
    ]


def test_main(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`main()` prints the requirements, or the error.

    Args:
        tmp_path: Temporary directory.
        capsys: Captured output.
        monkeypatch: Patches of the installed FOCA version.
    """
    monkeypatch.setattr(
        importlib.metadata, "version", lambda name: "0.17.0"
    )
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("# FOCA\nfoca>=0.1\ngunicorn\n")
    assert image_requirements.main([str(requirements)]) == 0
    assert capsys.readouterr().out == "foca>=0.1\ngunicorn\n"
    requirements.write_text(f"{PIN}\n")
    assert image_requirements.main([str(requirements)]) == 1
    assert capsys.readouterr().err == (
        f"error: The base image has FOCA 0.17.0, not of commit {SHA}\n"
    )


def test_script(tmp_path: Path) -> None:
    """The script runs as the image build calls it.

    Args:
        tmp_path: Temporary directory.
    """
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("gunicorn==22.0.0\n")
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [sys.executable, "-I", str(SCRIPT), str(requirements)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "gunicorn==22.0.0\n",
        "",
    )


def test_repository_requirements() -> None:
    """The base image of the `Dockerfile` matches the FOCA commit pin.

    If `requirements.txt` pins a FOCA commit, the `Dockerfile` names it
    (`## FOCA commit: <sha>`) next to the development image of that commit.
    """
    pins = [
        requirement
        for requirement in image_requirements.read_requirements(
            (ROOT / "requirements.txt").read_text()
        )
        if image_requirements.FOCA_REFERENCE.match(requirement)
    ]
    dockerfile = (ROOT / "Dockerfile").read_text()
    for pin in pins:
        match = image_requirements.FOCA_COMMIT.fullmatch(pin)
        assert match is not None
        assert f"## FOCA commit: {match['sha']}\n" in dockerfile
