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


def _app_env(resources: list[dict[str, Any]]) -> dict[str, str]:
    """Get the environment variables of the app's container.

    Args:
        resources: Rendered resources.

    Returns:
        The variables, by name.
    """
    (deployment,) = (
        resource
        for resource in of_kind(resources, "Deployment")
        if resource["metadata"]["name"] == "trs-filer"
    )
    (container,) = deployment["spec"]["template"]["spec"]["containers"]
    return {variable["name"]: variable["value"] for variable in container["env"]}


def test_forwarded_allow_ips_default() -> None:
    """By default, the app trusts forwarded headers from every address.

    So that links keep `https` behind any ingress controller or router.
    """
    assert _app_env(render())["FORWARDED_ALLOW_IPS"] == "*"


def test_forwarded_allow_ips() -> None:
    """`trs_filer.forwardedAllowIps` sets the addresses of trusted proxies."""
    env = _app_env(
        render("--set-string", "trs_filer.forwardedAllowIps=10.0.0.0/8\\,192.0.2.1")
    )
    assert env["FORWARDED_ALLOW_IPS"] == "10.0.0.0/8,192.0.2.1"


def test_forwarded_allow_ips_without_value() -> None:
    """Values without `trs_filer.forwardedAllowIps` keep trusting every address.

    E.g., upgrades with `--reuse-values` from charts without the value.
    """
    env = _app_env(render("--set", "trs_filer.forwardedAllowIps=null"))
    assert env["FORWARDED_ALLOW_IPS"] == "*"
