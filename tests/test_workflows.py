"""Tests for the names, publishing conditions, checks and installs of the workflows."""

import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tomllib
from typing import Any

from packaging.requirements import Requirement
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


def test_release_tag_checked_first() -> None:
    """The release tag is checked before any script of the tagged commit runs.

    The step that checks the tag (annotated, signature verified by GitHub,
    commit on `main`) holds a token and runs no code of the tagged commit;
    the scripts run in later steps, the version's without the token.
    """
    prepare = _load(WORKFLOWS / "release.yml")["jobs"]["prepare"]
    steps = {step["name"]: step for step in prepare["steps"]}
    # From the list, so that a second step of the same name is seen
    names = [step["name"] for step in prepare["steps"]]
    assert len(names) == len(steps)
    # Only the checkout and Python come first; Python with a fixed version
    # only (no `python-version-file` or cache, which read files of the commit)
    assert names[:3] == [
        "Check out repository",
        "Set up Python",
        "Check release tag and commit",
    ]
    assert set(steps["Set up Python"]["with"]) == {"python-version"}
    check = steps["Check release tag and commit"]
    assert check["id"] == "commit"
    assert "GH_TOKEN" in check["env"]
    assert ".verification.verified" in check["run"]
    # Neither scripts nor Python nor other files of the commit
    for code in ("scripts/", "python", "./"):
        assert code not in check["run"]
    assert prepare["outputs"]["sha"] == "${{ steps.commit.outputs.sha }}"
    derive = steps["Derive release version"]
    assert derive["id"] == "version"
    assert "scripts/release_version.py outputs" in derive["run"]
    assert "GH_TOKEN" not in derive["env"]
    assert "GH_TOKEN" not in prepare.get("env", {})


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


def _credential_jobs() -> list[tuple[str, str, dict[str, Any]]]:
    """List the jobs that hold publishing credentials.

    These are the jobs of all workflows that run in an environment
    (`environment:`, which holds the Docker Hub secrets), use a Docker Hub
    secret directly, or may sign or write (`id-token`, `contents`,
    `packages` or `attestations` permission `write`, or `write-all`, also
    inherited from the workflow's permissions). No workflow passes a
    secret to all its jobs (workflow-level `env:`).

    Returns:
        The workflow file name, job ID and job of each such job.
    """
    jobs = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = _load(path)
        assert "secrets." not in yaml.safe_dump(workflow.get("env", {})), path
        for job_id, job in workflow["jobs"].items():
            # Jobs without permissions of their own inherit the workflow's
            permissions = job.get("permissions", workflow.get("permissions", {}))
            writes = permissions == "write-all" or (
                isinstance(permissions, dict)
                and any(
                    permissions.get(scope) == "write"
                    for scope in ("id-token", "contents", "packages", "attestations")
                )
            )
            if (
                "environment" in job
                or "secrets.DOCKERHUB" in yaml.safe_dump(job)
                or writes
            ):
                jobs.append((path.name, job_id, job))
    return jobs


def _commands(step: dict[str, Any]) -> list[str]:
    """Split the script of a step into commands.

    Args:
        step: A step of a job.

    Returns:
        The commands of the step's `run` script: its lines, with
        continuation lines joined, split at `;`, `&&`, `||` and `|`, with
        whitespace normalised.
    """
    lines = step.get("run", "").replace("\\\n", " ").splitlines()
    return [
        " ".join(command.split())
        for line in lines
        for command in re.split(r"&&|\|\||;|\|", line)
        if command.strip()
    ]


# pip (also `pip3`, `pip3.13`, `"<venv>/bin/pip"`, with global options and
# their values) commands that install or build packages; the latter runs
# their build backends
PIP = re.compile(r"\bpip[0-9.]*[\"']?(\s+\S+)*?\s+(install|wheel|download)\b")
# Other installers (uv also with global options before the subcommand),
# and builds that install build requirements
INSTALLERS = re.compile(
    r"\b(pipx|pipenv|easy_install|uvx|pip-sync|poetry|pdm|hatch|conda|mamba"
    r"|micromamba|uv(\s+\S+)*?\s+(pip|tool|sync|run|add|build|venv)"
    r"|python[0-9.]*\s+-m\s+build)\b"
)
# `uv sync`, also with options before the subcommand
UV_SYNC = re.compile(r"\buv\s+(\S+\s+)*?sync\b")
# The jobs of `ci.yml` that install the app's dependencies, with their extra
LOCKED_JOBS = {"lint": "dev", "test": "dev", "chart": "dev", "docs": "docs"}


def test_credential_jobs_found() -> None:
    """The jobs that publish images are found as credential jobs."""
    found = {(name, job_id) for name, job_id, _ in _credential_jobs()}
    assert {
        ("ci.yml", "push"),
        ("ci.yml", "publish"),
        ("release.yml", "push"),
        ("release.yml", "publish"),
    } <= found


@pytest.mark.parametrize(
    ("command", "found"),
    [
        pytest.param("pip install foo", True, id="pip"),
        pytest.param("pip3.13 install foo", True, id="versioned"),
        pytest.param('"${VENV}/bin/pip" install foo', True, id="venv"),
        pytest.param("python -m pip wheel .", True, id="wheel"),
        pytest.param("pip download foo", True, id="download"),
        pytest.param("pip -q install foo", True, id="global-option"),
        pytest.param("pip --log pip.log install foo", True, id="option-value"),
        pytest.param("pip list", False, id="list"),
        pytest.param("echo pipeline install", False, id="other-word"),
    ],
)
def test_pip_pattern(command: str, found: bool) -> None:
    """The pattern finds pip commands that install or build packages.

    Args:
        command: A command.
        found: Whether the pattern finds it.
    """
    assert bool(PIP.search(command)) == found


@pytest.mark.parametrize(
    "command",
    [
        "pipx run foo",
        "pipenv install",
        "uv sync",
        "uv build",
        "python -m build",
        "poetry install",
        "conda install foo",
        "micromamba install foo",
        "uv --offline run pytest",
        "uv --directory x pip install foo",
    ],
)
def test_installers_pattern(command: str) -> None:
    """The pattern finds other installers and builds.

    Args:
        command: A command.
    """
    assert INSTALLERS.search(command)


def test_commands_split() -> None:
    """Commands chained on one line are checked one by one."""
    step = {"run": "pip install -r r.txt && pip install foo; echo a | tee b\n"}
    assert _commands(step) == [
        "pip install -r r.txt",
        "pip install foo",
        "echo a",
        "tee b",
    ]


@pytest.mark.parametrize(("job_id", "extra"), LOCKED_JOBS.items())
def test_jobs_on_lock(job_id: str, extra: str) -> None:
    """The jobs that install the app's dependencies install the locked ones.

    They run on the versions of `uv.lock`, so that pull requests that change
    only the lock (e.g., Dependabot's) are tested on it, with uv of a pinned
    `astral-sh/setup-uv`; no pip command installs anything.

    Args:
        job_id: The ID of the job.
        extra: The extra that the job installs.
    """
    job = _load(WORKFLOWS / "ci.yml")["jobs"][job_id]
    steps = {step.get("name"): step for step in job["steps"]}
    uv = steps["Set up uv"]
    assert re.fullmatch(r"astral-sh/setup-uv@[0-9a-f]{40}", uv["uses"])
    commands = _commands(steps["Install dependencies"])
    (sync,) = [shlex.split(command) for command in commands if UV_SYNC.search(command)]
    assert "--locked" in sync, (job_id, sync)
    assert "--frozen" not in sync, (job_id, sync)
    extras = {
        value
        for option, value in zip(sync, [*sync[1:], ""], strict=True)
        if option == "--extra"
    } | {
        token.removeprefix("--extra=") for token in sync if token.startswith("--extra=")
    }
    assert extras == {extra}, (job_id, sync)
    assert "--all-extras" not in sync, (job_id, sync)
    # Later steps run the tools of `.venv`
    assert 'echo "${PWD}/.venv/bin" >> "$GITHUB_PATH"' in commands, job_id
    names = list(steps)
    assert names.index("Set up Python") < names.index("Set up uv")
    assert names.index("Set up uv") < names.index("Install dependencies")


def test_lock_checked() -> None:
    """The lint job checks that the lock matches `pyproject.toml`."""
    steps = _load(WORKFLOWS / "ci.yml")["jobs"]["lint"]["steps"]
    names = [step.get("name") for step in steps]
    check = {step.get("name"): step for step in steps}["Check lock file"]
    assert _commands(check) == ["uv lock --check"]
    assert names.index("Check lock file") < names.index("Install dependencies")


def _allowed_install(command: str) -> bool:
    """Check whether a command of a job without credentials may install.

    Allowed are `uv sync --locked`, `pipx run` of a pinned tool (`--spec
    <name>==<version>`, e.g., cffconvert in `lint`, in its own environment)
    and `python -m build` (the build of the distributions in `lint`, with
    build requirements from the index, as the editable install of the app).

    Args:
        command: A command.

    Returns:
        Whether the command is allowed.
    """
    tokens = shlex.split(command)
    if UV_SYNC.search(command):
        # Locked, from the lock's sources and indexes only
        overrides = {"--frozen", "--no-sources", "--index", "--default-index"}
        overrides |= {"--index-url", "--extra-index-url", "--find-links"}
        return tokens[:3] == ["uv", "sync", "--locked"] and not any(
            token.split("=")[0] in overrides for token in tokens
        )
    if command.startswith("pipx run --spec "):
        return "==" in tokens[3]
    return command == "python -m build"


@pytest.mark.parametrize(
    ("command", "allowed"),
    [
        pytest.param("uv sync --locked --extra dev", True, id="sync-locked"),
        pytest.param("uv sync --extra dev", False, id="sync"),
        pytest.param("uv sync --locked --frozen", False, id="sync-frozen"),
        pytest.param("uv sync --locked --index-url=x", False, id="sync-index"),
        pytest.param("uv sync --locked --no-sources", False, id="sync-sources"),
        pytest.param("env X=1 uv sync --locked", False, id="sync-env"),
        pytest.param("uv --quiet sync --locked", False, id="sync-option"),
        pytest.param("pipx run --spec foo==1.0 foo", True, id="pipx-pinned"),
        pytest.param("pipx run --spec foo>=1 foo", False, id="pipx-range"),
        pytest.param("pipx run foo", False, id="pipx"),
        pytest.param("uvx ruff", False, id="uvx"),
        pytest.param("python -m build", True, id="build"),
    ],
)
def test_allowed_install(command: str, allowed: bool) -> None:
    """Only locked syncs, pinned `pipx run` and the build may install.

    Args:
        command: A command.
        allowed: Whether it is allowed.
    """
    assert _allowed_install(command) == allowed


def test_no_unlocked_installs() -> None:
    """No job without credentials installs Python packages but from the lock.

    No pip command installs anything there, and other installers are used
    only as `_allowed_install` allows. Jobs with publishing credentials are
    checked on their own.
    """
    credential = {(name, job_id) for name, job_id, _ in _credential_jobs()}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job_id, job in _load(path)["jobs"].items():
            if (path.name, job_id) in credential:
                continue
            for step in job.get("steps", []):
                for command in _commands(step):
                    where = (path.name, job_id, step.get("name"), command)
                    assert not PIP.search(command), where
                    if INSTALLERS.search(command) or UV_SYNC.search(command):
                        assert _allowed_install(command), where


def test_uv_version_locked() -> None:
    """Every `astral-sh/setup-uv` step installs the uv locked in `uv.lock`.

    The action reads the version from the lock (`version-file`), where uv is
    a dev dependency; it fails if the lock has none. Dependabot bumps it
    with the other locked packages.
    """
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert [package for package in lock["package"] if package["name"] == "uv"]
    setups = [
        (path.name, job_id, step)
        for path in sorted(WORKFLOWS.glob("*.yml"))
        for job_id, job in _load(path)["jobs"].items()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("astral-sh/setup-uv@")
    ]
    assert setups
    for name, job_id, step in setups:
        assert step["with"] == {"version-file": "uv.lock"}, (name, job_id)


# The only options of an install in a job with credentials, besides `-r`
HASH_CHECKED = ["--require-hashes", "--only-binary", ":all:", "--no-deps"]


def test_credential_jobs_install_hash_checked() -> None:
    """Jobs with publishing credentials install Python packages hash-checked.

    A compromised release of a package installed unpinned would run code in
    a job that holds registry credentials. So every pip command there that
    installs or builds packages is a `pip install` of exported locked
    requirements (`-r`) with hash checks, as wheels only and without
    resolving anything else, and no other installer is used. Actions
    (`uses:`) are pinned by commit and not checked here.
    """
    for name, job_id, job in _credential_jobs():
        assert "uses" not in job, (name, job_id)  # steps are checked here
        for step in job["steps"]:
            for command in _commands(step):
                where = (name, job_id, step.get("name"), command)
                assert not INSTALLERS.search(command), where
                assert not UV_SYNC.search(command), where
                if match := PIP.search(command):
                    assert match.group(2) == "install", where
                    # Exactly these options and one requirements file (no
                    # other files, packages or options)
                    options = shlex.split(command[match.end() :])
                    assert options.count("-r") == 1, where
                    file = options.index("-r")
                    # The file the step exported the lock to
                    assert options[file + 1] == "${requirements}", where
                    rest = options[:file] + options[file + 2 :]
                    assert rest == HASH_CHECKED, where


def _derive_version() -> dict[str, Any]:
    """Get the step of the `push` job of `ci.yml` that derives the version.

    Returns:
        The step.
    """
    jobs = _load(WORKFLOWS / "ci.yml")["jobs"]
    names = [step["name"] for step in jobs["push"]["steps"]]
    # Unique, so that the order checked is that of the step returned
    assert len(names) == len(set(names))
    steps = dict(zip(names, jobs["push"]["steps"], strict=True))
    # Before the job logs in to Docker Hub
    assert names.index("Derive version") < names.index("Log in to Docker Hub")
    return steps["Derive version"]


def test_dev_version_from_locked_build_requirements() -> None:
    """The `push` job of `ci.yml` derives the version with the locked tools.

    setuptools-scm and its dependencies are the `build-system` group of
    `uv.lock`, exported by the uv image of the `Dockerfile` (pinned by
    digest) and run from the virtual environment they are installed into
    (with hash checks, see `test_credential_jobs_install_hash_checked`).
    """
    commands = _commands(_derive_version())
    script = " ".join(commands)
    assert '"${uv_image}" export --frozen --only-group build-system' in script
    assert "--no-emit-project" in script
    assert "--network none" in script
    # pip installs exactly the exported requirements
    assert '--project /src > "${requirements}"' in script
    assert '--no-deps -r "${requirements}"' in script
    assert re.search(r"build-env/bin/python\"? -m setuptools_scm", script)

    def position(pattern: str) -> int:
        """Find the first command that matches a pattern.

        Args:
            pattern: Regular expression.

        Returns:
            Index of the command.
        """
        (index, *_) = [i for i, c in enumerate(commands) if re.search(pattern, c)]
        return index

    # Export, then install, then derive, and pass the version on
    export = position(r"\bexport --frozen\b")
    install = position(r"\bpip\"? install\b")
    derive = position(r"-m setuptools_scm")
    assert export < install < derive
    assert 'echo "version=${version}" >> "$GITHUB_OUTPUT"' in commands[derive + 1 :]
    assert commands[derive].startswith('version="$(')


def test_dev_version_uv_image() -> None:
    """The step finds the uv image of the `Dockerfile`, with its digest.

    The step's `sed` command runs against the `Dockerfile`, as in the step
    (GNU `sed`, as on the GitHub runners).
    """
    sed = shutil.which("sed")
    assert sed
    (command,) = [
        command
        for command in _commands(_derive_version())
        if command.startswith('uv_image="$(sed ')
    ]
    args = shlex.split(command.removeprefix('uv_image="$(').removesuffix(')"'))
    assert args[0] == "sed"
    assert args[-1] == "Dockerfile"
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [sed, *args[1:]],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"^FROM (ghcr\.io/astral-sh/uv:\S+) AS uv$", dockerfile, re.M)
    assert match
    assert re.fullmatch(r"ghcr\.io/astral-sh/uv:[^@]+@sha256:[0-9a-f]{64}", match[1])
    assert result.stdout == match[1] + "\n"


def test_build_system_group() -> None:
    """The `build-system` group is `build-system.requires`, and locked.

    The layout of the lock (`dev-dependencies`) is uv's; only the names are
    compared, as `uv lock --check` (lint job) covers the specifiers.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    group = pyproject["dependency-groups"]["build-system"]
    assert group == pyproject["build-system"]["requires"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    (project,) = [
        package for package in lock["package"] if package["name"] == "trs-filer"
    ]
    locked = [entry["name"] for entry in project["dev-dependencies"]["build-system"]]
    assert sorted(locked) == sorted(Requirement(spec).name for spec in group)


def test_chart_job() -> None:
    """CI lints and tests the chart with the Helm version of the release.

    The gate and `publish` need the job, so that a broken chart fails CI and
    holds back the `dev` image.
    """
    ci = _load(WORKFLOWS / "ci.yml")["jobs"]
    release = _load(WORKFLOWS / "release.yml")["jobs"]
    (ci_helm,) = _steps(ci["chart"], "azure/setup-helm")
    (release_helm,) = _steps(release["prepare"], "azure/setup-helm")
    assert ci_helm == release_helm
    assert ci["chart"]["name"] == "Chart"
    assert "chart" in ci["passed"]["needs"]
    assert "chart" in ci["publish"]["needs"]
    steps = {step.get("name"): step for step in ci["chart"]["steps"]}
    lint = _commands(steps["Lint chart"])
    assert any(
        command.startswith(
            "helm lint deployment --strict -f deployment/ci/test-values.yaml"
        )
        for command in lint
    )
    # Also without authentication and a host name (the defaults otherwise
    # needed for rendering)
    assert any(
        command.startswith("helm lint deployment --strict ")
        and "--set mongodb.auth.enabled=false" in command
        and "--set host_name=" in command
        for command in lint
    )
    # The release lints with the same values
    release_commands = [
        command for step in release["prepare"]["steps"] for command in _commands(step)
    ]
    assert any(
        command.startswith("helm lint ")
        and command.endswith("-f deployment/ci/test-values.yaml")
        for command in release_commands
    )
    tests = _commands(steps["Test chart"])
    assert any("tests/test_update_config_map.py" in command for command in tests)
    assert any("tests/test_chart.py" in command for command in tests)


def test_chart_install_job() -> None:
    """CI installs the chart on kind with the image of the commit.

    The job builds the image and loads it into the cluster (it pushes
    nothing), so it holds no credentials and runs for pull requests from
    forks too. It uses the Helm version of the release, and the gate and
    `publish` need it, so that a chart that doesn't install fails CI and
    holds back the `dev` image.
    """
    workflow = _load(WORKFLOWS / "ci.yml")
    ci = workflow["jobs"]
    release = _load(WORKFLOWS / "release.yml")["jobs"]
    job = ci["chart-install"]
    assert job["name"] == "Chart install"
    assert "chart-install" in ci["passed"]["needs"]
    assert "chart-install" in ci["publish"]["needs"]
    # Only the workflow's `contents: read`, no environment and no secrets
    assert "permissions" not in job
    assert workflow["permissions"] == {"contents": "read"}
    assert "environment" not in job
    assert "secrets." not in yaml.safe_dump(job)
    (helm,) = _steps(job, "azure/setup-helm")
    (release_helm,) = _steps(release["prepare"], "azure/setup-helm")
    assert helm == release_helm
    assert _steps(job, "helm/kind-action")
    commands = [command for step in job["steps"] for command in _commands(step)]
    assert any(command.startswith("kind load docker-image ") for command in commands)
    assert not any(command.startswith("docker push") for command in commands)
    assert any(
        command.startswith("helm install ")
        and "--wait" in command
        and "trs_filer.imagePullPolicy=Never" in command
        for command in commands
    )
