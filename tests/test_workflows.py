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
    """The workflows are `ci.yml`, `release.yml` and `scan.yml`."""
    names = {path.name: _load(path)["name"] for path in WORKFLOWS.iterdir()}
    assert names == {"ci.yml": "CI", "release.yml": "Release", "scan.yml": "Scan"}


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
    """The workflows publish and scan the same image, of `DOCKERHUB_ORG`."""
    expected = "docker.io/${{ vars.DOCKERHUB_ORG || 'elixircloud' }}/trs-filer"
    for name in ("ci.yml", "release.yml", "scan.yml"):
        assert _load(WORKFLOWS / name)["env"]["IMAGE_NAME"] == expected


def _steps(job: dict[str, Any], action: str) -> list[dict[str, Any]]:
    """Get the steps of a job that use an action.

    Args:
        job: The job.
        action: The action, without its ref (e.g., `actions/checkout`).

    Returns:
        The steps that use the action.
    """
    return [
        step
        for step in job.get("steps", [])
        if step.get("uses", "").startswith(f"{action}@")
    ]


SCAN_ACTION = "elixir-cloud-aai/.github/actions/scan-image"


def test_scan_jobs() -> None:
    """Images are scanned in jobs without credentials or signing identity.

    The Trivy action resolves the Trivy binary at run time, so the jobs that
    run it have no environment (and so no Docker Hub secrets), no secrets
    and no permissions beyond reading the repository and uploading to code
    scanning. Each workflow has exactly one such job, `scan`.
    """
    for path in sorted(WORKFLOWS.glob("*.yml")):
        jobs = _load(path)["jobs"]
        scanning = [name for name, job in jobs.items() if _steps(job, SCAN_ACTION)]
        assert scanning == ["scan"], path.name
        job = jobs["scan"]
        assert "environment" not in job, path.name
        assert "secrets." not in yaml.safe_dump(job), path.name
        assert set(job["permissions"].items()) <= {
            ("contents", "read"),
            ("security-events", "write"),
        }, path.name


def test_publish_after_scan() -> None:
    """Images are attested, signed and tagged only after the scan passed.

    `push` pushes the image by digest with SBOM and provenance attestations;
    `publish` needs `scan` (which scans that digest), attests the digest's
    build provenance and signs it (keyless, with the job's OIDC token)
    before it tags it.
    """
    for name in ("ci.yml", "release.yml"):
        jobs = _load(WORKFLOWS / name)["jobs"]
        assert "push" in jobs["scan"]["needs"], name
        assert "scan" in jobs["publish"]["needs"], name
        (build,) = _steps(jobs["push"], "docker/build-push-action")
        assert build["with"]["sbom"] is True, name
        assert build["with"]["provenance"] == "mode=max", name
        publish = jobs["publish"]
        assert publish["permissions"]["id-token"] == "write", name
        assert publish["permissions"]["attestations"] == "write", name
        steps = {step["name"]: step for step in publish["steps"]}
        attest = steps["Attest build provenance"]
        assert attest["uses"].startswith("actions/attest-build-provenance@")
        assert attest["with"]["subject-digest"] == "${{ env.DIGEST }}", name
        assert attest["with"]["push-to-registry"] is True, name
        sign = steps["Sign image"]
        assert sign["run"] == 'cosign sign --yes "${IMAGE_NAME}@${DIGEST}"', name
        # Steps of `ci.yml` run only for the head of the branch, as the tags
        assert attest.get("if") == sign.get("if") == steps["Tag image"].get("if")
        names = list(steps)
        assert names.index("Attest build provenance") < names.index("Tag image")
        assert names.index("Sign image") < names.index("Tag image")


def test_release_chart_signed() -> None:
    """The release workflow attests and signs the chart before the release.

    The Sigstore bundles (`<chart>.tgz.sigstore.json`) are written to
    `dist/`, so that they are uploaded with the chart.
    """
    publish = _load(WORKFLOWS / "release.yml")["jobs"]["publish"]
    steps = {step["name"]: step for step in publish["steps"]}
    assert steps["Attest chart provenance"]["with"]["subject-path"] == "dist/*.tgz"
    sign = steps["Sign chart"]["run"]
    assert "for chart in dist/*.tgz; do" in sign
    assert 'cosign sign-blob --yes --bundle "${chart}.sigstore.json" "${chart}"' in sign
    names = list(steps)
    # The downloaded chart is the one of `prepare`, checked before signing
    check = steps["Check chart"]
    assert check["env"]["SHA256"] == "${{ needs.prepare.outputs.chart_sha256 }}"
    assert '[[ ! "${SHA256}" =~ ^[0-9a-f]{64}$ ]]' in check["run"]
    assert '"${#files[@]}" -ne 1' in check["run"]
    assert "sha256sum --check --strict" in check["run"]
    assert names.index("Download chart") < names.index("Check chart")
    assert names.index("Check chart") < names.index("Attest chart provenance")
    assert names.index("Attest chart provenance") < names.index("Create release")
    assert names.index("Sign chart") < names.index("Create release")
    assert 'gh release upload "${TAG}" dist/*' in steps["Create release"]["run"]


def test_verification_commands() -> None:
    """The verification commands name the workflows that sign the images.

    `docs/operations.md` verifies release images and charts with the
    identity of `release.yml` at the release tag (`gh attestation verify`
    and `cosign verify` of the image, both of the chart), and `dev` images
    with that of `ci.yml` at `refs/heads/dev`, so renaming a workflow must
    update them.
    """
    text = " ".join((ROOT / "docs" / "operations.md").read_text().split())
    workflows = re.findall(r"trs-filer/\.github/workflows/([a-z-]+\.yml)", text)
    assert sorted(set(workflows)) == ["ci.yml", "release.yml"]
    assert all((WORKFLOWS / workflow).is_file() for workflow in workflows)
    release = "trs-filer/.github/workflows/release.yml"
    assert text.count(f"{release}@refs/tags/v{{{{ version }}}}") == 2
    assert text.count(f"--signer-workflow elixir-cloud-aai/{release}") == 2
    assert text.count("--source-ref refs/tags/v{{ version }}") == 2
    assert "trs-filer/.github/workflows/ci.yml@refs/heads/dev" in text
    assert "--source-ref refs/heads/dev" in text


def test_shared_actions_pinned() -> None:
    """The shared actions of `elixir-cloud-aai/.github` are pinned alike.

    All pins name the same full commit SHA and, in a comment, its release
    (`@<sha> # vX.Y.Z`), so that Dependabot bumps them together. Whether the
    commit is the release's commit isn't checked here (no network in the
    tests).
    """
    pin = re.compile(
        r"uses: elixir-cloud-aai/\.github/actions/[a-z-]+"
        r"@([0-9a-f]{40}) # (v\d+\.\d+\.\d+)$"
    )
    pins: set[tuple[str, str]] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "uses: elixir-cloud-aai/.github/" in line:
                match = pin.search(line)
                assert match, (path.name, line.strip())
                pins.add((match[1], match[2]))
    assert len(pins) == 1, pins
