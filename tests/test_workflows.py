"""Tests for the names, publishing conditions and checks of the workflows."""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
# A chart file name as the release workflow packages it
CHART = "trs-filer-1.2.3.tgz"


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
        (scan,) = _steps(jobs["scan"], SCAN_ACTION)
        image = scan["with"]["image"]
        if name == "release.yml":
            assert image == "${{ env.IMAGE_NAME }}@${{ needs.push.outputs.digest }}"
        else:
            # The pushed digest where `push` runs (see "Determine image")
            assert image == "${{ steps.image.outputs.image }}"
            (determine,) = (s for s in jobs["scan"]["steps"] if s.get("id") == "image")
            assert determine["env"]["DIGEST"] == "${{ needs.push.outputs.digest }}"
            assert 'echo "image=${IMAGE_NAME}@${DIGEST}"' in determine["run"]
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


def test_release_chart_checked() -> None:
    """The release workflow checks the chart before attesting and signing it.

    `publish` downloads the chart artifact, which any job of the run could
    replace, so it checks that `dist/` holds exactly the file that `prepare`
    packaged (its name and SHA-256, as outputs of `prepare`) before anything,
    the image included, is attested or signed. Only that file is attested and
    signed; the Sigstore bundle (`<chart>.tgz.sigstore.json`) is written to
    `dist/`, so that it is uploaded with the chart. The wiring and order of
    the steps are checked here, the script itself by
    `test_release_chart_check_runs`.
    """
    release = _load(WORKFLOWS / "release.yml")["jobs"]
    prepare = release["prepare"]
    assert prepare["outputs"]["chart_file"] == "${{ steps.chart.outputs.file }}"
    assert prepare["outputs"]["chart_sha256"] == "${{ steps.chart.outputs.sha256 }}"
    packaging = {step["name"]: step for step in prepare["steps"]}
    assert packaging["Package chart"]["id"] == "chart"
    # Re-runs of all jobs replace the chart, so its checksum is the new one
    assert packaging["Upload chart"]["with"]["overwrite"] is True
    steps = {step["name"]: step for step in release["publish"]["steps"]}
    assert steps["Download chart"]["with"] == {"name": "chart", "path": "dist/"}
    check = steps["Check chart"]
    # A failed check stops the job
    assert "continue-on-error" not in check
    assert "if" not in check
    assert check["env"]["FILE"] == "${{ needs.prepare.outputs.chart_file }}"
    assert check["env"]["SHA256"] == "${{ needs.prepare.outputs.chart_sha256 }}"
    chart = "dist/${{ needs.prepare.outputs.chart_file }}"
    assert steps["Attest chart provenance"]["with"]["subject-path"] == chart
    assert steps["Sign chart"]["env"]["CHART"] == chart
    sign = steps["Sign chart"]["run"]
    assert sign == 'cosign sign-blob --yes --bundle "${CHART}.sigstore.json" "${CHART}"'
    names = list(steps)
    assert names.index("Download chart") < names.index("Check chart")
    # A rejected chart leaves the image (pushed untagged by `push`) without
    # GitHub attestation, signature and tags too
    assert names.index("Check chart") < names.index("Attest build provenance")
    assert names.index("Check chart") < names.index("Sign image")
    assert names.index("Check chart") < names.index("Attest chart provenance")
    assert names.index("Check chart") < names.index("Sign chart")
    assert names.index("Attest chart provenance") < names.index("Create release")
    assert names.index("Sign chart") < names.index("Create release")
    assert 'gh release upload "${TAG}" dist/*' in steps["Create release"]["run"]


@pytest.mark.parametrize(
    ("extra", "rename", "tamper", "empty", "file", "sha256", "passes"),
    [
        pytest.param(None, None, False, False, CHART, None, True, id="good"),
        pytest.param(None, None, True, False, CHART, None, False, id="wrong-hash"),
        # Sorts before the chart
        pytest.param("other.tgz", None, False, False, CHART, None, False, id="extra"),
        # Sorts after the chart, so only the count rejects it
        pytest.param("zzz", None, False, False, CHART, None, False, id="extra-after"),
        pytest.param(".hidden", None, False, False, CHART, None, False, id="hidden"),
        pytest.param(
            None, "trs-filer-9.9.9.tgz", False, False, CHART, None, False, id="renamed"
        ),
        pytest.param(None, None, False, True, CHART, None, False, id="empty"),
        pytest.param(None, None, False, False, "../x.tgz", None, False, id="bad-name"),
        pytest.param(
            None,
            "trs-filer-1.tar",
            False,
            False,
            "trs-filer-1.tar",
            None,
            False,
            id="not-tgz",
        ),
        pytest.param(None, None, False, False, CHART, "abc", False, id="bad-hash"),
        pytest.param(None, None, False, False, CHART, "", False, id="no-hash"),
        pytest.param(None, None, False, False, CHART, "A" * 64, False, id="upper-hash"),
    ],
)
def test_release_chart_check_runs(
    tmp_path: Path,
    extra: str | None,
    rename: str | None,
    tamper: bool,
    empty: bool,
    file: str,
    sha256: str | None,
    passes: bool,
) -> None:
    """The chart check of `publish` passes only for the chart of `prepare`.

    The step's script runs with the options of GitHub's default shell for
    steps without `shell:` (`bash -e`, no `pipefail`) in a directory whose
    `dist/` holds the downloaded artifact. It needs `bash`
    and GNU `sha256sum`, as on the GitHub runners.

    Args:
        tmp_path: The working directory of the step.
        extra: A file added to the artifact, if any.
        rename: The name the chart is renamed to in the artifact, if any.
        tamper: Whether the chart's content is changed after packaging.
        empty: Whether the artifact holds no file at all.
        file: The chart file name output by `prepare`.
        sha256: The checksum output by `prepare` (that of the chart if None).
        passes: Whether the check passes.
    """
    bash = shutil.which("bash")
    assert bash
    steps = _load(WORKFLOWS / "release.yml")["jobs"]["publish"]["steps"]
    script = {step["name"]: step for step in steps}["Check chart"]["run"]
    dist = tmp_path / "dist"
    dist.mkdir()
    chart = dist / CHART
    chart.write_bytes(b"chart")
    digest = hashlib.sha256(chart.read_bytes()).hexdigest()
    if tamper:
        chart.write_bytes(b"other chart")
    if rename:
        chart.rename(dist / rename)
    if extra:
        (dist / extra).write_bytes(b"extra")
    if empty:
        chart.unlink()
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [bash, "--noprofile", "--norc", "-e", "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "FILE": file,
            "SHA256": digest if sha256 is None else sha256,
        },
        check=False,
    )
    assert (result.returncode == 0) == passes, result.stdout + result.stderr


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
