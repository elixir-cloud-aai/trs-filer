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
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "update-config-map.sh"
CONFIG = ROOT / "trs_filer" / "config.yaml"
JOB = ROOT / "deployment" / "templates" / "trs-filer-configmap-job.yaml"
SERVICE_ACCOUNT = "/var/run/secrets/kubernetes.io/serviceaccount"
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
PODS = ["trs-filer-5d9c-x1", "trs-filer-5d9c-x2", "mongodb-trs-filer-0", "other-1"]
# Stub of `curl`: records each request (method, URL, headers, body) as a
# JSON line in `$CURL_LOG`, and answers like the API server
CURL_STUB = """\
import json
import os
import sys

args = sys.argv[1:]
request = {"method": "GET", "headers": [], "body": None, "url": None}
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
    if not arg.startswith("-"):
        request["url"] = arg
    index += 1
with open(os.environ["CURL_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(request) + "\\n")
answer = ""
if request["method"] == "GET" and "/configmaps/" in request["url"]:
    answer = json.dumps(
        {"kind": "ConfigMap", "metadata": {"name": "app-config-trs-filer"},
         "data": {"config.yaml": "# Empty"}}
    )
elif request["method"] == "GET" and request["url"].endswith("/pods/"):
    answer = json.dumps(
        {"items": [{"metadata": {"name": name}} for name in os.environ["PODS"].split()]}
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


def _run(
    tmp_path: Path, env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    """Run the script against the stub API server.

    Args:
        tmp_path: Temporary directory.
        env: Environment variables of the script, besides `PATH`.

    Returns:
        The completed process, and the requests to the API server.
    """
    account = tmp_path / "serviceaccount"
    account.mkdir()
    (account / "namespace").write_text(NAMESPACE, encoding="utf-8")
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
    log = tmp_path / "curl.jsonl"
    result = subprocess.run(  # noqa: S603 (fixed executable, no shell)
        ["/bin/sh", str(script)],
        capture_output=True,
        check=False,
        text=True,
        env={
            "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
            "CURL_LOG": str(log),
            "PODS": " ".join(PODS),
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
        ("GET", PODS_URL),
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

    As when `APP_CONFIG_PATH` doesn't match the image's Python version.

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


def test_config_path_python_version() -> None:
    """The Job's config path is in the site-packages of the image's Python.

    The base image's Python changes every year (see "Python versions" in
    `docs/development.md`); a stale path fails the Job (exit code 4).
    """
    image = re.search(
        r"^FROM elixircloud/foca:[^-@\s]+-py(?P<version>3\.\d+)@",
        (ROOT / "Dockerfile").read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert image, "No Python version in the base image tag of the Dockerfile"
    path = re.search(
        r"name: APP_CONFIG_PATH\s+value: (?P<path>\S+)",
        JOB.read_text(encoding="utf-8"),
    )
    assert path, "No APP_CONFIG_PATH in the config Job"
    assert path["path"] == (
        f"/usr/local/lib/python{image['version']}/site-packages/trs_filer/config.yaml"
    )
