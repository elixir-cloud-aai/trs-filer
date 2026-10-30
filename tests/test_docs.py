"""Tests of the documentation setup (`mkdocs.yml`, `.readthedocs.yaml`)."""

from pathlib import Path
import re
import tomllib

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_readthedocs_python_version() -> None:
    """Read the Docs builds with the Python version of the base image."""
    match = re.search(
        r"^FROM elixircloud/foca:[^-@\s]+-py(?P<version>3\.\d+)@",
        (ROOT / "Dockerfile").read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert match, "No Python version in the base image tag of the Dockerfile"
    config = yaml.safe_load((ROOT / ".readthedocs.yaml").read_text(encoding="utf-8"))
    assert config["build"]["tools"]["python"] == match["version"]
    assert config["python"]["install"] == [
        {"method": "pip", "path": ".", "extra_requirements": ["docs"]}
    ]
    assert config["mkdocs"]["fail_on_warning"] is True


def test_docs_dependencies_bounded() -> None:
    """The docs dependencies are bounded by major version.

    New major versions may add warnings, which fail the strict build.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = pyproject["project"]["optional-dependencies"]["docs"]
    assert requirements
    for requirement in requirements:
        assert re.fullmatch(r"[a-z-]+>=[\d.]+,<\d+", requirement), requirement


def test_nav_lists_all_pages() -> None:
    """Every page in `docs/` is in the navigation of `mkdocs.yml`."""

    class Loader(yaml.SafeLoader):
        """YAML loader that accepts the `!ENV` tag of MkDocs."""

    Loader.add_constructor("!ENV", lambda loader, node: None)
    config = yaml.load(  # noqa: S506 (a safe loader with one more tag)
        (ROOT / "mkdocs.yml").read_text(encoding="utf-8"), Loader=Loader
    )

    def pages(nav: object) -> list[str]:
        """Collect the pages of (a part of) the navigation.

        Args:
            nav: Navigation, or one of its entries.

        Returns:
            The paths of the pages, relative to `docs/`.
        """
        if isinstance(nav, str):
            return [nav]
        if isinstance(nav, list):
            return [page for entry in nav for page in pages(entry)]
        if isinstance(nav, dict):
            return [page for entry in nav.values() for page in pages(entry)]
        return []

    docs = ROOT / "docs"
    assert sorted(pages(config["nav"])) == sorted(
        str(path.relative_to(docs)) for path in docs.rglob("*.md")
    )
