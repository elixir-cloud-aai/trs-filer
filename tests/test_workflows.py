"""Tests for the names and the publishing conditions of the workflows."""

from pathlib import Path
import re
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _load(path: Path) -> dict[str, Any]:
    """Load a workflow file.

    Args:
        path: The path of the workflow file.

    Returns:
        The workflow.
    """
    workflow: dict[str, Any] = yaml.safe_load(path.read_text())
    return workflow


def test_workflow_files() -> None:
    """The workflows are `ci.yml` and `release.yml`."""
    names = {path.name: _load(path)["name"] for path in WORKFLOWS.iterdir()}
    assert names == {"ci.yml": "CI", "release.yml": "Release"}


def test_job_names_unique() -> None:
    """Job names are unique across all workflows (they name the checks)."""
    names = [
        job["name"]
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for job in _load(path)["jobs"].values()
    ]
    assert len(names) == len(set(names))


def test_publish_condition() -> None:
    """`push` and `publish` run exactly where `PUBLISH` of `ci.yml` is "true".

    The gate allows them to be skipped only where their condition is false
    (`tests/test_config.py`), so the jobs and `PUBLISH` must agree.
    """
    workflow = _load(WORKFLOWS / "ci.yml")
    publish = workflow["env"]["PUBLISH"]
    assert publish.startswith("${{ github.event_name == 'push' && ")
    jobs = workflow["jobs"]
    assert f"${{{{ {jobs['push']['if']} }}}}" == publish
    assert jobs["publish"]["if"] == jobs["push"]["if"]


def test_upstream_owner() -> None:
    """`ci.yml` marks upstream runs by the owner `elixir-cloud-aai` only.

    A typo in, or an inverted, owner check would quietly change upstream runs
    (e.g., release readiness findings to warnings), so every check compares
    with `==`.
    """
    text = (WORKFLOWS / "ci.yml").read_text()
    checks = re.findall(r"github\.repository_owner\s*(\S+)\s*'([^']*)'", text)
    assert checks
    assert len(checks) == text.count("github.repository_owner")
    assert set(checks) == {("==", "elixir-cloud-aai")}


def test_secrets_in_environments() -> None:
    """Only jobs in the `dev-images` or `release` environment use secrets.

    The Docker Hub secrets are kept in these environments (branch `dev` and
    required reviewers), not as repository secrets; Codecov's token is the
    only repository secret.
    """
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for name, job in _load(path)["jobs"].items():
            text = yaml.safe_dump(job)
            used = set(re.findall(r"secrets\.([A-Z_]+)", text)) - {"CODECOV_TOKEN"}
            if used:
                environment = job.get("environment")
                if isinstance(environment, dict):
                    environment = environment["name"]
                expected = "release" if path.name == "release.yml" else "dev-images"
                assert environment == expected, f"{path.name}: {name}"


def test_image_name() -> None:
    """Both workflows publish the same image, of `DOCKERHUB_ORG`."""
    expected = "docker.io/${{ vars.DOCKERHUB_ORG || 'elixircloud' }}/trs-filer"
    for name in ("ci.yml", "release.yml"):
        assert _load(WORKFLOWS / name)["env"]["IMAGE_NAME"] == expected
