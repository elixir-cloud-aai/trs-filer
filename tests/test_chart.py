"""Tests of how the Helm chart (`deployment/`) exposes the app.

They render the chart with `helm template`. Without Helm, they are skipped,
except in CI (`CI` set), where they fail: GitHub's Ubuntu runners have Helm.
"""

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deployment"
HELM = shutil.which("helm")
ROUTE_API = "route.openshift.io/v1"
ALLOWLIST = "haproxy.router.openshift.io/ip_allowlist"

pytestmark = pytest.mark.skipif(
    HELM is None and not os.environ.get("CI"), reason="Helm is not installed"
)


def helm_template(chart: Path, *args: str) -> str:
    """Render a chart with `helm template`.

    Args:
        chart: Directory of the chart.
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        The rendered manifests.
    """
    assert HELM is not None, "Helm is not installed"
    result = subprocess.run(  # noqa: S603 (fixed executable, no shell)
        [
            HELM,
            "template",
            "trs-filer",
            str(chart),
            "--namespace",
            "trs",
            "--set",
            "host_name=trs.example.org",
            *args,
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


def render(*args: str) -> list[dict[str, Any]]:
    """Render the chart's resources.

    Args:
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        The rendered resources.
    """
    return [doc for doc in yaml.safe_load_all(helm_template(CHART, *args)) if doc]


def render_notes(tmp_path: Path, *args: str) -> str:
    """Render the chart's `NOTES.txt`, which `helm template` leaves out.

    The chart is copied, and a template of the copy renders `NOTES.txt` into
    a document.

    Args:
        tmp_path: Directory for the copy of the chart.
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        The rendered notes.
    """
    chart = tmp_path / "chart"
    shutil.copytree(CHART, chart)
    (chart / "templates" / "NOTES.txt").rename(chart / "NOTES.raw")
    (chart / "templates" / "notes.yaml").write_text(
        'notes: {{ tpl (.Files.Get "NOTES.raw") . | toJson }}\n', encoding="utf-8"
    )
    manifests = helm_template(chart, "--show-only", "templates/notes.yaml", *args)
    notes: str = yaml.safe_load(manifests)["notes"]
    return notes


def of_kind(resources: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """Select the resources of a kind.

    Args:
        resources: Rendered resources.
        kind: Kind to select, e.g., `Route`.

    Returns:
        The resources of that kind.
    """
    return [resource for resource in resources if resource["kind"] == kind]


def test_ingress_by_default() -> None:
    """By default, the chart creates the Ingress and no Route."""
    resources = render("--api-versions", ROUTE_API)
    assert len(of_kind(resources, "Ingress")) == 1
    assert of_kind(resources, "Route") == []


def test_route_without_ingress() -> None:
    """Without the Ingress, the chart creates the Route, without annotations."""
    resources = render(
        "--api-versions", ROUTE_API, "--set", "trs_filer.ingress.enabled=false"
    )
    assert of_kind(resources, "Ingress") == []
    (route,) = of_kind(resources, "Route")
    assert "annotations" not in route["metadata"]


def test_route_needs_route_api() -> None:
    """The chart creates no Route if the cluster serves no Routes."""
    resources = render("--set", "trs_filer.ingress.enabled=false")
    assert of_kind(resources, "Route") == []


def test_route_annotations(tmp_path: Path) -> None:
    """The Route gets `trs_filer.route.annotations`, as strings.

    `null` leaves an annotation out.

    Args:
        tmp_path: Directory for the values file.
    """
    values = tmp_path / "values.yaml"
    values.write_text(
        yaml.safe_dump(
            {
                "trs_filer": {
                    "ingress": {"enabled": False},
                    "route": {
                        "annotations": {
                            ALLOWLIST: "192.0.2.0/24",
                            "example.org/number": 100,
                            "example.org/removed": None,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    resources = render("--api-versions", ROUTE_API, "--values", str(values))
    (route,) = of_kind(resources, "Route")
    assert route["metadata"]["annotations"] == {
        ALLOWLIST: "192.0.2.0/24",
        "example.org/number": "100",
    }


def test_route_disabled() -> None:
    """With `trs_filer.route.enabled: false`, the chart creates no Route."""
    resources = render(
        "--api-versions",
        ROUTE_API,
        "--set",
        "trs_filer.ingress.enabled=false",
        "--set",
        "trs_filer.route.enabled=false",
    )
    assert of_kind(resources, "Route") == []
    assert of_kind(resources, "Ingress") == []


def test_route_without_route_values() -> None:
    """Values without `trs_filer.route` (e.g., of older charts) keep the Route.

    So do upgrades with `--reuse-values` from charts without the value.
    `null` removes the key from the chart's defaults.
    """
    resources = render(
        "--api-versions",
        ROUTE_API,
        "--set",
        "trs_filer.ingress.enabled=false",
        "--set",
        "trs_filer.route=null",
    )
    assert len(of_kind(resources, "Route")) == 1


def test_notes_ingress(tmp_path: Path) -> None:
    """With the Ingress, the notes give its URLs and the no-auth warning.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(tmp_path)
    # The warning links the issue of authentication (#7)
    assert "has no authentication yet" in notes
    assert "trs-filer/issues/7" in notes
    assert "http://trs.example.org/ga4gh/trs/v2/" in notes
    assert "port-forward" not in notes


def test_notes_route(tmp_path: Path) -> None:
    """With the Route, the notes give its `https` URLs.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(
        tmp_path,
        "--api-versions",
        ROUTE_API,
        "--set",
        "trs_filer.ingress.enabled=false",
    )
    assert "https://trs.example.org/ga4gh/trs/v2/" in notes
    assert "port-forward" not in notes


def test_notes_nothing_exposed(tmp_path: Path) -> None:
    """If nothing exposes the app, the notes say so and give no URLs.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(
        tmp_path,
        "--api-versions",
        ROUTE_API,
        "--set",
        "trs_filer.ingress.enabled=false",
        "--set",
        "trs_filer.route.enabled=false",
    )
    assert "The chart exposes the app neither via an Ingress" in notes
    assert "kubectl port-forward svc/trs-filer 8080:8080 -n trs" in notes
    assert "trs.example.org" not in notes


OPENSHIFT_SECURITY_API = "security.openshift.io/v1"
RESTRICTED_CONTAINER = {
    "allowPrivilegeEscalation": False,
    "capabilities": {"drop": ["ALL"]},
    "readOnlyRootFilesystem": True,
}


def _pod(resources: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    """Get the pod spec of a workload.

    Args:
        resources: Rendered resources.
        kind: Kind of the workload, `Deployment` or `Job`.
        name: Name of the workload, or its start (for the Job, which is
            named by revision).

    Returns:
        The pod spec.
    """
    (workload,) = (
        resource
        for resource in of_kind(resources, kind)
        if resource["metadata"]["name"].startswith(name)
    )
    pod: dict[str, Any] = workload["spec"]["template"]["spec"]
    return pod


def _tmp_volume(pod: dict[str, Any]) -> dict[str, Any]:
    """Get the volume mounted at `/tmp` of the pod's only container.

    Args:
        pod: Pod spec.

    Returns:
        The volume.
    """
    (container,) = pod["containers"]
    (mount,) = (m for m in container["volumeMounts"] if m["mountPath"] == "/tmp")  # noqa: S108 (a mount path)
    (volume,) = (v for v in pod["volumes"] if v["name"] == mount["name"])
    return volume


@pytest.mark.parametrize(
    ("kind", "name"), [("Deployment", "trs-filer"), ("Job", "configmap-job-")]
)
def test_app_security_context(kind: str, name: str) -> None:
    """The app and the config Job run as non-root, without privileges.

    They meet the Pod Security Standard "restricted", with a read-only root
    file system and a writable `emptyDir` at `/tmp`; the image's user (1000)
    is kept, so OpenShift can assign its own.

    Args:
        kind: Kind of the workload.
        name: Name of the workload, or its start.
    """
    pod = _pod(render(), kind, name)
    assert pod["securityContext"] == {
        "runAsNonRoot": True,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    (container,) = pod["containers"]
    assert container["securityContext"] == RESTRICTED_CONTAINER
    assert _tmp_volume(pod) == {"name": "tmp", "emptyDir": {"sizeLimit": "64Mi"}}


def test_mongodb_security_context() -> None:
    """MongoDB runs as its image's user `mongodb` (999), without privileges.

    The data volume belongs to its group (`fsGroup`); the root file system
    is read-only, with `emptyDir`s at `/tmp` and `/data/configdb`.
    """
    pod = _pod(render(), "Deployment", "mongodb-trs-filer")
    assert pod["securityContext"] == {
        "runAsNonRoot": True,
        "runAsUser": 999,
        "runAsGroup": 999,
        "fsGroup": 999,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    (container,) = pod["containers"]
    assert container["securityContext"] == RESTRICTED_CONTAINER
    assert _tmp_volume(pod) == {"name": "tmp", "emptyDir": {"sizeLimit": "64Mi"}}
    mounts = {mount["mountPath"] for mount in container["volumeMounts"]}
    assert "/data/configdb" in mounts


def test_security_context_openshift() -> None:
    """On OpenShift, which assigns user and group IDs, the chart sets none."""
    resources = render("--api-versions", OPENSHIFT_SECURITY_API)
    pod = _pod(resources, "Deployment", "mongodb-trs-filer")
    assert pod["securityContext"] == {
        "runAsNonRoot": True,
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def test_security_context_values(tmp_path: Path) -> None:
    """The security contexts and `/tmp` limits are values.

    Args:
        tmp_path: Directory for the values file.
    """
    values = tmp_path / "values.yaml"
    values.write_text(
        yaml.safe_dump(
            {
                "trs_filer": {
                    "podSecurityContext": {"runAsUser": 2000},
                    "securityContext": {"readOnlyRootFilesystem": False},
                    "tmpSizeLimit": None,
                },
                "mongodb": {"podSecurityContext": None, "tmpSizeLimit": "1Gi"},
            }
        ),
        encoding="utf-8",
    )
    resources = render("--values", str(values))
    app = _pod(resources, "Deployment", "trs-filer")
    # Maps are merged with the chart's defaults, `null` removes a key
    assert app["securityContext"]["runAsUser"] == 2000
    assert app["containers"][0]["securityContext"]["readOnlyRootFilesystem"] is False
    assert _tmp_volume(app) == {"name": "tmp", "emptyDir": {}}
    mongodb = _pod(resources, "Deployment", "mongodb-trs-filer")
    assert mongodb["securityContext"] == {}
    assert _tmp_volume(mongodb)["emptyDir"] == {"sizeLimit": "1Gi"}


def test_security_context_without_values() -> None:
    """Values without the new settings (e.g., of older charts) still render.

    So do upgrades with `--reuse-values`; the pods then run as before, and
    MongoDB without its NetworkPolicy. `null` removes the keys from the
    chart's defaults.
    """
    resources = render(
        "--set",
        "trs_filer.podSecurityContext=null",
        "--set",
        "trs_filer.securityContext=null",
        "--set",
        "trs_filer.tmpSizeLimit=null",
        "--set",
        "trs_filer.networkPolicy=null",
        "--set",
        "mongodb.podSecurityContext=null",
        "--set",
        "mongodb.securityContext=null",
        "--set",
        "mongodb.tmpSizeLimit=null",
        "--set",
        "mongodb.networkPolicy=null",
    )
    app = _pod(resources, "Deployment", "trs-filer")
    assert app["securityContext"] == {}
    assert app["containers"][0]["securityContext"] == {}
    assert of_kind(resources, "NetworkPolicy") == []


def test_mongodb_network_policy() -> None:
    """By default, only the app's pods may connect to MongoDB."""
    (policy,) = of_kind(render(), "NetworkPolicy")
    assert policy["metadata"]["name"] == "mongodb-trs-filer"
    assert policy["spec"] == {
        "podSelector": {"matchLabels": {"app": "mongodb-trs-filer"}},
        "policyTypes": ["Ingress"],
        "ingress": [
            {
                "from": [{"podSelector": {"matchLabels": {"app": "trs-filer"}}}],
                "ports": [{"port": 27017, "protocol": "TCP"}],
            }
        ],
    }


def test_mongodb_network_policy_disabled() -> None:
    """`mongodb.networkPolicy.enabled: false` leaves MongoDB's policy out."""
    resources = render("--set", "mongodb.networkPolicy.enabled=false")
    assert of_kind(resources, "NetworkPolicy") == []


def test_app_network_policy(tmp_path: Path) -> None:
    """`trs_filer.networkPolicy` lets only the listed peers connect to the app.

    Args:
        tmp_path: Directory for the values file.
    """
    peer = {
        "namespaceSelector": {
            "matchLabels": {"kubernetes.io/metadata.name": "ingress-nginx"}
        }
    }
    values = tmp_path / "values.yaml"
    values.write_text(
        yaml.safe_dump(
            {"trs_filer": {"networkPolicy": {"enabled": True, "ingressFrom": [peer]}}}
        ),
        encoding="utf-8",
    )
    policies = {
        policy["metadata"]["name"]: policy
        for policy in of_kind(render("--values", str(values)), "NetworkPolicy")
    }
    assert sorted(policies) == ["mongodb-trs-filer", "trs-filer"]
    assert policies["trs-filer"]["spec"] == {
        "podSelector": {"matchLabels": {"app": "trs-filer"}},
        "policyTypes": ["Ingress"],
        "ingress": [{"from": [peer], "ports": [{"port": 8080, "protocol": "TCP"}]}],
    }


def test_app_network_policy_needs_peers() -> None:
    """The app's policy without peers fails, as it would allow all sources."""
    with pytest.raises(subprocess.CalledProcessError) as error:
        render("--set", "trs_filer.networkPolicy.enabled=true")
    assert "trs_filer.networkPolicy.ingressFrom must list" in error.value.stderr
