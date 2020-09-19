"""Test for endpoint controller utility functions."""

from tests.mock_data import MOCK_ID_ONE_CHAR
from trs_filer.ga4gh.trs.endpoints.utils import generate_id


def test_generate_id():
    """Test for generating random ID with literal character set."""
    assert generate_id(charset=MOCK_ID_ONE_CHAR, length=6) == "AAAAAA"
