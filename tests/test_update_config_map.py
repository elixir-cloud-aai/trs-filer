"""Tests of `update-config-map.sh`, the script of the chart's config Job.

The script fills the app's ConfigMap from the packaged config and restarts
the app (TEMPORARY, with the Job, until the chart uses the FOCA library
chart: #135). It runs with the real `jq` and `yq` (the Python `yq` of the
`Dockerfile`, a wrapper of `jq`) against a stub of `curl` that plays the
Kubernetes API server; its fixed paths (the service account's files and
`/tmp`) are moved to a temporary directory. Without `jq` or the Python
`yq` (a dev dependency), the tests that run it are skipped, except in CI
(`CI` set), where they fail.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "update-config-map.sh"
CONFIG = ROOT / "trs_filer" / "config.yaml"
JOB = ROOT / "deployment" / "templates" / "trs-filer-configmap-job.yaml"
SERVICE_ACCOUNT = "/var/run/secrets/kubernetes.io/serviceaccount"
# The script's path in the image, which the Job runs
SCRIPT_IN_IMAGE = "/app/update-config-map.sh"
# The script's directory for temporary files, moved by the tests
SCRIPT_TMP = "/tmp/"  # noqa: S108 (a path in the script, not used here)
NAMESPACE = "trs"
TOKEN = "token-of-the-job"  # noqa: S105 (fake token of the stub API server)
APISERVER = "kubernetes.default.svc"
CONFIG_MAP = "app-config-trs-filer"
CONFIG_MAP_URL = (
    f"https://{APISERVER}/api/v1/namespaces/{NAMESPACE}/configmaps/{CONFIG_MAP}"
)
PODS_URL = f"https://{APISERVER}/api/v1/namespaces/{NAMESPACE}/pods/"
APP_PODS_URL = (
    f"https://{APISERVER}/api/v1/namespaces/{NAMESPACE}/pods?labelSelector=app%3D"
    "trs-filer"
)
# Pods of the namespace and their label `app`: the app's, MongoDB's, and
# those of other workloads, one of them with a name that starts with the
# app's
PODS = {
    "trs-filer-5d9c-x1": "trs-filer",
    "trs-filer-5d9c-x2": "trs-filer",
    "mongodb-trs-filer-0": "mongodb-trs-filer",
    "trs-filer-tools-7f8d-y1": "trs-filer-tools",
    "other-1": "other",
}
# Stub of `curl`: records each request (method, URL, headers, body) as a
# JSON line in `$CURL_LOG`, and answers like the API server; it refuses
# (`403`) requests whose method and URL end with `$CURL_REFUSE` (e.g.,
# `PATCH /configmaps/app-config-trs-filer`), and then exits as `curl
# --fail` does
CURL_STUB = """\
import json
import os
import sys

args = sys.argv[1:]
request = {"method": "GET", "headers": [], "body": None, "url": None, "flags": []}
output = None
index = 0
while index < len(args):
    arg = args[index]
    if arg in ("-X", "-H", "-o", "-d", "-w", "--cacert"):
        value = args[index + 1]
        index += 2
        if arg == "-X":
            request["method"] = value
        elif arg == "-H":
            request["headers"].append(value)
        elif arg == "-o":
            output = value
        elif arg == "-d":
            with open(value.removeprefix("@"), encoding="utf-8") as body:
                request["body"] = json.load(body)
        continue
    if arg.startswith("-"):
        request["flags"].append(arg)
    else:
        request["url"] = arg
    index += 1
with open(os.environ["CURL_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(request) + "\\n")
refuse = os.environ.get("CURL_REFUSE", "").split(" ", 1)
answer = ""
if len(refuse) == 2 and request["method"] == refuse[0] and request["url"].endswith(
    refuse[1]
):
    if "--fail" in request["flags"]:
        sys.stderr.write("curl: (22) The requested URL returned error: 403\\n")
        sys.exit(22)
    answer = json.dumps({"kind": "Status", "code": 403})
elif request["method"] == "GET" and "/configmaps/" in request["url"]:
    answer = json.dumps(
        {"kind": "ConfigMap", "metadata": {"name": "app-config-trs-filer"},
         "data": {"config.yaml": "# Empty"}}
    )
elif request["method"] == "GET" and "/pods?labelSelector=app%3D" in request["url"]:
    app = request["url"].split("labelSelector=app%3D", 1)[1]
    pods = dict(pod.split("=") for pod in os.environ["PODS"].split())
    answer = json.dumps(
        {
            "items": [
                {"metadata": {"name": name, "labels": {"app": label}}}
                for name, label in pods.items()
                if label == app
            ]
        }
    )
if output is not None and output != "/dev/null":
    with open(output, "w", encoding="utf-8") as file:
        file.write(answer)
elif output is None:
    sys.stdout.write(answer)
"""


def _has_tools() -> bool:
    """Check whether `jq` and the Python `yq` are installed.

    Returns:
        Whether both are on the `PATH`; another `yq` (e.g., the Go `yq`,
        whose arguments differ) doesn't count.
    """
    yq = shutil.which("yq")
    if shutil.which("jq") is None or yq is None:
        return False
    version = subprocess.run(  # noqa: S603 (executable from the PATH, no shell)
        [yq, "--version"], capture_output=True, check=False, text=True
    ).stdout
    # e.g., "yq 3.4.3"; the Go `yq` prints "yq (https://...) version v4..."
    return re.match(r"yq \d", version) is not None


TOOLS = pytest.mark.skipif(
    not _has_tools() and not os.environ.get("CI"),
    reason="jq or the Python yq is not installed",
)


def _job_command() -> str:
    """Get the shell command of the config Job, which runs the script.

    Returns:
        The command (`/bin/sh -c`), from the Job's template.
    """
    command = re.search(
        r"^ *- \|\n(?P<command>(?: {10}.*\n)+)",
        JOB.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert command, "No shell command in the config Job"
    return textwrap.dedent(command["command"])


def _run(
    tmp_path: Path,
    env: dict[str, str],
    namespace: str = NAMESPACE,
    job: bool = False,
    bare_python: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    """Run the script against the stub API server.

    It runs in `tmp_path`, so that Python doesn't find the package in the
    working directory.

    Args:
        tmp_path: Temporary directory.
        env: Environment variables of the script, besides `PATH`.
        namespace: Content of the service account's namespace file.
        job: Whether to run the script through the Job's command, which sets
            `APP_CONFIG_PATH`.
        bare_python: Whether `python3` runs without `site-packages` (`-S`),
            where the dev environment has the package.

    Returns:
        The completed process, and the requests to the API server.
    """
    account = tmp_path / "serviceaccount"
    account.mkdir()
    (account / "namespace").write_text(namespace, encoding="utf-8")
    (account / "token").write_text(TOKEN, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    script = tmp_path / "update-config-map.sh"
    # `SCRIPT_TMP` first: the temporary directory may be under it
    script.write_text(
        SCRIPT.read_text(encoding="utf-8")
        .replace(SCRIPT_TMP, f"{work}/")
        .replace(SERVICE_ACCOUNT, str(account)),
        encoding="utf-8",
    )
    stubs = tmp_path / "bin"
    stubs.mkdir()
    curl = stubs / "curl"
    curl.write_text(f"#!{sys.executable}\n{CURL_STUB}", encoding="utf-8")
    curl.chmod(0o755)
    if bare_python:
        python = stubs / "python3"
        python.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" -S "$@"\n', encoding="utf-8"
        )
        python.chmod(0o755)
    log = tmp_path / "curl.jsonl"
    command = ["/bin/sh", str(script)]
    if job:
        command = [
            "/bin/sh",
            "-c",
            _job_command().replace(SCRIPT_IN_IMAGE, f"/bin/sh {script}"),
        ]
    result = subprocess.run(  # noqa: S603 (fixed executable, no shell)
        command,
        capture_output=True,
        check=False,
        cwd=tmp_path,
        text=True,
        env={
            "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
            "CURL_LOG": str(log),
            "PODS": " ".join(f"{name}={label}" for name, label in PODS.items()),
            **env,
        },
    )
    requests = (
        [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        if log.exists()
        else []
    )
    return result, requests


def _env(**changes: str | None) -> dict[str, str]:
    """Get the environment of the script as set by the Job, with changes.

    Args:
        **changes: Variables to set, or to remove (`None`).

    Returns:
        Environment variables.
    """
    env: dict[str, str | None] = {
        "APISERVER": APISERVER,
        "CONFIG_MAP_NAME": CONFIG_MAP,
        "APP_CONFIG_PATH": str(CONFIG),
        "APP_NAME": "trs-filer",
        "HOST_NAME": "trs.example.org",
        "MONGO_HOST": "mongodb-trs-filer",
        **changes,
    }
    return {key: value for key, value in env.items() if value is not None}


@TOOLS
def test_update_config_map(tmp_path: Path) -> None:
    """The ConfigMap gets the packaged config, and the app's pods restart.

    The config is served at the host name via HTTPS and uses the chart's
    MongoDB; the requests use the service account's token and namespace.

    Args:
        tmp_path: Temporary directory.
    """
    result, requests = _run(tmp_path, _env())
    assert result.returncode == 0, result.stdout + result.stderr
    assert [(r["method"], r["url"]) for r in requests] == [
        ("GET", CONFIG_MAP_URL),
        ("PATCH", CONFIG_MAP_URL),
        ("GET", APP_PODS_URL),
        ("DELETE", f"{PODS_URL}trs-filer-5d9c-x1"),
        ("DELETE", f"{PODS_URL}trs-filer-5d9c-x2"),
    ]
    for request in requests:
        assert f"Authorization: Bearer {TOKEN}" in request["headers"]
    patch = requests[1]
    assert "Content-Type: application/strategic-merge-patch+json" in patch["headers"]
    assert patch["body"]["metadata"] == {"name": CONFIG_MAP}
    expected = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    expected["custom"]["service"].update(
        url_prefix="https", external_host="trs.example.org", external_port=443
    )
    expected["db"]["host"] = "mongodb-trs-filer"
    assert yaml.safe_load(patch["body"]["data"]["config.yaml"]) == expected


@TOOLS
def test_update_config_map_default_mongo_host(tmp_path: Path) -> None:
    """Without `MONGO_HOST`, the config uses the MongoDB host `mongodb`.

    Args:
        tmp_path: Temporary directory.
    """
    result, requests = _run(tmp_path, _env(MONGO_HOST=None))
    assert result.returncode == 0, result.stdout + result.stderr
    config = yaml.safe_load(requests[1]["body"]["data"]["config.yaml"])
    assert config["db"]["host"] == "mongodb"


@TOOLS
def test_update_config_map_no_config(tmp_path: Path) -> None:
    """A missing config fails the script before any change (exit code 4).

    Args:
        tmp_path: Temporary directory.
    """
    result, requests = _run(tmp_path, _env(APP_CONFIG_PATH=str(tmp_path / "none")))
    assert result.returncode == 4
    assert requests == []


@pytest.mark.parametrize(
    "name", ["CONFIG_MAP_NAME", "APISERVER", "APP_CONFIG_PATH", "HOST_NAME", "APP_NAME"]
)
def test_update_config_map_required(tmp_path: Path, name: str) -> None:
    """Each required variable missing fails the script before any request.

    Args:
        tmp_path: Temporary directory.
        name: Name of the missing variable.
    """
    result, requests = _run(tmp_path, _env(**{name: None}))
    assert result.returncode == 1
    assert requests == []


@TOOLS
def test_job_command(tmp_path: Path) -> None:
    """The Job's command runs the script with the installed package's config.

    So the Job needs no path with the image's Python version in it (the
    base image's Python changes every year). The package is found via
    `PYTHONPATH`, as in the image via `site-packages`.

    Args:
        tmp_path: Temporary directory.
    """
    result, requests = _run(
        tmp_path, _env(APP_CONFIG_PATH=None, PYTHONPATH=str(ROOT)), job=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"APP CONFIG PATH: {CONFIG}" in result.stdout
    config = yaml.safe_load(requests[1]["body"]["data"]["config.yaml"])
    assert config["custom"]["service"]["external_host"] == "trs.example.org"


def test_job_command_no_package(tmp_path: Path) -> None:
    """Without the package, the Job's command fails before the script (exit 4).

    Args:
        tmp_path: Temporary directory.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    result, requests = _run(
        tmp_path,
        _env(APP_CONFIG_PATH=None, PYTHONPATH=str(empty), PYTHONNOUSERSITE="1"),
        job=True,
        bare_python=True,
    )
    assert result.returncode == 4, result.stdout + result.stderr
    assert "Cannot find the package trs_filer" in result.stderr
    assert "Inputs:" not in result.stdout
    assert requests == []


def test_update_config_map_no_namespace(tmp_path: Path) -> None:
    """Without the service account's namespace, the script fails (exit 6).

    It fails before any request.

    Args:
        tmp_path: Temporary directory.
    """
    result, requests = _run(tmp_path, _env(), namespace="")
    assert result.returncode == 6, result.stdout + result.stderr
    assert requests == []


@TOOLS
@pytest.mark.parametrize(
    ("refused", "code", "count"),
    [
        (f"GET /configmaps/{CONFIG_MAP}", 7, 1),
        (f"PATCH /configmaps/{CONFIG_MAP}", 8, 2),
        ("GET /pods?labelSelector=app%3Dtrs-filer", 9, 3),
    ],
)
def test_update_config_map_refused(
    tmp_path: Path, refused: str, code: int, count: int
) -> None:
    """A request that the API server refuses fails the script.

    E.g., if the Job's Role lacks a right; the script stops at the refused
    request, so it deletes no pods.

    Args:
        tmp_path: Temporary directory.
        refused: Method and end of the URL of the refused request.
        code: Expected exit code.
        count: Expected number of requests, including the refused one.
    """
    result, requests = _run(tmp_path, {**_env(), "CURL_REFUSE": refused})
    assert result.returncode == code, result.stdout + result.stderr
    assert len(requests) == count
    assert "All Done" not in result.stdout
