"""Tests of how the Helm chart (`deployment/`) exposes the app.

They render the chart with `helm template` and are skipped if Helm is not
installed (it is on GitHub's Ubuntu runners).
"""

from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
HELM = shutil.which("helm")
ROUTE_API = "route.openshift.io/v1"

pytestmark = pytest.mark.skipif(HELM is None, reason="Helm is not installed")


def render(*args: str) -> list[dict[str, Any]]:
    """Render the chart with `helm template`.

    Args:
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        The rendered resources.
    """
    assert HELM is not None
    result = subprocess.run(  # noqa: S603 (fixed executable, no shell)
        [
            HELM,
            "template",
            "trs-filer",
            str(ROOT / "deployment"),
            "--set",
            "host_name=trs.example.org",
            *args,
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def kinds(resources: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
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
    assert len(kinds(resources, "Ingress")) == 1
    assert kinds(resources, "Route") == []


def test_route_without_ingress() -> None:
    """Without the Ingress, the chart creates the Route, without annotations."""
    resources = render(
        "--api-versions", ROUTE_API, "--set", "trs_filer.ingress.enabled=false"
    )
    assert kinds(resources, "Ingress") == []
    (route,) = kinds(resources, "Route")
    assert "annotations" not in route["metadata"]


def test_route_needs_route_api() -> None:
    """The chart creates no Route if the cluster serves no Routes."""
    resources = render("--set", "trs_filer.ingress.enabled=false")
    assert kinds(resources, "Route") == []


def test_route_annotations() -> None:
    """The Route gets the annotations of `trs_filer.route.annotations`."""
    resources = render(
        "--api-versions",
        ROUTE_API,
        "--set",
        "trs_filer.ingress.enabled=false",
        "--set-string",
        "trs_filer.route.annotations.haproxy\\.router\\.openshift\\.io/"
        "ip_allowlist=192.0.2.0/24",
    )
    (route,) = kinds(resources, "Route")
    assert route["metadata"]["annotations"] == {
        "haproxy.router.openshift.io/ip_allowlist": "192.0.2.0/24"
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
    assert kinds(resources, "Route") == []
    assert kinds(resources, "Ingress") == []
