"""Tests of the model of the custom config."""

import pydantic
import pytest

from trs_filer.custom_config import IdConfig


@pytest.mark.parametrize("charset", ["string.ascii_uppercase", "", 1])
def test_id_config_charset(charset: object) -> None:
    """Character sets must be non-empty strings of characters.

    Args:
        charset: Invalid character set.
    """
    with pytest.raises(pydantic.ValidationError):
        IdConfig(charset=charset)  # type: ignore[arg-type]
