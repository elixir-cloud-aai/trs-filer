"""Tests of the model of the custom config."""

import pydantic
import pytest

from trs_filer.custom_config import (
    AccessControlConfig,
    CustomConfig,
    IdConfig,
    IoSchemaConfig,
    ServiceConfig,
    ToolClassConfig,
)


@pytest.mark.parametrize("charset", ["string.ascii_uppercase", "", 1])
def test_id_config_charset(charset: object) -> None:
    """Character sets must be non-empty strings of characters.

    Args:
        charset: Invalid character set.
    """
    with pytest.raises(pydantic.ValidationError):
        IdConfig(charset=charset)  # type: ignore[arg-type]


def test_access_control_config_default() -> None:
    """Tool classes are added in mode `open` by default."""
    assert AccessControlConfig().tool_classes == "open"
    custom = CustomConfig(service=ServiceConfig())
    assert custom.access_control == AccessControlConfig()


@pytest.mark.parametrize("mode", ["open", "controlled", "moderated"])
def test_access_control_config_modes(mode: str) -> None:
    """The modes `open`, `controlled` and `moderated` are supported.

    Args:
        mode: Mode of adding tool classes.
    """
    assert AccessControlConfig(tool_classes=mode).tool_classes == mode  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mode", "applied"), [("open", "controlled"), ("controlled", "controlled")]
)
def test_tool_class_validation_deprecated(mode: str, applied: str) -> None:
    """The deprecated tool class validation applies the mode `controlled`.

    Args:
        mode: Mode of adding tool classes, as configured.
        applied: Mode applied.
    """
    custom = CustomConfig(
        service=ServiceConfig(),
        toolclass=ToolClassConfig(validation=True),
        access_control=AccessControlConfig(tool_classes=mode),  # type: ignore[arg-type]
    )
    assert custom.access_control.tool_classes == applied
    custom = CustomConfig(
        service=ServiceConfig(),
        access_control=AccessControlConfig(tool_classes=mode),  # type: ignore[arg-type]
    )
    assert custom.access_control.tool_classes == mode


def test_tool_class_validation_moderated() -> None:
    """The deprecated tool class validation contradicts the mode `moderated`."""
    with pytest.raises(pydantic.ValidationError, match="can't be combined"):
        CustomConfig(
            service=ServiceConfig(),
            toolclass=ToolClassConfig(validation=True),
            access_control=AccessControlConfig(tool_classes="moderated"),
        )


@pytest.mark.parametrize("mode", ["Open", "closed", "", None])
def test_access_control_config_invalid_mode(mode: object) -> None:
    """Modes other than `open`, `controlled` and `moderated` are rejected.

    Args:
        mode: Invalid mode of adding tool classes.
    """
    with pytest.raises(
        pydantic.ValidationError,
        match="Input should be 'open', 'controlled' or 'moderated'",
    ):
        AccessControlConfig(tool_classes=mode)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_io_schema_config_invalid_timeout(timeout: float) -> None:
    """Time limits of checking I/O Schemas must be positive and finite.

    Args:
        timeout: Invalid time limit.
    """
    with pytest.raises(pydantic.ValidationError):
        IoSchemaConfig(timeout=timeout)
