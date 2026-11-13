"""Tests of the Helm chart (`deployment/`), a thin chart on FOCA's library chart.

They render the chart with `helm template`. Without Helm, they are skipped,
except in CI (`CI` set), where they fail: GitHub's Ubuntu runners have Helm.
The library chart (`foca-common`) must be downloaded first (`helm dependency
build deployment`), or they fail.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deployment"
# Values of CI's lint: a host name, the Secret of MongoDB's credentials and a
# fictitious identity provider with an admin group
TEST_VALUES = CHART / "ci" / "test-values.yaml"
HELM = shutil.which("helm")
RELEASE = "trs-filer"
# Names of the app's and MongoDB's resources of the release `trs-filer`
APP = "trs-filer"
MONGODB = "trs-filer-mongodb"
HOST = "trs.example.org"
SECRET = "trs-filer-mongodb-credentials"  # noqa: S105 (a Secret's name)
ROUTE_API = ("--api-versions", "route.openshift.io/v1")
OPENSHIFT_API = ("--api-versions", "security.openshift.io/v1")
NO_INGRESS = ("--set", "trsFiler.ingress.enabled=false")
LIBRARY = "foca-common"

pytestmark = pytest.mark.skipif(
    HELM is None and not os.environ.get("CI"), reason="Helm is not installed"
)

Manifest = dict[str, Any]


def helm_template(chart: Path, *args: str, release: str = RELEASE) -> str:
    """Render a chart with `helm template`, with the values of CI's lint.

    Args:
        chart: Directory of the chart.
        *args: Further arguments of `helm template`, e.g., `--set`.
        release: Name of the release.

    Returns:
        The rendered manifests.

    Raises:
        RuntimeError: The library chart is missing.
    """
    assert HELM is not None, "Helm is not installed"
    if not list((chart / "charts").glob(f"{LIBRARY}-*.tgz")):
        raise RuntimeError(
            "The library chart is missing: run `helm dependency build deployment`"
        )
    result = subprocess.run(  # noqa: S603 (fixed executable, no shell)
        [
            HELM,
            "template",
            release,
            str(chart),
            "--namespace",
            "trs",
            "--values",
            str(TEST_VALUES),
            *args,
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


def render(*args: str, release: str = RELEASE) -> list[Manifest]:
    """Render the chart's resources.

    Args:
        *args: Further arguments of `helm template`, e.g., `--set`.
        release: Name of the release.

    Returns:
        The rendered resources.
    """
    rendered = helm_template(CHART, *args, release=release)
    return [doc for doc in yaml.safe_load_all(rendered) if doc]


def render_error(*args: str) -> str:
    """Render the chart, expecting Helm to fail.

    Args:
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        Helm's error output.
    """
    with pytest.raises(subprocess.CalledProcessError) as error:
        helm_template(CHART, *args)
    stderr: str = error.value.stderr
    return stderr


def copy_chart(tmp_path: Path, templates: dict[str, str]) -> Path:
    """Copy the chart, with additional templates.

    Args:
        tmp_path: Directory for the copy of the chart.
        templates: Contents of the additional templates, by file name.

    Returns:
        The copy of the chart.
    """
    chart = tmp_path / "chart"
    shutil.copytree(CHART, chart)
    for name, template in templates.items():
        (chart / "templates" / name).write_text(template, encoding="utf-8")
    return chart


def render_notes(tmp_path: Path, *args: str) -> str:
    """Render the chart's `NOTES.txt`, which `helm template` leaves out.

    A template of a copy of the chart renders `NOTES.txt` into a document.

    Args:
        tmp_path: Directory for the copy of the chart.
        *args: Further arguments of `helm template`, e.g., `--set`.

    Returns:
        The rendered notes.
    """
    chart = copy_chart(
        tmp_path,
        {"notes.yaml": 'notes: {{ tpl (.Files.Get "NOTES.raw") . | toJson }}\n'},
    )
    (chart / "templates" / "NOTES.txt").rename(chart / "NOTES.raw")
    manifests = helm_template(chart, "--show-only", "templates/notes.yaml", *args)
    notes: str = yaml.safe_load(manifests)["notes"]
    return notes


def find(resources: list[Manifest], kind: str, name: str) -> Manifest:
    """Get the resource of a kind and name.

    Args:
        resources: Rendered resources.
        kind: Kind of the resource, e.g., `Deployment`.
        name: Name of the resource.

    Returns:
        The resource.
    """
    (resource,) = [
        resource
        for resource in resources
        if resource["kind"] == kind and resource["metadata"]["name"] == name
    ]
    return resource


def of_kind(resources: list[Manifest], kind: str) -> list[Manifest]:
    """Select the resources of a kind.

    Args:
        resources: Rendered resources.
        kind: Kind to select, e.g., `Route`.

    Returns:
        The resources of that kind.
    """
    return [resource for resource in resources if resource["kind"] == kind]


def overlay(resources: list[Manifest], name: str = APP) -> dict[str, Any]:
    """Get the app's config overlay.

    Args:
        resources: Rendered resources.
        name: Name of the app's resources.

    Returns:
        The overlay of the ConfigMap `<app>-config`.
    """
    config_map = find(resources, "ConfigMap", f"{name}-config")
    config: dict[str, Any] = yaml.safe_load(config_map["data"]["overlay.yaml"])
    return config


def pod_spec(resources: list[Manifest], name: str = APP) -> Manifest:
    """Get the pod spec of a Deployment.

    Args:
        resources: Rendered resources.
        name: Name of the Deployment.

    Returns:
        Its pod spec.
    """
    spec: Manifest = find(resources, "Deployment", name)["spec"]["template"]["spec"]
    return spec


def container(resources: list[Manifest], name: str = APP) -> Manifest:
    """Get the container of a Deployment.

    Args:
        resources: Rendered resources.
        name: Name of the Deployment.

    Returns:
        Its only container.
    """
    (only,) = pod_spec(resources, name)["containers"]
    return only


def env(resources: list[Manifest], name: str = APP) -> dict[str, Any]:
    """Get the environment variables of a Deployment's container.

    Args:
        resources: Rendered resources.
        name: Name of the Deployment.

    Returns:
        The variables, by name: their values, or their `valueFrom`.
    """
    return {
        var["name"]: var.get("value", var.get("valueFrom"))
        for var in container(resources, name).get("env", [])
    }


def test_resources() -> None:
    """The chart renders the library's resources, without the config Job.

    No Job, ServiceAccount or RBAC: Helm renders the config overlay.
    """
    resources = render()
    names = {(r["kind"], r["metadata"]["name"]) for r in resources}
    assert names == {
        ("ConfigMap", f"{APP}-config"),
        ("ConfigMap", f"{MONGODB}-init-script"),
        ("Deployment", APP),
        ("Deployment", MONGODB),
        ("Service", APP),
        ("Service", MONGODB),
        ("PersistentVolumeClaim", MONGODB),
        ("NetworkPolicy", MONGODB),
        ("Ingress", APP),
    }
    for resource in resources:
        labels = resource["metadata"]["labels"]
        assert labels["app.kubernetes.io/instance"] == RELEASE
        assert labels["app.kubernetes.io/name"] == "trs-filer"


def test_names_from_release() -> None:
    """Resource names are derived from the release name."""
    resources = render(release="prod")
    assert find(resources, "Deployment", "prod-trs-filer")
    assert find(resources, "Deployment", "prod-trs-filer-mongodb")
    config = overlay(resources, "prod-trs-filer")
    assert config["db"]["host"] == "prod-trs-filer-mongodb"


def test_config_overlay() -> None:
    """The overlay has the public URL, MongoDB's host and the `config` value.

    The public URL (`custom.service`) is `https://<hostName>:443`.
    """
    config = overlay(render())
    assert config["custom"]["service"] == {
        "url_prefix": "https",
        "external_host": HOST,
        "external_port": 443,
    }
    assert config["db"] == {"host": MONGODB}
    assert config["security"]["auth"]["issuers"] == ["https://login.example.org/oidc/"]


def test_config_overrides_generated() -> None:
    """`config` takes precedence over the generated config, merged by key."""
    config = overlay(
        render(
            "--set",
            "config.custom.service.external_port=8443",
            "--set",
            "config.custom.remote_files.max_size=10",
        )
    )
    assert config["custom"]["service"]["external_port"] == 8443
    assert config["custom"]["service"]["external_host"] == HOST
    assert config["custom"]["remote_files"] == {"max_size": 10}


def test_config_custom_null() -> None:
    """`config.custom: null` keeps the generated public URL."""
    config = overlay(render("--set-json", "config.custom=null"))
    assert config["custom"]["service"]["external_host"] == HOST


def test_deployment() -> None:
    """The app reads the overlay, and MongoDB's app user from the Secret.

    The chart sets no database (`MONGO_DBNAME`): the app uses that of its
    base config (`trsStore`). It trusts no forwarded headers by default.
    """
    resources = render()
    variables = env(resources)
    assert variables["FOCA_CONFIG_OVERLAY"] == "/etc/trs-filer/overlay.yaml"
    assert variables["MONGO_USERNAME"] == {
        "secretKeyRef": {"name": SECRET, "key": "username"}
    }
    assert variables["MONGO_PASSWORD"] == {
        "secretKeyRef": {"name": SECRET, "key": "password"}
    }
    assert variables["GUNICORN_CMD_ARGS"] == (
        "--workers 1 --threads 4 --timeout 30 --graceful-timeout 20 --keep-alive 100"
    )
    for name in ("MONGO_DBNAME", "MONGO_HOST", "FORWARDED_ALLOW_IPS"):
        assert name not in variables
    spec = pod_spec(resources)
    assert spec["automountServiceAccountToken"] is False
    assert "serviceAccountName" not in spec


def test_image() -> None:
    """The image is tagged with `appVersion` (`dev`), unless a tag is set."""
    app = container(render())
    assert app["image"] == "docker.io/elixircloud/trs-filer:dev"
    assert app["imagePullPolicy"] == "Always"
    tagged = container(render("--set", "trsFiler.tag=1.2.3"))
    assert tagged["image"] == "docker.io/elixircloud/trs-filer:1.2.3"


def test_probes() -> None:
    """The app's probes request the Swagger UI."""
    app = container(render())
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert app[probe]["httpGet"] == {"path": "/ga4gh/trs/v2/ui/", "port": 8080}


def test_gunicorn() -> None:
    """The Gunicorn values are passed to the image."""
    variables = env(render("--set", "trsFiler.gunicorn.workers=2"))
    assert variables["GUNICORN_CMD_ARGS"].startswith("--workers 2 ")


def test_extra_env() -> None:
    """`trsFiler.extraEnv` sets further variables, e.g., `FORWARDED_ALLOW_IPS`."""
    extra = [{"name": "FORWARDED_ALLOW_IPS", "value": "192.0.2.0/24"}]
    variables = env(render("--set-json", f"trsFiler.extraEnv={json.dumps(extra)}"))
    assert variables["FORWARDED_ALLOW_IPS"] == "192.0.2.0/24"


def test_extra_env_reserved() -> None:
    """`trsFiler.extraEnv` must not set the chart's variables."""
    extra = [{"name": "FOCA_CONFIG_OVERLAY", "value": "/etc/other.yaml"}]
    error = render_error("--set-json", f"trsFiler.extraEnv={json.dumps(extra)}")
    assert "FOCA_CONFIG_OVERLAY" in error


def test_init_script() -> None:
    """MongoDB's init script creates the app user in the app's database."""
    resources = render()
    config_map = find(resources, "ConfigMap", f"{MONGODB}-init-script")
    script = config_map["data"]["create-app-user.js"]
    assert "getSiblingDB('trsStore')" in script
    assert "trs-filer-db" not in script


def test_mongodb_auth_needs_secret() -> None:
    """Rendering fails without the Secret of MongoDB's credentials."""
    error = render_error("--set", "mongodb.auth.existingSecret=")
    assert "mongodb.auth.existingSecret" in error


def test_mongodb_auth_disabled() -> None:
    """Without authentication, the chart creates no users and passes none."""
    resources = render(
        "--set", "mongodb.auth.enabled=false", "--set", "mongodb.auth.existingSecret="
    )
    names = [r["metadata"]["name"] for r in of_kind(resources, "ConfigMap")]
    assert names == [f"{APP}-config"]
    assert "MONGO_USERNAME" not in env(resources)


def test_mongodb_persistence() -> None:
    """MongoDB's claim is kept when the release is uninstalled."""
    claim = find(render(), "PersistentVolumeClaim", MONGODB)
    assert claim["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    assert claim["spec"]["resources"]["requests"]["storage"] == "1Gi"


def test_mongodb_volume_size_deprecated() -> None:
    """`mongodb.volumeSize` of the earlier charts fails with `persistence.size`."""
    assert "volumeSize" in render_error("--set", "mongodb.volumeSize=2Gi")


def test_security_contexts() -> None:
    """The pods run as non-root users, with a read-only root file system."""
    resources = render()
    for name in (APP, MONGODB):
        assert pod_spec(resources, name)["securityContext"]["runAsNonRoot"] is True
        context = container(resources, name)["securityContext"]
        assert context["readOnlyRootFilesystem"] is True
    mongodb = pod_spec(resources, MONGODB)["securityContext"]
    assert mongodb["runAsUser"] == 999
    assert mongodb["fsGroupChangePolicy"] == "OnRootMismatch"


def test_security_contexts_openshift() -> None:
    """On OpenShift, user and group IDs are left to OpenShift."""
    mongodb = pod_spec(render(*OPENSHIFT_API), MONGODB)["securityContext"]
    for key in ("runAsUser", "runAsGroup", "fsGroup"):
        assert key not in mongodb


def test_route_without_ingress() -> None:
    """Without the Ingress, the chart creates a Route on OpenShift."""
    resources = render(*ROUTE_API, *NO_INGRESS)
    assert of_kind(resources, "Ingress") == []
    assert find(resources, "Route", APP)["spec"]["host"] == HOST
    assert of_kind(render(*NO_INGRESS), "Route") == []
    assert of_kind(render(*ROUTE_API), "Route") == []


def test_http_route() -> None:
    """With the Ingress disabled, the chart can attach an HTTPRoute."""
    parents = [{"name": "gateway", "namespace": "gateway-system"}]
    resources = render(
        *NO_INGRESS,
        "--set",
        "trsFiler.httpRoute.enabled=true",
        "--set-json",
        f"trsFiler.httpRoute.parentRefs={json.dumps(parents)}",
    )
    assert find(resources, "HTTPRoute", APP)["spec"]["hostnames"] == [HOST]


def test_app_network_policy() -> None:
    """The app's NetworkPolicy admits the peers in `ingressFrom`, required."""
    peers = [{"namespaceSelector": {"matchLabels": {"name": "ingress"}}}]
    resources = render(
        "--set",
        "trsFiler.networkPolicy.enabled=true",
        "--set-json",
        f"trsFiler.networkPolicy.ingressFrom={json.dumps(peers)}",
    )
    policy = find(resources, "NetworkPolicy", APP)
    assert policy["spec"]["ingress"][0]["from"] == peers
    assert "ingressFrom" in render_error("--set", "trsFiler.networkPolicy.enabled=true")


def test_replicas() -> None:
    """Several replicas get a PodDisruptionBudget."""
    resources = render("--set", "trsFiler.replicas=2")
    assert find(resources, "Deployment", APP)["spec"]["replicas"] == 2
    assert find(resources, "PodDisruptionBudget", APP)


def test_autoscaling_rejected() -> None:
    """The chart has no HorizontalPodAutoscaler, so the schema refuses it."""
    assert "autoscaling" in render_error("--set", "trsFiler.autoscaling.enabled=true")


def test_host_name_required() -> None:
    """Rendering fails without `hostName`, which sets the public URL."""
    assert "hostName must be set" in render_error("--set", "hostName=")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--set", "host_name=trs.example.org"), "host_name was renamed to hostName"),
        (("--set", "trs_filer.appName=trs"), "trs_filer was renamed to trsFiler"),
        (("--set", "apiServer=kubernetes.default.svc:443"), "apiServer was removed"),
        (("--set", "clusterType=openshift"), "clusterType was removed"),
        (("--set", "trsFiler.appName=trs"), "trsFiler.appName was removed"),
        (("--set", "trsFiler.config.x=1"), "trsFiler.config was removed"),
        (
            ("--set", "trsFiler.forwardedAllowIps=*"),
            "trsFiler.forwardedAllowIps was removed",
        ),
        (("--set", "mongodb.dbName=trs-filer-db"), "mongodb.dbName was removed"),
    ],
)
def test_legacy_values(args: tuple[str, ...], message: str) -> None:
    """Values of the charts before foca-common fail, instead of being ignored.

    Args:
        args: Arguments that set a legacy value.
        message: Expected part of the error.
    """
    error = render_error(*args)
    assert message in error
    assert "From earlier charts" in error


def test_legacy_values_before_host_name() -> None:
    """A renamed `host_name` is reported instead of the missing `hostName`."""
    error = render_error("--set", "hostName=", "--set", "host_name=trs.example.org")
    assert "host_name was renamed" in error


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--set-json", "config.security.auth.issuers=[]"), "issuers"),
        (("--set-json", "config.security.auth.audience=null"), "audience"),
        (("--set-json", "config.security.access_control.group_mapping={}"), "admin"),
        (("--set", "config.security.access_control.enforce=false"), "enforce"),
    ],
)
def test_access_control_required(args: tuple[str, ...], message: str) -> None:
    """Rendering fails without what the app needs to start (as on startup).

    Args:
        args: Arguments that unset a required setting.
        message: Expected part of the error.
    """
    assert message in render_error(*args)


def test_access_control_without_admins() -> None:
    """Without required admins, no admin group is needed."""
    resources = render(
        "--set-json",
        "config.security.access_control.group_mapping={}",
        "--set",
        "config.security.access_control.require_admin=false",
    )
    assert overlay(resources)["security"]["access_control"]["require_admin"] is False


def test_test_values_not_packaged(tmp_path: Path) -> None:
    """The packaged chart has the library, but not the CI values and digest.

    Args:
        tmp_path: Directory for the package.
    """
    assert HELM is not None
    subprocess.run(  # noqa: S603 (fixed executable, no shell)
        [HELM, "package", str(CHART), "--destination", str(tmp_path)],
        capture_output=True,
        check=True,
    )
    (package,) = tmp_path.glob("trs-filer-*.tgz")
    with tarfile.open(package) as archive:
        names = archive.getnames()
    assert "trs-filer/values.schema.json" in names
    assert [name for name in names if name.startswith(f"trs-filer/charts/{LIBRARY}")]
    assert not [name for name in names if "/ci/" in name]
    assert "trs-filer/charts.sha256" not in names


def test_library_versions() -> None:
    """Chart, lock, digest and schema name the same library version."""
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
    lock = yaml.safe_load((CHART / "Chart.lock").read_text())
    (dependency,) = chart["dependencies"]
    (locked,) = lock["dependencies"]
    assert dependency["name"] == locked["name"] == LIBRARY
    assert dependency["version"] == locked["version"]
    version = dependency["version"]
    digest = (CHART / "charts.sha256").read_text()
    assert digest.rstrip().endswith(f"  charts/{LIBRARY}-{version}.tgz")
    schema = json.loads((CHART / "values.schema.json").read_text())
    assert f"{LIBRARY} {version} " in schema["$comment"]


# Calls the check of upgrades with a Deployment as `lookup` returns it
LEGACY_CHECK = """{{- include "trs-filer.failIfLegacy" (dict "root" . "resource" (dict
  "metadata" (dict
    "name" "NAME"
    "annotations" (dict "meta.helm.sh/release-name" "RELEASE")
    "labels" (dict LABELS)
  )
)) }}
"""


INSTANCE = (
    '"app.kubernetes.io/instance" "trs-filer" "app.kubernetes.io/name" "trs-filer"'
)
MONGODB_LABELS = f'{INSTANCE} "app.kubernetes.io/component" "mongodb"'
EXISTING_CLAIM = ("--set", "mongodb.persistence.existingClaim=old-claim")


@pytest.mark.parametrize(
    ("release", "name", "labels", "args", "error"),
    [
        # A Deployment of a chart before foca-common, of this release
        ("trs-filer", APP, '"app" "trs-filer"', (), "uninstall it and install"),
        # Ones of this chart
        ("trs-filer", APP, INSTANCE, (), None),
        ("trs-filer", MONGODB, MONGODB_LABELS, (), None),
        # Another name label (a changed nameOverride), with the same names
        (
            "trs-filer",
            APP,
            '"app.kubernetes.io/instance" "trs-filer" "app.kubernetes.io/name" "filer"',
            (),
            "a changed nameOverride",
        ),
        # Its MongoDB under another name (a changed fullnameOverride)
        ("trs-filer", "old-mongodb", MONGODB_LABELS, (), "new, empty claim"),
        # ... which keeps its data with an existing claim, or has none
        ("trs-filer", "old-mongodb", MONGODB_LABELS, EXISTING_CLAIM, None),
        (
            "trs-filer",
            "old-mongodb",
            MONGODB_LABELS,
            ("--set", "mongodb.persistence.enabled=false"),
            None,
        ),
        (
            "trs-filer",
            "old-mongodb",
            MONGODB_LABELS,
            ("--set", "mongodb.enabled=false", "--set", "config.db.host=db.local"),
            None,
        ),
        # Ones of another release
        ("other", APP, '"app" "trs-filer"', (), None),
        ("other", "old-mongodb", MONGODB_LABELS, (), None),
    ],
)
def test_fail_if_legacy(
    tmp_path: Path,
    release: str,
    name: str,
    labels: str,
    args: tuple[str, ...],
    error: str | None,
) -> None:
    """Upgrades fail for earlier charts' Deployments and for renames.

    `lookup` finds nothing in `helm template`, so the check is called with a
    Deployment of the release as `lookup` would return it.

    Args:
        tmp_path: Directory for the copy of the chart.
        release: Release that the Deployment belongs to.
        name: Name of the Deployment.
        labels: Labels of the Deployment (template arguments of `dict`).
        args: Further arguments of `helm template`.
        error: Expected part of the error, or None if the check passes.
    """
    template = (
        LEGACY_CHECK.replace("RELEASE", release)
        .replace("NAME", name)
        .replace("LABELS", labels)
    )
    chart = copy_chart(tmp_path, {"legacy-check.yaml": template})
    if error:
        with pytest.raises(subprocess.CalledProcessError) as failure:
            helm_template(chart, *args)
        assert error in failure.value.stderr
    else:
        helm_template(chart, *args)


def test_upgrade_check_included() -> None:
    """The check of upgrades runs on upgrades, once, in the app's ConfigMap.

    `lookup` finds nothing in `helm template`, so an upgrade renders; the
    check itself is tested by `test_fail_if_legacy`.
    """
    templates = {
        path.name: path.read_text(encoding="utf-8")
        for path in (CHART / "templates").glob("*.yaml")
    }
    assert [
        name for name, text in templates.items() if "trs-filer.checkUpgrade" in text
    ] == ["configmap.yaml"]
    helpers = (CHART / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    check = helpers.split('{{- define "trs-filer.checkUpgrade" -}}')[1]
    assert check.lstrip().startswith("{{- if .Release.IsUpgrade -}}")
    assert find(render("--is-upgrade"), "ConfigMap", f"{APP}-config")


def test_readme_references() -> None:
    """The chart's references to sections of its README name existing ones.

    References (e.g., "see deployment/README.md, Server") may span lines of
    comments, which are joined first.
    """
    readme = (CHART / "README.md").read_text(encoding="utf-8")
    headings = re.findall(r"^#+ (.+)$", readme, re.MULTILINE)
    prefix = "deployment/README.md, "
    files = [
        CHART / "values.yaml",
        CHART / "values.schema.json",
        *(CHART / "templates").iterdir(),
    ]
    sections = []
    for path in files:
        text = re.sub(r"\s*\n\s*#?\s*", " ", path.read_text(encoding="utf-8"))
        for part in text.split(prefix)[1:]:
            matches = [
                heading
                for heading in headings
                if re.match(rf"{re.escape(heading)}\b", part)
            ]
            assert matches, f"{path.name}: {prefix}{part[:40]}"
            sections.extend(matches)
    assert {"Configuration", "From earlier charts", "Several replicas"} <= set(sections)


def test_notes(tmp_path: Path) -> None:
    """The notes show the API's URL, and that the Ingress has no TLS.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(tmp_path)
    assert f"https://{HOST}/ga4gh/trs/v2/service-info" in notes
    assert "The Ingress has no TLS" in notes
    assert "WARNING" not in notes


def test_notes_warnings(tmp_path: Path) -> None:
    """The notes warn of disabled authentication.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(
        tmp_path,
        "--set",
        "config.api.specs.trs.disable_auth=true",
        "--set",
        "mongodb.auth.enabled=false",
    )
    assert "authentication is disabled (config.api.specs.trs.disable_auth)" in notes
    assert "MongoDB runs without authentication" in notes


def test_notes_config_not_maps(tmp_path: Path) -> None:
    """The notes render with sections of `config` that are null.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(tmp_path, "--set-json", "config.api.specs=null")
    assert "authentication is disabled" not in notes


def test_notes_not_exposed(tmp_path: Path) -> None:
    """Without an Ingress, HTTPRoute or Route, the notes show a port forward.

    Args:
        tmp_path: Directory for the copies of the chart.
    """
    notes = render_notes(tmp_path / "plain", *NO_INGRESS)
    assert f"kubectl port-forward svc/{APP} 8080:8080 -n trs" in notes
    assert "http://localhost:8080/ga4gh/trs/v2/ui/" in notes
    notes = render_notes(tmp_path / "route", *NO_INGRESS, *ROUTE_API)
    assert "port-forward" not in notes
    assert f"https://{HOST}/ga4gh/trs/v2/ui/" in notes
