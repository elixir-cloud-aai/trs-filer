"""Tests of the Helm chart's default values (`deployment/values.yaml`)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_ingress_disabled_by_default() -> None:
    """The Ingress is disabled in the default values.

    The API has no authentication, so operators enable the Ingress only after
    restricting the methods that change data (see `deployment/README.md`).
    """
    values = yaml.safe_load(
        (ROOT / "deployment" / "values.yaml").read_text(encoding="utf-8")
    )
    assert values["trs_filer"]["ingress"]["enabled"] is False
