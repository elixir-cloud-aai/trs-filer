"""Tests of the release pin check (`scripts/check_release_pins.py`)."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_release_pins.py"

# `scripts/` is not a package, so the script is loaded from its file
_spec = importlib.util.spec_from_file_location("check_release_pins", SCRIPT)
assert _spec and _spec.loader
check_release_pins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_release_pins)

PYPROJECT = """[project]
name = "app"
dependencies = [
{dependencies}
]
"""
DOCKERFILE = """## A comment
FROM elixircloud/foca:{tag}@sha256:{digest}
USER 1000
"""
CHART = """apiVersion: v2
name: app
version: 0.0.0
appVersion: "dev"
dependencies:
  # A comment
  - name: foca-common
    version: {version}
    repository: oci://ghcr.io/elixir-cloud-aai/charts
"""
LOCK = """dependencies:
- name: foca-common
  repository: oci://ghcr.io/elixir-cloud-aai/charts
  version: {version}
digest: sha256:{digest}
generated: "2026-10-22T22:26:15.352841967+02:00"
"""
DIGEST = "0" * 64
# A `uv.lock` with the project itself and a package from PyPI
UV_LOCK = """version = 1
revision = 3
requires-python = ">=3.13"

[[package]]
name = "app"
source = { editable = "." }
dependencies = [
    { name = "foca" },
]

[[package]]
name = "foca"
version = "0.17.0"
source = { registry = "https://pypi.org/simple" }
"""
# Where `uv.lock` and `[tool.uv]` may take packages from; not the script's
# constant, so that a change of it fails the tests
PYPI = "https://pypi.org/simple"


def _write(
    root: Path,
    dependencies: str = '"foca>=0.17.0,<0.18",',
    tag: str = "0.17.0-py3.13",
    chart_version: str = "0.2.0",
    uv_lock: str = UV_LOCK,
) -> Path:
    """Write the files that the script checks.

    Args:
        root: Directory to write them to.
        dependencies: Lines of `project.dependencies` in `pyproject.toml`.
        tag: Tag of the base image in the `Dockerfile`.
        chart_version: Version of the chart's dependency, also locked and
            named by the values schema.
        uv_lock: Content of `uv.lock`.

    Returns:
        The directory.
    """
    (root / "deployment").mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT.format(dependencies=dependencies))
    (root / "uv.lock").write_text(uv_lock)
    (root / "Dockerfile").write_text(DOCKERFILE.format(tag=tag, digest=DIGEST))
    (root / "deployment" / "Chart.yaml").write_text(CHART.format(version=chart_version))
    (root / "deployment" / "Chart.lock").write_text(
        LOCK.format(version=chart_version, digest=DIGEST)
    )
    _write_schema(root, f"Schema of the library chart foca-common {chart_version}.")
    return root


def _write_schema(root: Path, comment: object) -> None:
    """Write the chart's values schema.

    Args:
        root: Root directory of the repository.
        comment: The schema's `$comment`.
    """
    (root / "deployment" / "values.schema.json").write_text(
        json.dumps({"$schema": "x", "$comment": comment, "type": "object"})
    )


def test_release_pins(tmp_path: Path) -> None:
    """Pins of released versions are accepted."""
    root = _write(tmp_path, dependencies='"connexion>=2.15.1,<3",\n"foca[x]>=0.17.0",')
    assert check_release_pins.find_dev_pins(root) == []


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        (
            {
                "dependencies": (
                    '"foca @ git+https://github.com/elixir-cloud-aai/foca@'
                    + "a" * 40
                    + '",'
                )
            },
            "pyproject.toml: dependency 'foca @ git+https://github.com/"
            f"elixir-cloud-aai/foca@{'a' * 40}' is a direct reference",
        ),
        (
            {"dependencies": '"foca[x] @ https://example.org/foca.tar.gz",'},
            "pyproject.toml: dependency 'foca[x] @ https://example.org/foca.tar.gz'"
            " is a direct reference",
        ),
        (
            {"dependencies": '"foca@https://example.org/foca.tar.gz",'},
            "pyproject.toml: dependency 'foca@https://example.org/foca.tar.gz'"
            " is a direct reference",
        ),
        (
            {"dependencies": '"Foca [x]@https://example.org/foca.tar.gz",'},
            "pyproject.toml: dependency 'Foca [x]@https://example.org/foca.tar.gz'"
            " is a direct reference",
        ),
        (
            {"dependencies": '"foca>=0.17.0rc1,<0.18",'},
            "pyproject.toml: dependency 'foca>=0.17.0rc1,<0.18' names a pre-release",
        ),
        (
            {"dependencies": "\"connexion==3.0.dev0; python_version < '3.14'\","},
            "pyproject.toml: dependency 'connexion==3.0.dev0; python_version < "
            "'3.14'' names a pre-release",
        ),
        (
            {"dependencies": '"foca==0.17.0+gabc1234",'},
            "pyproject.toml: dependency 'foca==0.17.0+gabc1234' names a local version",
        ),
        (
            {"dependencies": "\"foca===0.17.0+local.1; python_version >= '3'\","},
            "pyproject.toml: dependency 'foca===0.17.0+local.1; python_version >= "
            "'3'' names a local version",
        ),
        (
            {"tag": "20261022-py3.13"},
            "Dockerfile: FOCA image tag '20261022-py3.13' is not a release tag "
            "(<X.Y.Z>-py<X.Y>)",
        ),
        (
            {"tag": "0.17.0"},
            "Dockerfile: FOCA image tag '0.17.0' is not a release tag "
            "(<X.Y.Z>-py<X.Y>)",
        ),
        (
            {"chart_version": "0.2.0-rc1"},
            "deployment/Chart.yaml: dependency version '0.2.0-rc1' is not a "
            "release version",
        ),
        (
            {"chart_version": '"~0.2.0"'},
            "deployment/Chart.yaml: dependency version '~0.2.0' is not a "
            "release version",
        ),
        (
            {"chart_version": "0.2.0 || 0.2.1-rc1  # a comment"},
            "deployment/Chart.yaml: dependency version '0.2.0 || 0.2.1-rc1' is "
            "not a release version",
        ),
    ],
    ids=[
        "git",
        "url",
        "no-spaces",
        "extras-spaces",
        "pre-release",
        "dev-marker",
        "local",
        "local-marker",
        "dated-image",
        "no-python",
        "chart-rc",
        "chart-range",
        "chart-alternatives",
    ],
)
def test_dev_pins(tmp_path: Path, kwargs: dict[str, str], error: str) -> None:
    """Pins of development versions are found."""
    assert check_release_pins.find_dev_pins(_write(tmp_path, **kwargs)) == [error]


@pytest.mark.parametrize(
    "requirement",
    ["foca>=0.17.0", "rcpackage>=1.0", "dev-tools[a]>=2.0.post1", "abc==1.0.0b1"],
    ids=["release", "name-rc", "post-release", "beta"],
)
def test_requirement_versions(tmp_path: Path, requirement: str) -> None:
    """Only versions are checked for pre-releases, not names or extras."""
    pins = check_release_pins.find_dev_pins(
        _write(tmp_path, dependencies=f'"{requirement}",')
    )
    assert pins == (
        [f"pyproject.toml: dependency '{requirement}' names a pre-release"]
        if requirement == "abc==1.0.0b1"
        else []
    )


def test_optional_dependencies(tmp_path: Path) -> None:
    """Optional dependencies are checked, too."""
    root = _write(tmp_path)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text()
        + '[project.optional-dependencies]\ndev = ["x @ https://example.org/x.zip"]\n'
    )
    assert check_release_pins.find_dev_pins(root) == [
        "pyproject.toml: dependency 'x @ https://example.org/x.zip' is a direct "
        "reference"
    ]


@pytest.mark.parametrize("dependencies", ["[]", "{}", "[]  # none"])
def test_chart_dependencies_empty(tmp_path: Path, dependencies: str) -> None:
    """Charts with an empty list (or map) of dependencies have no findings.

    Args:
        tmp_path: Directory of the repository.
        dependencies: The empty dependencies, in flow style.
    """
    root = _write(tmp_path)
    (root / "deployment" / "Chart.yaml").write_text(
        f"name: app\ndependencies: {dependencies}\n"
    )
    assert check_release_pins.find_dev_pins(root) == []


@pytest.mark.parametrize(
    "dependencies",
    [
        "dependencies: [{name: a, version: 1.0.0-rc1}]\n",
        "dependencies:\n  - {name: a, version: 1.0.0-rc1}\n",
    ],
    ids=["flow-list", "flow-item"],
)
def test_chart_dependencies_flow(tmp_path: Path, dependencies: str) -> None:
    """Dependencies in flow style are reported, as they can't be checked."""
    root = _write(tmp_path)
    (root / "deployment" / "Chart.yaml").write_text(f"name: app\n{dependencies}")
    assert check_release_pins.find_dev_pins(root) == [
        "deployment/Chart.yaml: dependencies in flow style can't be checked"
    ]


def test_no_base_image(tmp_path: Path) -> None:
    """A `Dockerfile` without the FOCA base image is reported."""
    root = _write(tmp_path)
    (root / "Dockerfile").write_text("FROM python:3.13\n")
    assert check_release_pins.find_dev_pins(root) == [
        "Dockerfile: no elixircloud/foca base image"
    ]


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`main()` reports pins as GitHub errors, and fails if there are any."""
    released = tmp_path / "released"
    released.mkdir()
    assert check_release_pins.main([str(_write(released))]) == 0
    assert capsys.readouterr().err == ""
    dev = tmp_path / "dev"
    dev.mkdir()
    assert check_release_pins.main([str(_write(dev, tag="20261022-py3.13"))]) == 1
    assert capsys.readouterr().err == (
        "::error::Dockerfile: FOCA image tag '20261022-py3.13' is not a release "
        "tag (<X.Y.Z>-py<X.Y>): pin the released version before releasing\n"
    )


def test_main_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without arguments, `main()` checks this repository."""
    roots: list[Path] = []

    def find_dev_pins(root: Path) -> list[str]:
        roots.append(root)
        return []

    monkeypatch.setattr(check_release_pins, "find_dev_pins", find_dev_pins)
    assert check_release_pins.main([]) == 0
    assert roots == [ROOT]


def test_chart_dependencies_indentless(tmp_path: Path) -> None:
    """Dependencies listed without indentation are checked, too."""
    root = _write(tmp_path)
    (root / "deployment" / "Chart.yaml").write_text(
        "name: app\ndependencies:\n- name: a\n  version: 1.0.0-rc1\n"
        "  repository: https://example.org/charts\n  tags:\n  - b\n  - c\n"
        "version: 0.0.0\n"
    )
    assert check_release_pins.find_dev_pins(root) == [
        "deployment/Chart.yaml: dependency version '1.0.0-rc1' is not a release version"
    ]


def test_chart_dependencies(tmp_path: Path) -> None:
    """All dependencies of the chart are checked, and only their versions."""
    root = _write(tmp_path)
    (root / "deployment" / "Chart.yaml").write_text(
        """apiVersion: v2
name: app
version: 0.0.0
dependencies:  # A comment
  - name: foca-common
    version: 0.2.0
    repository: oci://ghcr.io/elixir-cloud-aai/charts
  # A comment
  - version: "1.0.0-rc1"
    name: other
    repository: "https://example.org/charts"  # A comment
    import-values:
      - child: x
        version: 2.0.0-rc1

maintainers:
  - name: someone
    version: not-a-dependency
annotations:
  version: dev
"""
    )
    assert check_release_pins.find_dev_pins(root) == [
        "deployment/Chart.yaml: dependency version '1.0.0-rc1' is not a release version"
    ]


def test_script(tmp_path: Path) -> None:
    """The script runs as the release workflow calls it."""
    shutil.copytree(ROOT / "scripts", tmp_path / "scripts")
    _write(tmp_path, chart_version="0.2.0-rc1")
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [sys.executable, "-I", str(tmp_path / "scripts" / "check_release_pins.py")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert (result.returncode, result.stdout) == (1, "")
    assert "dependency version '0.2.0-rc1'" in result.stderr


@pytest.mark.parametrize(
    ("dockerfile", "errors"),
    [
        (
            "FROM elixircloud/foca:0.17.0-py3.13 AS build\n"
            f"FROM elixircloud/foca:20261022-py3.13@sha256:{DIGEST}\n",
            [
                "Dockerfile: FOCA image tag '20261022-py3.13' is not a release "
                "tag (<X.Y.Z>-py<X.Y>)"
            ],
        ),
        (
            "from --platform=linux/amd64 docker.io/elixircloud/foca:dev\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            f"FROM elixircloud/foca@sha256:{DIGEST}\n",
            ["Dockerfile: FOCA image has no tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM elixircloud/foca-other:dev\n",
            ["Dockerfile: no elixircloud/foca base image"],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\n"
            "FROM elixircloud/foca:0.17.0-py3.12\n",
            [],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\nFROM \\\n  elixircloud/foca:dev\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\n"
            "FROM index.docker.io/elixircloud/foca:dev\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\n"
            "FROM ${REGISTRY}elixircloud/foca:dev\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\n"
            "COPY --from=elixircloud/foca:dev /app /app\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\n"
            "RUN --mount=type=bind,from=elixircloud/foca:dev,target=/x true\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\n"
            "RUN --mount=from=elixircloud/foca:dev,target=/x true\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM elixircloud/foca:0.17.0-py3.13\n"
            'RUN --mount="type=bind,from=elixircloud/foca:dev" true\n',
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "# COPY --from=elixircloud/foca:dev /x /x\n"
            "FROM \\\n  # a comment\n  elixircloud/foca:dev\n",
            ["Dockerfile: FOCA image tag 'dev' is not a release tag (<X.Y.Z>-py<X.Y>)"],
        ),
        (
            "FROM python:3.13\nCOPY --from=elixircloud/foca:0.17.0-py3.13 /x /x\n",
            ["Dockerfile: no elixircloud/foca base image"],
        ),
    ],
    ids=[
        "later-stage",
        "options",
        "no-tag",
        "other-image",
        "all-releases",
        "continued-line",
        "registry",
        "variable",
        "copy-from",
        "mount-from",
        "mount-from-first",
        "quoted-mount",
        "comments",
        "copy-from-only",
    ],
)
def test_base_images(tmp_path: Path, dockerfile: str, errors: list[str]) -> None:
    """All FOCA base images of the `Dockerfile` are checked, in any stage."""
    root = _write(tmp_path)
    (root / "Dockerfile").write_text(dockerfile)
    assert check_release_pins.find_dev_pins(root) == errors


@pytest.mark.parametrize(
    ("dependency", "errors"),
    [
        (
            "  - name: foca-common\n    version: 0.2.0\n"
            "    repository: file://../../foca/deployment/foca-common\n",
            [
                "deployment/Chart.yaml: dependency 'foca-common' has repository "
                "'file://../../foca/deployment/foca-common', not a chart repository "
                "(oci:// or https://)"
            ],
        ),
        (
            "  - name: foca-common\n"
            "    repository: oci://ghcr.io/elixir-cloud-aai/charts\n",
            ["deployment/Chart.yaml: dependency 'foca-common' has no version"],
        ),
        (
            "  - name: foca-common\n    version: 0.2.0\n    repository: '@local'\n",
            [
                "deployment/Chart.yaml: dependency 'foca-common' has repository "
                "'@local', not a chart repository (oci:// or https://)"
            ],
        ),
        (
            "  -\n    name: foca-common\n    version: 0.2.0\n"
            "    repository: oci://ghcr.io/elixir-cloud-aai/charts\n",
            [],
        ),
    ],
    ids=["file-repository", "no-version", "alias-repository", "item-on-own-line"],
)
@pytest.mark.parametrize("key", ["dependencies", '"dependencies"', "'dependencies'"])
def test_chart_dependency_sources(
    tmp_path: Path, dependency: str, errors: list[str], key: str
) -> None:
    """Chart dependencies need a version and a chart repository.

    The key `dependencies` may be quoted.
    """
    root = _write(tmp_path)
    (root / "deployment" / "Chart.yaml").write_text(f"name: app\n{key}:\n{dependency}")
    assert check_release_pins.find_dev_pins(root) == errors


def test_build_requirements(tmp_path: Path) -> None:
    """Build requirements and dependency groups are checked, too."""
    root = _write(tmp_path)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        '[build-system]\nrequires = ["setuptools>=77", '
        '"setuptools-scm @ git+https://example.org/scm"]\n'
        + pyproject.read_text()
        + '[dependency-groups]\ntest = ["pytest>=9.0rc1", {include-group = "x"}]\n'
    )
    assert check_release_pins.find_dev_pins(root) == [
        "pyproject.toml: dependency 'pytest>=9.0rc1' names a pre-release",
        "pyproject.toml: build requirement 'setuptools-scm @ "
        "git+https://example.org/scm' is a direct reference",
    ]


def _schema_error(named: str, pinned: str) -> str:
    """Return the error for a values schema of another library version.

    Args:
        named: The versions that the schema's `$comment` names.
        pinned: The version that the chart pins.

    Returns:
        The error.
    """
    return (
        f"deployment/values.schema.json: its $comment names foca-common {named} "
        "(the version that the release requires, whose values schema it is), but "
        f"deployment/Chart.yaml pins {pinned}"
    )


@pytest.mark.parametrize(
    ("comment", "named"),
    [
        ("Schema of the library chart foca-common 0.1.0.", "0.1.0"),
        ("Schema of the library chart foca-common.", "(no version)"),
        ("foca-common 0.2.0 or foca-common 0.3.0", "0.2.0, 0.3.0"),
        ("foca-common 0.2.0-rc1", "(no version)"),
        ("my-foca-common 0.2.0", "(no version)"),
        (["foca-common 0.2.0"], "(no version)"),
    ],
    ids=["other", "none", "several", "pre-release", "other-chart", "not-text"],
)
def test_library_schema(tmp_path: Path, comment: object, named: str) -> None:
    """The values schema must name the version of the library chart."""
    root = _write(tmp_path)
    _write_schema(root, comment)
    assert check_release_pins.find_dev_pins(root) == [_schema_error(named, "0.2.0")]


@pytest.mark.parametrize("schema", ["{", "[]"], ids=["invalid", "not-object"])
def test_library_schema_unreadable(tmp_path: Path, schema: str) -> None:
    """A values schema without a readable `$comment` names no version."""
    root = _write(tmp_path)
    (root / "deployment" / "values.schema.json").write_text(schema)
    assert check_release_pins.find_dev_pins(root) == [
        _schema_error("(no version)", "0.2.0")
    ]


@pytest.mark.parametrize(
    ("lock", "locked"),
    [
        (LOCK.format(version="0.1.0", digest=DIGEST), "0.1.0"),
        ("dependencies:\n- name: foca-common\n", "no version"),
        ("dependencies: []\n", "no version"),
        (None, "no version"),
    ],
    ids=["other", "no-version", "none", "no-lock"],
)
def test_library_lock(tmp_path: Path, lock: str | None, locked: str) -> None:
    """The lock file must lock the version of the library chart."""
    root = _write(tmp_path)
    path = root / "deployment" / "Chart.lock"
    if lock is None:
        path.unlink()
    else:
        path.write_text(lock)
    assert check_release_pins.find_dev_pins(root) == [
        f"deployment/Chart.lock: 'foca-common' is locked at {locked}, not at "
        "0.2.0 as in deployment/Chart.yaml"
    ]


def test_library_version_mismatch(tmp_path: Path) -> None:
    """A chart on another library version than the release requires fails.

    E.g., if the app requires a new FOCA release, but the chart was not moved
    to the matching library version.
    """
    root = _write(tmp_path, chart_version="0.1.0")
    _write_schema(root, "Schema of the library chart foca-common 0.2.0.")
    assert check_release_pins.find_dev_pins(root) == [_schema_error("0.2.0", "0.1.0")]


def _append(path: Path, text: str) -> None:
    """Append text to a file.

    Args:
        path: The file.
        text: The text to append.
    """
    path.write_text(path.read_text() + text)


def _index_error(name: str, url: str) -> str:
    """Return the error for a package index other than PyPI.

    Args:
        name: The name of the index.
        url: Its URL.

    Returns:
        The error.
    """
    return f"pyproject.toml: [[tool.uv.index]] '{name}' is {url}, not {PYPI}"


# The indexes that `test_uv_sources` defines: PyPI (with a trailing slash,
# which is the same index) and a mirror
INDEXES = f"""
[[tool.uv.index]]
name = "pypi"
url = "{PYPI}/"

[[tool.uv.index]]
name = "mirror"
url = "https://example.org/simple"
"""
MIRROR = _index_error("mirror", "https://example.org/simple")


@pytest.mark.parametrize(
    ("sources", "errors"),
    [
        (
            'foca = { git = "https://github.com/elixir-cloud-aai/foca", rev = "a" }\n',
            ["pyproject.toml: [tool.uv.sources] 'foca' is a git source", MIRROR],
        ),
        (
            'foca = { url = "https://example.org/foca.tar.gz" }\n',
            ["pyproject.toml: [tool.uv.sources] 'foca' is a url source", MIRROR],
        ),
        (
            'foca = { path = "../foca" }\n',
            ["pyproject.toml: [tool.uv.sources] 'foca' is a path source", MIRROR],
        ),
        (
            'foca = { path = "../foca", editable = true }\n',
            ["pyproject.toml: [tool.uv.sources] 'foca' is a path source", MIRROR],
        ),
        (
            "foca = { workspace = true }\n",
            ["pyproject.toml: [tool.uv.sources] 'foca' is a workspace source", MIRROR],
        ),
        (
            'foca = [\n  { git = "https://example.org/foca", marker = "os_name == '
            '\'nt\'" },\n  { index = "pypi" },\n]\n',
            ["pyproject.toml: [tool.uv.sources] 'foca' is a git source", MIRROR],
        ),
        (
            'foca = { index = "mirror" }\n',
            [
                "pyproject.toml: [tool.uv.sources] 'foca' is from index 'mirror' "
                f"(https://example.org/simple), not {PYPI}",
                MIRROR,
            ],
        ),
        (
            'foca = { index = "missing" }\n',
            [
                "pyproject.toml: [tool.uv.sources] 'foca' is from index 'missing' "
                f"(not defined), not {PYPI}",
                MIRROR,
            ],
        ),
        ('foca = { index = "pypi" }\n', [MIRROR]),
        (
            'foca = { branch = "main" }\n',
            ["pyproject.toml: [tool.uv.sources] 'foca' is an unknown source", MIRROR],
        ),
        (
            'foca = "https://example.org/foca"\n',
            ["pyproject.toml: [tool.uv.sources] 'foca' is an unknown source", MIRROR],
        ),
    ],
    ids=[
        "git",
        "url",
        "path",
        "editable",
        "workspace",
        "list",
        "other-index",
        "undefined-index",
        "pypi-index",
        "unknown",
        "not-table",
    ],
)
def test_uv_sources(tmp_path: Path, sources: str, errors: list[str]) -> None:
    """Sources of `[tool.uv.sources]` other than PyPI are reported.

    The mirror that is defined as an index is reported, too.

    Args:
        tmp_path: Directory of the repository.
        sources: The lines of `[tool.uv.sources]`.
        errors: The expected findings.
    """
    root = _write(tmp_path)
    _append(root / "pyproject.toml", f"{INDEXES}\n[tool.uv.sources]\n{sources}")
    assert check_release_pins.find_dev_pins(root) == errors


@pytest.mark.parametrize(
    ("settings", "errors"),
    [
        (f'index-url = "{PYPI}"\n', []),
        (
            'index-url = "https://example.org/simple"\n',
            [
                "pyproject.toml: [tool.uv] index-url is "
                f"https://example.org/simple, not {PYPI}"
            ],
        ),
        (
            f'extra-index-url = ["https://example.org/simple", "{PYPI}"]\n',
            [
                "pyproject.toml: [tool.uv] extra-index-url is "
                f"https://example.org/simple, not {PYPI}"
            ],
        ),
        (
            'find-links = ["./wheels"]\n',
            [f"pyproject.toml: [tool.uv] find-links is ./wheels, not {PYPI}"],
        ),
        (
            "index-url = 1\n",
            [f"pyproject.toml: [tool.uv] index-url is 1, not {PYPI}"],
        ),
        (f'[[tool.uv.index]]\nurl = "{PYPI}"\n', []),
        (
            '[[tool.uv.index]]\nurl = "https://example.org/simple"\n',
            [_index_error("(no name)", "https://example.org/simple")],
        ),
        ("index = 1\n", ["pyproject.toml: [tool.uv] index can't be read"]),
        ("index = [1]\n", ["pyproject.toml: [tool.uv] index can't be read"]),
        ("sources = 1\n", ["pyproject.toml: [tool.uv] sources can't be read"]),
    ],
    ids=[
        "pypi",
        "index-url",
        "extra-index-url",
        "find-links",
        "not-text",
        "unnamed-pypi",
        "unnamed-other",
        "index-not-list",
        "index-not-tables",
        "sources-not-table",
    ],
)
def test_uv_indexes(tmp_path: Path, settings: str, errors: list[str]) -> None:
    """Package indexes other than PyPI are reported.

    Args:
        tmp_path: Directory of the repository.
        settings: The lines of `[tool.uv]`.
        errors: The expected findings.
    """
    root = _write(tmp_path)
    _append(root / "pyproject.toml", f"\n[tool.uv]\n{settings}")
    assert check_release_pins.find_dev_pins(root) == errors


@pytest.mark.parametrize(
    ("package", "error"),
    [
        (
            'version = "1.0"\nsource = { git = "https://example.org/x?rev=a#a" }\n',
            "uv.lock: 'x' 1.0 comes from git https://example.org/x?rev=a#a",
        ),
        (
            'version = "1.0"\nsource = { url = "https://example.org/x.zip" }\n',
            "uv.lock: 'x' 1.0 comes from url https://example.org/x.zip",
        ),
        (
            'version = "1.0"\nsource = { path = "wheels/x.whl" }\n',
            "uv.lock: 'x' 1.0 comes from path wheels/x.whl",
        ),
        (
            'version = "1.0"\nsource = { directory = "../x" }\n',
            "uv.lock: 'x' 1.0 comes from directory ../x",
        ),
        (
            'version = "1.0"\nsource = { editable = "../x" }\n',
            "uv.lock: 'x' 1.0 comes from editable ../x",
        ),
        (
            'version = "1.0"\nsource = { editable = "." }\n',
            "uv.lock: 'x' 1.0 comes from editable .",
        ),
        (
            'version = "1.0"\nsource = { virtual = "../x" }\n',
            "uv.lock: 'x' 1.0 comes from virtual ../x",
        ),
        (
            'source = { registry = "https://example.org/simple" }\n',
            "uv.lock: 'x' (no version) comes from registry https://example.org/simple",
        ),
        ('version = "1.0"\n', "uv.lock: 'x' 1.0 comes from no source"),
        ('version = "1.0"\nsource = {}\n', "uv.lock: 'x' 1.0 comes from no source"),
    ],
    ids=[
        "git",
        "url",
        "path",
        "directory",
        "editable",
        "editable-root-other-name",
        "virtual",
        "other-registry",
        "no-source",
        "empty-source",
    ],
)
def test_lock_sources(tmp_path: Path, package: str, error: str) -> None:
    """Packages of `uv.lock` from other sources than PyPI are reported.

    Args:
        tmp_path: Directory of the repository.
        package: The keys of package `x` (added to `uv.lock`) after its name.
        error: The expected finding.
    """
    root = _write(tmp_path, uv_lock=f'{UV_LOCK}\n[[package]]\nname = "x"\n{package}')
    assert check_release_pins.find_dev_pins(root) == [error]


@pytest.mark.parametrize(
    ("project", "errors"),
    [
        ('name = "App"\nsource = { virtual = "." }\n', []),
        ('name = "app"\nversion = "1.0"\nsource = { editable = "." }\n', []),
        (
            'name = "app"\nversion = "1.0"\nsource = { editable = "../app" }\n',
            ["uv.lock: 'app' 1.0 comes from editable ../app"],
        ),
    ],
    ids=["virtual", "editable", "elsewhere"],
)
def test_lock_project(tmp_path: Path, project: str, errors: list[str]) -> None:
    """The project itself (`.`, by its normalized name) is not reported.

    Args:
        tmp_path: Directory of the repository.
        project: The keys of the project's package in `uv.lock`.
        errors: The expected findings.
    """
    lock = UV_LOCK.replace('name = "app"\nsource = { editable = "." }\n', project)
    assert lock != UV_LOCK
    root = _write(tmp_path, uv_lock=lock)
    assert check_release_pins.find_dev_pins(root) == errors


def test_lock_pypi_trailing_slash(tmp_path: Path) -> None:
    """PyPI with a trailing slash is PyPI."""
    lock = UV_LOCK.replace(f'"{PYPI}"', f'"{PYPI}/"')
    assert lock != UV_LOCK
    assert check_release_pins.find_dev_pins(_write(tmp_path, uv_lock=lock)) == []


@pytest.mark.parametrize(
    ("lock", "error"),
    [
        (None, "uv.lock: missing (the image is installed from it)"),
        ("[[package]\n", "uv.lock: can't be read ("),
        ("package = 1\n", "uv.lock: can't be read (no list of packages)"),
        ("package = [1]\n", "uv.lock: can't be read (no list of packages)"),
    ],
    ids=["missing", "invalid", "not-list", "not-tables"],
)
def test_lock_unreadable(tmp_path: Path, lock: str | None, error: str) -> None:
    """A missing or unreadable `uv.lock` is reported.

    Args:
        tmp_path: Directory of the repository.
        lock: Content of `uv.lock`; none if `None`.
        error: The start of the expected finding.
    """
    root = _write(tmp_path)
    if lock is None:
        (root / "uv.lock").unlink()
    else:
        (root / "uv.lock").write_text(lock)
    (pin,) = check_release_pins.find_dev_pins(root)
    assert pin.startswith(error)


def test_repository_lock() -> None:
    """This repository's `uv.lock` and `[tool.uv]` pass, but for FOCA.

    The real lock can be read, and its only possible finding is a temporary
    pin to a FOCA commit, which the release must reject until FOCA is
    released (see "Versioning and releases" in `docs/development.md`).
    """
    pins = [
        pin
        for pin in check_release_pins.find_dev_pins(ROOT)
        if pin.startswith(("uv.lock:", "pyproject.toml: [tool.uv"))
    ]
    assert all(pin.startswith("uv.lock: 'foca' ") for pin in pins), pins
    # A FOCA commit in `pyproject.toml` is locked from Git, and reported
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert bool(pins) == ("foca @ git+" in pyproject), pins


def test_lock_project_without_name(tmp_path: Path) -> None:
    """Without a project name, no package of `uv.lock` is the project."""
    root = _write(tmp_path, uv_lock='[[package]]\nsource = { editable = "." }\n')
    pyproject = root / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('name = "app"\n', ""))
    assert check_release_pins.find_dev_pins(root) == [
        "uv.lock: '(no name)' (no version) comes from editable ."
    ]
