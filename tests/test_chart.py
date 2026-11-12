"""Tests of how the Helm chart (`deployment/`) exposes the app.

They render the chart with `helm template`. Without Helm, they are skipped,
except in CI (`CI` set), where they fail: GitHub's Ubuntu runners have Helm.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deployment"
# Values of CI's lint, e.g., the Secret of MongoDB's credentials
TEST_VALUES = CHART / "ci" / "test-values.yaml"
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
            "--values",
            str(TEST_VALUES),
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
    """With the Ingress, the notes give its URLs and who may write.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(tmp_path)
    assert "writes (POST, PUT and DELETE) need an access token" in notes
    assert "has no authentication" not in notes
    assert "authentication is disabled" not in notes
    assert "http://trs.example.org/ga4gh/trs/v2/" in notes
    assert "port-forward" not in notes


def test_notes_auth_disabled(tmp_path: Path) -> None:
    """With authentication disabled, the notes warn that everyone may write.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    notes = render_notes(
        tmp_path, "--set", "trs_filer.config.api.specs.trs.disable_auth=true"
    )
    assert "WARNING: authentication is disabled" in notes


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
        The variables with values, by name (not those from Secrets).
    """
    (deployment,) = (
        resource
        for resource in of_kind(resources, "Deployment")
        if resource["metadata"]["name"] == "trs-filer"
    )
    (container,) = deployment["spec"]["template"]["spec"]["containers"]
    return {
        variable["name"]: variable["value"]
        for variable in container["env"]
        if "value" in variable
    }


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


def test_forwarded_allow_ips_list(tmp_path: Path) -> None:
    """`trs_filer.forwardedAllowIps` may be a list.

    Args:
        tmp_path: Directory for the values file.
    """
    values = tmp_path / "values.yaml"
    values.write_text(
        yaml.safe_dump(
            {"trs_filer": {"forwardedAllowIps": ["10.0.0.0/8", "192.0.2.1"]}}
        ),
        encoding="utf-8",
    )
    env = _app_env(render("--values", str(values)))
    assert env["FORWARDED_ALLOW_IPS"] == "10.0.0.0/8,192.0.2.1"


@pytest.mark.parametrize("value", ["", "[]", "' '", "','", "['', ' ']"])
def test_forwarded_allow_ips_empty(tmp_path: Path, value: str) -> None:
    """An empty `trs_filer.forwardedAllowIps` fails rendering.

    Gunicorn would trust no address, so links would get `http`.

    Args:
        tmp_path: Directory for the values file.
        value: The empty value, as YAML.
    """
    values = tmp_path / "values.yaml"
    values.write_text(
        f"trs_filer:\n  forwardedAllowIps: {value or "''"}\n", encoding="utf-8"
    )
    with pytest.raises(subprocess.CalledProcessError) as error:
        render("--values", str(values))
    assert "trs_filer.forwardedAllowIps must not be empty" in error.value.stderr


@pytest.mark.parametrize("value", ["false", "5", "{10.0.0.0/8,5}"])
def test_forwarded_allow_ips_type(value: str) -> None:
    """`trs_filer.forwardedAllowIps` other than strings fails rendering.

    Also lists with other members.

    Args:
        value: The value, as `--set` parses it (a boolean, a number, or a
            list with a number).
    """
    with pytest.raises(subprocess.CalledProcessError) as error:
        render("--set", f"trs_filer.forwardedAllowIps={value}")
    assert "must be a string or a list of strings" in error.value.stderr


@pytest.mark.parametrize("value", ["10.0.0.0 /8", "10.0.0.0/8\\,192.0.2. 1"])
def test_forwarded_allow_ips_inner_spaces(value: str) -> None:
    """Entries with spaces inside fail rendering, instead of being joined.

    E.g., `10.0.0.0 /8` would otherwise become `10.0.0.0/8`.

    Args:
        value: The value, as `--set-string` parses it.
    """
    with pytest.raises(subprocess.CalledProcessError) as error:
        render("--set-string", f"trs_filer.forwardedAllowIps={value}")
    assert "must not contain spaces" in error.value.stderr


def test_forwarded_allow_ips_spaces() -> None:
    """Spaces and empty entries are dropped from `trs_filer.forwardedAllowIps`."""
    env = _app_env(
        render("--set-string", "trs_filer.forwardedAllowIps=10.0.0.0/8\\, \\,192.0.2.1")
    )
    assert env["FORWARDED_ALLOW_IPS"] == "10.0.0.0/8,192.0.2.1"


def test_forwarded_allow_ips_without_value() -> None:
    """Values without `trs_filer.forwardedAllowIps` keep trusting every address.

    E.g., upgrades with `--reuse-values` from charts without the value;
    `null` removes the key from the chart's defaults, as such values lack it.
    """
    env = _app_env(render("--set", "trs_filer.forwardedAllowIps=null"))
    assert env["FORWARDED_ALLOW_IPS"] == "*"


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
        "fsGroupChangePolicy": "OnRootMismatch",
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    (container,) = pod["containers"]
    assert container["securityContext"] == RESTRICTED_CONTAINER
    assert _tmp_volume(pod) == {"name": "tmp", "emptyDir": {"sizeLimit": "64Mi"}}
    mounts = {mount["mountPath"] for mount in container["volumeMounts"]}
    assert "/data/configdb" in mounts


@pytest.mark.parametrize(
    ("kind", "name", "fs_group"),
    [
        ("Deployment", "trs-filer", False),
        ("Job", "configmap-job-", False),
        ("Deployment", "mongodb-trs-filer", True),
    ],
)
def test_security_context_openshift(kind: str, name: str, fs_group: bool) -> None:
    """On OpenShift, which assigns user and group IDs, the chart sets none.

    Also not if set in the values (here: `runAsUser` of all three); the
    other settings are kept.

    Args:
        kind: Kind of the workload.
        name: Name of the workload, or its start.
        fs_group: Whether the pod has MongoDB's `fsGroupChangePolicy`.
    """
    resources = render(
        "--api-versions",
        OPENSHIFT_SECURITY_API,
        "--set",
        "trs_filer.podSecurityContext.runAsUser=2000",
        "--set",
        "mongodb.podSecurityContext.runAsUser=2000",
    )
    pod = _pod(resources, kind, name)
    expected: dict[str, Any] = {
        "runAsNonRoot": True,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    if fs_group:
        expected["fsGroupChangePolicy"] = "OnRootMismatch"
    assert pod["securityContext"] == expected
    (container,) = pod["containers"]
    assert container["securityContext"] == RESTRICTED_CONTAINER


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
    for kind, name in [
        ("Deployment", "trs-filer"),
        ("Job", "configmap-job-"),
        ("Deployment", "mongodb-trs-filer"),
    ]:
        pod = _pod(resources, kind, name)
        assert pod["securityContext"] == {}
        assert pod["containers"][0]["securityContext"] == {}
        assert _tmp_volume(pod) == {"name": "tmp", "emptyDir": {}}
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


def test_config_job_rights() -> None:
    """The config Job's ServiceAccount has only the rights that its script uses.

    A namespaced Role allows reading and patching the app's ConfigMap, and
    listing and deleting pods (to restart the app); no ClusterRole (e.g.,
    `admin`) is bound.
    """
    resources = render()
    (job,) = of_kind(resources, "Job")
    account = job["spec"]["template"]["spec"]["serviceAccountName"]
    assert account == "trs-filer-configurer"
    (binding,) = of_kind(resources, "RoleBinding")
    assert binding["subjects"] == [{"kind": "ServiceAccount", "name": account}]
    assert binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "trs-filer-configurer",
    }
    # Renamed from `admin-<appName>-configurer`: `roleRef` is immutable, so
    # upgrades replace the binding instead of patching it
    assert binding["metadata"]["name"] == "trs-filer-configurer"
    (role,) = of_kind(resources, "Role")
    assert role["metadata"]["name"] == "trs-filer-configurer"
    assert role["rules"] == [
        {
            "apiGroups": [""],
            "resources": ["configmaps"],
            "resourceNames": ["app-config-trs-filer"],
            "verbs": ["get", "patch"],
        },
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["list", "delete"]},
    ]
    assert of_kind(resources, "ClusterRole") == []
    assert of_kind(resources, "ClusterRoleBinding") == []


SECRET = "trs-filer-mongodb-credentials"  # noqa: S105 (a Secret's name)


def _env_from_secrets(container: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Get the environment variables of a container that come from Secrets.

    Args:
        container: Container spec.

    Returns:
        The Secret's name and key of each variable, by variable name.
    """
    return {
        variable["name"]: (
            variable["valueFrom"]["secretKeyRef"]["name"],
            variable["valueFrom"]["secretKeyRef"]["key"],
        )
        for variable in container.get("env", [])
        if "secretKeyRef" in variable.get("valueFrom", {})
    }


def _init_scripts(resources: list[dict[str, Any]]) -> dict[str, str]:
    """Get MongoDB's init scripts.

    Args:
        resources: Rendered resources.

    Returns:
        The scripts of the ConfigMap `mongo-init-script-<appName>`, by name.
    """
    (init,) = (
        resource
        for resource in of_kind(resources, "ConfigMap")
        if resource["metadata"]["name"] == "mongo-init-script-trs-filer"
    )
    scripts: dict[str, str] = init["data"]
    return scripts


def test_mongodb_auth_needs_secret() -> None:
    """By default, MongoDB requires credentials: without a Secret, rendering fails."""
    with pytest.raises(subprocess.CalledProcessError) as error:
        render("--set", "mongodb.auth.existingSecret=")
    assert "mongodb.auth.existingSecret must be set" in error.value.stderr


def test_mongodb_auth() -> None:
    """With authentication, MongoDB and the app get their credentials.

    MongoDB gets the root user's and the app user's credentials from the
    Secret, and an init script that creates the app user in the app's
    database; the app connects as the app user.
    """
    resources = render()
    mongodb = _pod(resources, "Deployment", "mongodb-trs-filer")
    (container,) = mongodb["containers"]
    assert _env_from_secrets(container) == {
        "MONGO_INITDB_ROOT_USERNAME": (SECRET, "root-username"),
        "MONGO_INITDB_ROOT_PASSWORD": (SECRET, "root-password"),
        "MONGO_APP_USERNAME": (SECRET, "username"),
        "MONGO_APP_PASSWORD": (SECRET, "password"),
    }
    app = _pod(resources, "Deployment", "trs-filer")
    assert _env_from_secrets(app["containers"][0]) == {
        "MONGO_USERNAME": (SECRET, "username"),
        "MONGO_PASSWORD": (SECRET, "password"),
    }
    script = _init_scripts(resources)["create-app-user.js"]
    assert 'db.getSiblingDB("trs-filer-db").createUser(' in script
    assert "user: process.env.MONGO_APP_USERNAME" in script
    assert "pwd: process.env.MONGO_APP_PASSWORD" in script
    assert "roles: [{ role: 'readWrite', db: \"trs-filer-db\" }]" in script
    # Both scripts of the ConfigMap run on the first start
    (mount,) = (m for m in container["volumeMounts"] if m["name"] == "init-script")
    assert mount == {
        "name": "init-script",
        "mountPath": "/docker-entrypoint-initdb.d",
        "readOnly": True,
    }


def test_mongodb_auth_database_name() -> None:
    """The app user gets access to the database of `mongodb.dbName`."""
    resources = render("--set", "mongodb.dbName=trs")
    script = _init_scripts(resources)["create-app-user.js"]
    assert 'db.getSiblingDB("trs").createUser(' in script
    assert "roles: [{ role: 'readWrite', db: \"trs\" }]" in script


def test_mongodb_database_name_quoted() -> None:
    """The database name is a JavaScript string in the init scripts.

    Quotes in `mongodb.dbName` stay inside the string.
    """
    scripts = _init_scripts(render("--set-string", "mongodb.dbName=a'b\"c"))
    assert 'db.getSiblingDB("a\'b\\"c").createUser(' in scripts["create-app-user.js"]
    assert 'db = db.getSiblingDB("a\'b\\"c");' in scripts["init-script.js"]


@pytest.mark.parametrize("name", ["123", "true", "a'b\"c"])
def test_mongodb_database_name_quoted_env(name: str) -> None:
    """The database name is a string in the app's environment.

    Also names that YAML reads as numbers or booleans.

    Args:
        name: Database name (`mongodb.dbName`).
    """
    env = _app_env(render("--set-string", f"mongodb.dbName={name}"))
    assert env["MONGO_DBNAME"] == name


def test_mongodb_auth_disabled() -> None:
    """`mongodb.auth.enabled: false` runs MongoDB without credentials."""
    resources = render("--set", "mongodb.auth.enabled=false")
    mongodb = _pod(resources, "Deployment", "mongodb-trs-filer")
    assert _env_from_secrets(mongodb["containers"][0]) == {}
    app = _pod(resources, "Deployment", "trs-filer")
    assert _env_from_secrets(app["containers"][0]) == {}
    assert "create-app-user.js" not in _init_scripts(resources)


def test_mongodb_auth_secret_without_enabled() -> None:
    """A Secret's name without `mongodb.auth.enabled` enables authentication.

    E.g., upgrades with `--reuse-values` from older charts and
    `--set mongodb.auth.existingSecret=...`, whose values lack `enabled`.
    """
    resources = render("--set", "mongodb.auth.enabled=null")
    mongodb = _pod(resources, "Deployment", "mongodb-trs-filer")
    assert _env_from_secrets(mongodb["containers"][0])["MONGO_APP_USERNAME"] == (
        SECRET,
        "username",
    )
    assert "create-app-user.js" in _init_scripts(resources)


def test_mongodb_auth_without_values() -> None:
    """Values without `mongodb.auth` (e.g., of older charts) keep MongoDB as it was.

    Simulates the values of upgrades with `--reuse-values` from older
    charts: `null` removes the key from the chart's defaults.
    """
    resources = render("--set", "mongodb.auth=null")
    mongodb = _pod(resources, "Deployment", "mongodb-trs-filer")
    assert _env_from_secrets(mongodb["containers"][0]) == {}
    app = _pod(resources, "Deployment", "trs-filer")
    assert _env_from_secrets(app["containers"][0]) == {}


def test_test_values_not_packaged(tmp_path: Path) -> None:
    """The test values are left out of the packaged chart.

    Args:
        tmp_path: Directory for the package.
    """
    assert HELM
    subprocess.run(  # noqa: S603 (fixed executable, no shell)
        [HELM, "package", str(CHART), "--destination", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    (package,) = tmp_path.glob("*.tgz")
    with tarfile.open(package) as archive:
        names = archive.getnames()
    assert "trs-filer/values.yaml" in names
    assert not [name for name in names if name.startswith("trs-filer/ci/")]


def test_notes_mongodb_auth_disabled(tmp_path: Path) -> None:
    """Without MongoDB authentication, the notes say so.

    Args:
        tmp_path: Directory for the copy of the chart.
    """
    default = render_notes(tmp_path / "default")
    assert "MongoDB runs without authentication" not in default
    notes = render_notes(tmp_path / "disabled", "--set", "mongodb.auth.enabled=false")
    assert "MongoDB runs without authentication" in notes
    # A Secret without `enabled` enables authentication (see `mongodbAuth`)
    secret_only = render_notes(
        tmp_path / "secret", "--set", "mongodb.auth.enabled=null"
    )
    assert "MongoDB runs without authentication" not in secret_only


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        pytest.param((), "Always", id="default"),
        pytest.param(
            ("--set", "trs_filer.imagePullPolicy=IfNotPresent"),
            "IfNotPresent",
            id="set",
        ),
        # Values without the setting (e.g., `--reuse-values` with older ones)
        pytest.param(
            ("--set", "trs_filer.imagePullPolicy=null"), "Always", id="without"
        ),
    ],
)
def test_app_image_pull_policy(args: tuple[str, ...], expected: str) -> None:
    """The app and the config Job pull the app's image as the value says.

    E.g., `IfNotPresent` or `Never` for an image loaded into the cluster's
    nodes (CI's job "Chart install" loads the image into kind).

    Args:
        args: Further arguments of `helm template`.
        expected: The expected pull policy.
    """
    resources = render(*args)
    for kind, name in [("Deployment", "trs-filer"), ("Job", "configmap-job-")]:
        (container,) = _pod(resources, kind, name)["containers"]
        assert container["imagePullPolicy"] == expected, kind


def test_config_overlay() -> None:
    """The `config` value is the app's second config overlay.

    It is rendered into a ConfigMap of its own, merged after the overlay
    that the config Job writes, and the app restarts when it changes (the
    checksum of the ConfigMap in the pod template).
    """
    resources = render()
    values = yaml.safe_load(TEST_VALUES.read_text())
    (config_map,) = (
        resource
        for resource in of_kind(resources, "ConfigMap")
        if resource["metadata"]["name"] == "app-config-overlay-trs-filer"
    )
    assert (
        yaml.safe_load(config_map["data"]["config.yaml"])
        == (values["trs_filer"]["config"])
    )
    (deployment,) = (
        resource
        for resource in of_kind(resources, "Deployment")
        if resource["metadata"]["name"] == "trs-filer"
    )
    annotations = deployment["spec"]["template"]["metadata"]["annotations"]
    assert len(annotations["checksum/config-overlay"]) == 64
    pod = _pod(resources, "Deployment", "trs-filer")
    (container,) = pod["containers"]
    env = {var["name"]: var.get("value") for var in container["env"]}
    assert env["FOCA_CONFIG_OVERLAY"] == (
        "/etc/trs-filer/config.yaml:/etc/trs-filer/overlay.yaml"
    )
    (mount,) = (
        m
        for m in container["volumeMounts"]
        if m["mountPath"] == "/etc/trs-filer/overlay.yaml"
    )
    (volume,) = (v for v in pod["volumes"] if v["name"] == mount["name"])
    assert volume["configMap"]["name"] == "app-config-overlay-trs-filer"


def test_config_overlay_checksum() -> None:
    """The checksum of the overlay changes with the `config` value."""

    def checksum(*args: str) -> str:
        (deployment,) = (
            resource
            for resource in of_kind(render(*args), "Deployment")
            if resource["metadata"]["name"] == "trs-filer"
        )
        value: str = deployment["spec"]["template"]["metadata"]["annotations"][
            "checksum/config-overlay"
        ]
        return value

    changed = "trs_filer.config.security.auth.audience[0]=other-client"
    assert checksum() != checksum("--set", changed)


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("--set", "trs_filer.config=null"), id="without config"),
        pytest.param(
            ("--set", "trs_filer.config.security.auth.issuers=null"), id="no issuers"
        ),
        pytest.param(
            ("--set", "trs_filer.config.security.auth.issuers=https://x.example.org/"),
            id="issuers not a list",
        ),
    ],
)
def test_config_needs_issuers(args: tuple[str, ...]) -> None:
    """Rendering fails without trusted token issuers in the `config` value.

    The app would refuse to start without them.

    Args:
        args: Further arguments of `helm template`.
    """
    with pytest.raises(subprocess.CalledProcessError) as error:
        render(*args)
    assert "trs_filer.config.security.auth.issuers must be set" in error.value.stderr
