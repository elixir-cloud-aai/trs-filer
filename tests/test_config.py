"""Tests of the packaging, the image and the development config overlay."""

import fnmatch
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from typing import Any
import zipfile

from foca.config.config_parser import ConfigParser
from foca.models.config import Config
from packaging.requirements import Requirement
import pytest
import yaml

from trs_filer.custom_config import CustomConfig

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "trs_filer"
CONFIG_FILE = PACKAGE / "config.yaml"
CUSTOM_CONFIG_MODEL = "trs_filer.custom_config.CustomConfig"


def _parse_config() -> Config:
    """Parse the base config, with overlays from `FOCA_CONFIG_OVERLAY`.

    Returns:
        The parsed config.
    """
    return ConfigParser(
        config_file=CONFIG_FILE,
        custom_config_model=CUSTOM_CONFIG_MODEL,
        format_logs=False,
    ).config


def test_config_dev_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Docker Compose overlay sets the URL that Docker Compose publishes.

    Args:
        monkeypatch: Fixture to set `FOCA_CONFIG_OVERLAY` with.
    """
    monkeypatch.setenv("FOCA_CONFIG_OVERLAY", str(ROOT / "config.dev.yaml"))
    custom = (_parse_config().model_extra or {}).get("custom")
    assert isinstance(custom, CustomConfig)
    service = custom.service
    assert (service.url_prefix, service.external_host) == ("http", "localhost")
    compose = yaml.safe_load((ROOT / "docker-compose.yaml").read_text())
    assert compose["services"]["trs-filer"]["ports"] == [
        f"127.0.0.1:{service.external_port}:8080"
    ]


def _package_data() -> list[str]:
    """Get the files that the base config references, relative to the package.

    Returns:
        The config itself and the specs of the API.
    """
    config = yaml.safe_load(CONFIG_FILE.read_text())
    return [
        "config.yaml",
        *(path for spec in config["api"]["specs"].values() for path in spec["path"]),
    ]


def test_package_data() -> None:
    """Files that the base config references are package data."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    patterns = pyproject["tool"]["setuptools"]["package-data"]["trs_filer"]
    files = _package_data()
    assert "api/additions.openapi.yaml" in files
    for path in files:
        assert (PACKAGE / path).is_file(), path
        # setuptools matches the patterns from the package directory
        assert any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), path


def test_wheel_contents(tmp_path: Path) -> None:
    """The wheel contains the package data, as the image installs it.

    The tests run on an editable install, which reads the files from the
    source tree, so the wheel is built from a copy of the sources, with the
    build requirements of the dev environment.

    Args:
        tmp_path: Directory for the sources and the wheel.
    """
    source = tmp_path / "source"
    shutil.copytree(
        PACKAGE,
        source / "trs_filer",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for name in ["pyproject.toml", "README.md", "LICENSE"]:
        shutil.copy(ROOT / name, source / name)
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(tmp_path / "dist"),
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SETUPTOOLS_SCM_PRETEND_VERSION": "0.0.0"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (wheel,) = (tmp_path / "dist").glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        contents = set(archive.namelist())
    for path in _package_data():
        assert f"trs_filer/{path}" in contents, path
    assert "trs_filer-0.0.0.dist-info/licenses/LICENSE" in contents
    assert not any(name.startswith(("tests/", "scripts/")) for name in contents)


def _foca_requirement() -> Requirement:
    """Get the `foca` requirement of the app (`pyproject.toml`).

    Returns:
        The requirement.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    (foca,) = [
        requirement
        for requirement in map(Requirement, pyproject["project"]["dependencies"])
        if requirement.name == "foca"
    ]
    return foca


def _base_image_tag() -> str:
    """Get the tag of the FOCA base image (`Dockerfile`), without Python.

    Returns:
        The tag's version part (a FOCA release, or a date).
    """
    match = re.search(
        r"^FROM elixircloud/foca:(?P<version>[^-@\s]+)",
        (ROOT / "Dockerfile").read_text(),
        flags=re.MULTILINE,
    )
    assert match, "No FOCA base image in the Dockerfile"
    return match["version"]


def test_base_image_foca() -> None:
    """The base image has the FOCA that the `foca` requirement pins.

    So the image build does not install another FOCA on top of it: a FOCA
    release that satisfies the requirement or, for a direct reference to a
    FOCA commit (temporary, see `scripts/check_release_pins.py`), FOCA's
    development image (tagged by date) of that commit, which the `Dockerfile`
    records; the image build checks the FOCA version of the image
    (`scripts/image_requirements.py`).
    """
    foca, tag = _foca_requirement(), _base_image_tag()
    if foca.url is None:
        assert foca.specifier.contains(tag), (
            f"Base image has FOCA {tag}, but {foca} is required"
        )
    else:
        commit = re.fullmatch(
            r"git\+https://github\.com/elixir-cloud-aai/foca"
            r"@(?P<sha>[0-9a-f]{40})",
            foca.url,
        )
        assert commit, f"FOCA must be pinned to a full commit SHA, not {foca.url}"
        assert re.fullmatch(r"[0-9]{8}", tag), (
            "A FOCA commit needs FOCA's development image (tagged by date)"
        )
        dockerfile = (ROOT / "Dockerfile").read_text()
        assert f"## FOCA commit: {commit['sha']}\n" in dockerfile, (
            "The Dockerfile must record the FOCA commit of its base image"
        )


def test_python_version() -> None:
    """The app targets one Python version, that of the base image.

    That is, the Python version of the base image in the `Dockerfile` is the
    minimum of `requires-python` and the only one in the classifiers, and all
    workflows use it.
    """
    match = re.search(
        r"^FROM elixircloud/foca:[^-@\s]+-py(?P<version>3\.\d+)@",
        (ROOT / "Dockerfile").read_text(),
        flags=re.MULTILINE,
    )
    assert match, "No Python version in the base image tag of the Dockerfile"
    image = match["version"]
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert pyproject["project"]["requires-python"] == f">={image}"
    prefix = "Programming Language :: Python :: 3."
    classifiers = [
        classifier.removeprefix("Programming Language :: Python :: ")
        for classifier in pyproject["project"]["classifiers"]
        if classifier.startswith(prefix)
    ]
    assert classifiers == [image]
    workflows = sorted((ROOT / ".github" / "workflows").glob("*"))
    assert [workflow.suffix for workflow in workflows] == [".yml"] * len(workflows)
    for workflow in workflows:
        jobs = yaml.safe_load(workflow.read_text())["jobs"]
        for name, job in jobs.items():
            for step in job.get("steps", []):
                if "actions/setup-python@" in step.get("uses", ""):
                    version = step["with"]["python-version"]
                    assert version == image, f"{workflow.name}: {name}"
    # TEMPORARY: the chart's config Job reads the installed base config
    # (#135)
    job = (
        ROOT / "deployment" / "templates" / "trs-filer-configmap-job.yaml"
    ).read_text()
    assert f"/usr/local/lib/python{image}/site-packages/trs_filer/" in job


def _ci_gate() -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the gate `passed` of the CI workflow.

    Returns:
        The other jobs of the workflow, by ID, and the gate's only step.
    """
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    jobs = workflow["jobs"]
    gate = jobs.pop("passed")
    assert gate["name"] == "CI passed"
    assert gate["if"] == "always()"
    assert sorted(gate["needs"]) == sorted(jobs)
    (step,) = gate["steps"]
    return jobs, step


def test_ci_gate() -> None:
    """The gate `passed` of the CI workflow checks every other job.

    The ruleset requires the gate only, so a job that it doesn't check could
    fail without blocking pull requests. The shared gate action (tested in
    `elixir-cloud-aai/.github`) gets the results of all needed jobs, pinned
    to the full commit SHA of a release (`# vX.Y.Z`; Dependabot bumps it).
    """
    _, step = _ci_gate()
    assert re.fullmatch(
        r"elixir-cloud-aai/\.github/actions/gate@[0-9a-f]{40}", step["uses"]
    )
    assert step["with"]["needs"] == "${{ toJSON(needs) }}"


def test_ci_gate_conditions() -> None:
    """The gate may skip a job exactly where the job's condition is false.

    Only `pins` and `publish` may be skipped; `allow-skipped` names each of
    them under the negated `if:` of the job, so that a job skipped where it
    should run fails the gate.
    """
    jobs, step = _ci_gate()
    allowed = " ".join(step["with"]["allow-skipped"].split())
    named = re.findall(r"&& '([a-z-]+)' \|\| ''", allowed)
    assert sorted(named) == ["pins", "publish"]
    conditions = [
        f"!({' '.join(jobs[job]['if'].split())}) && '{job}' || ''" for job in named
    ]
    assert allowed == f"${{{{ format('{{0}} {{1}}', {', '.join(conditions)}) }}}}"
